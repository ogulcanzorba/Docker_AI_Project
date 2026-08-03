from django.db import IntegrityError
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from .forms import UserLoginForm
from .models import ChatHistory, Quiz, Transcript
from django.template.loader import render_to_string
from django.http import JsonResponse, StreamingHttpResponse
from django.core.cache import cache
import os
import requests
import base64
import json
import logging
import hashlib
import time
import re
from .tasks import generate_quiz, generate_transcript
from .lectures import LECTURES
from celery.result import AsyncResult

logger = logging.getLogger(__name__)

@login_required
def lecture_list(request):
    lectures = [
        {'name': name, 'title': config['title']}
        for name, config in LECTURES.items()
    ]
    return render(request, 'index.html', {'lectures': lectures})

@login_required
def lecture_view(request, lecture_name):
    lecture_config = LECTURES

    config = lecture_config.get(lecture_name)
    if not config:
        logger.warning(f"Invalid lecture: {lecture_name}")
        return redirect('lecture_list')
    
    start_time = time.time()
    cache_key = f"chat_history:{request.user.id}:{lecture_name}"
    chat_history = cache.get(cache_key)
    
    if chat_history is None:
        logger.info(f"Cache miss for {cache_key}, querying SQLite")
        chat_history = ChatHistory.objects.filter(
            user=request.user,
            lecture=lecture_name
        ).order_by('created_at')
        

        seen = {}
        deduplicated = []
        for entry in chat_history:
            key = (entry.user_id, entry.lecture, entry.user_input.lower().strip())
            if key not in seen or entry.created_at > seen[key].created_at:
                seen[key] = entry
        deduplicated = list(seen.values())
        
        chat_history = deduplicated
        if chat_history:
            cache.set(cache_key, chat_history, timeout=3600)
            logger.info(
                f"Cached {cache_key}, {len(chat_history)} entries, time: {time.time() - start_time:.3f}s"
            )
        else:
            logger.debug(f"Not caching empty chat history for {cache_key}")
    
    logger.debug(
        f"Chat history for {cache_key}: {len(chat_history)} entries, "
        f"message_ids={[entry.message_id for entry in chat_history]}"
    )

    quizzes = Quiz.objects.filter(user=request.user, lecture=lecture_name).order_by('created_at')
    transcripts = Transcript.objects.filter(user=request.user, lecture=lecture_name).order_by('-created_at')

    if request.method == "POST":
        user_input = request.POST.get('question', '').strip()
        logger.info(f"Received question: {user_input}")
        is_ajax = request.headers.get("x-requested-with") == "XMLHttpRequest"

        if not user_input and is_ajax:
            logger.info(f"Empty question received, returning chat history for {lecture_name}")
            html = render_to_string("partials/lecture_chat.html", {"chat_history": chat_history, "quizzes": quizzes})
            return JsonResponse({'html': html})

        if any(keyword in user_input.lower() for keyword in ['summarize', 'explain', 'pdf', 'transcript']):
            title_query = None
            user_input_lower = user_input.lower()

            for t in transcripts:
                if t.title.lower() in user_input_lower:
                    title_query = t.title
                    break

            if not title_query:
                normalized_input = user_input.replace('-', ' ').replace('_', ' ').lower()
                for t in transcripts:
                    normalized_title = t.title.replace('-', ' ').replace('_', ' ').lower()
                    if normalized_title in normalized_input:
                        title_query = t.title
                        break

            transcript = None
            for t in transcripts:
                cache_key_transcript = f"transcript:{request.user.id}:{lecture_name}:{hashlib.md5(t.transcript_text.encode()).hexdigest()}"
                cached_data = cache.get(cache_key_transcript)
                if cached_data and (not title_query or title_query == cached_data['title']):
                    transcript = t
                    break

            if not transcript:
                transcript = transcripts.filter(title=title_query).first() if title_query else transcripts.first()

            if not transcript:
                logger.error("No transcript found for request")
                if is_ajax:
                    return JsonResponse({'error': 'No transcript found'}, status=404)
                return render(request, config['template'], {
                    'error': 'No transcript found',
                    'chat_history': chat_history,
                    'quizzes': quizzes,
                    'transcripts': transcripts,
                    'lecture_name': lecture_name,
                    'lecture_title': config['title'],
                    'lecture_config': lecture_config,
                })


            normalized_input = user_input.lower().strip()
            message_id = f"msg-{hashlib.md5(normalized_input.encode()).hexdigest()[:16]}"
            logger.debug(
                f"PDF question: original={user_input}, normalized={normalized_input}, "
                f"message_id={message_id}, transcript={transcript.title}"
            )


            existing_entry = ChatHistory.objects.filter(
                user=request.user,
                lecture=config['lecture_id'],
                user_input=normalized_input
            ).first()
            if existing_entry:
                logger.info(
                    f"Duplicate PDF chat entry detected: user={request.user.id}, "
                    f"lecture={config['lecture_id']}, normalized_input={normalized_input}, "
                    f"existing_id={existing_entry.id}, message_id={existing_entry.message_id}"
                )
                if is_ajax:
                    return JsonResponse({
                        'chunk': existing_entry.bot_response,
                        'message_id': existing_entry.message_id,
                        'done': True
                    })
                return render(request, config['template'], {
                    'chat_history': chat_history,
                    'quizzes': quizzes,
                    'transcripts': transcripts,
                    'lecture_name': lecture_name,
                    'lecture_title': config['title'],
                    'lecture_config': lecture_config,
                })

            prompt = (
                f"You are a precise CS tutor. The user asked: '{user_input}'.\n"
                f"Provide a clear, technical explanation of the following PDF summary, focusing strictly on the content provided. Do not include unrelated topics or suggestions:\n"
                f"{transcript.transcript_text}"
            )
            data = {
                "model": "gemma3:1b",
                "prompt": prompt,
                "stream": True,
                "num_ctx": 512,
                "num_predict": 300
            }

            cache_key_response = f"model_response:{request.user.id}:{hashlib.md5(normalized_input.encode()).hexdigest()}"
            cache.delete(cache_key_response)

            def stream_response():
                try:
                    response = requests.post(
                        "http://ollama:11434/api/generate",
                        json=data,
                        stream=True,
                        timeout=60
                    )
                    response.raise_for_status()
                    full_response = ""
                    for line in response.iter_lines():
                        if line:
                            try:
                                if line.strip():
                                    json_data = json.loads(line.decode('utf-8'))
                                    chunk = json_data.get("response", "")
                                    if chunk:
                                        full_response += chunk
                                        logger.debug(f"Streaming chunk: {chunk}")
                                        yield f"data: {json.dumps({'chunk': chunk, 'message_id': message_id})}\n\n"
                                    if json_data.get("done", False):
                                        logger.info(f"Stream completed for {user_input}")
                                        try:
                                            ChatHistory.objects.create(
                                                user=request.user,
                                                user_input=normalized_input,
                                                bot_response=full_response,
                                                lecture=config['lecture_id'],
                                                message_id=message_id
                                            )
                                            cache.delete(cache_key)
                                            chat_history_updated = ChatHistory.objects.filter(
                                                user=request.user, lecture=config['lecture_id']
                                            ).order_by('created_at').distinct()
                                            cache.set(cache_key, list(chat_history_updated), timeout=3600)
                                            logger.info(f"Saved chat entry for PDF question: {normalized_input}")
                                        except IntegrityError:
                                            logger.info(f"Duplicate chat entry skipped: {normalized_input}")
                                        yield f"data: {json.dumps({'done': True, 'message_id': message_id})}\n\n"
                                        break
                            except json.JSONDecodeError as e:
                                logger.error(f"JSON decode error: {str(e)}, line: {line}")
                                yield f"data: {json.dumps({'error': 'Invalid response format', 'details': str(e)})}\n\n"
                                break
                    else:
                        logger.warning("Stream ended without 'done' signal")
                        yield f"data: {json.dumps({'error': 'Stream ended unexpectedly', 'details': 'No done signal received'})}\n\n"
                except requests.RequestException as e:
                    logger.error(f"Ollama API error: {str(e)}")
                    yield f"data: {json.dumps({'error': 'Failed to connect to AI service', 'details': str(e)})}\n\n"
                except Exception as e:
                    logger.error(f"Unexpected error in stream: {str(e)}")
                    yield f"data: {json.dumps({'error': 'Unexpected server error', 'details': str(e)})}\n\n"

            if is_ajax:
                return StreamingHttpResponse(stream_response(), content_type="text/event-stream")

        off_topic_config = config.get('off_topic')
        if off_topic_config and any(keyword in user_input.lower() for keyword in off_topic_config['keywords']):
            logger.info(f"Off-topic question detected: {user_input}")
            bot_response = off_topic_config['response']
            normalized_input = user_input.lower().strip()
            message_id = f"msg-{hashlib.md5(normalized_input.encode()).hexdigest()[:16]}"
            if not ChatHistory.objects.filter(
                user=request.user,
                lecture=config['lecture_id'],
                user_input=normalized_input
            ).exists():
                ChatHistory.objects.create(
                    user=request.user,
                    user_input=normalized_input,
                    bot_response=bot_response,
                    lecture=config['lecture_id'],
                    message_id=message_id
                )
                cache.delete(cache_key)
                chat_history = ChatHistory.objects.filter(
                    user=request.user, lecture=config['lecture_id']
                ).order_by('created_at').distinct()
                cache.set(cache_key, list(chat_history), timeout=3600)
            if is_ajax:
                def stream_off_topic_response():
                    yield f"data: {json.dumps({'chunk': bot_response, 'message_id': message_id, 'done': True})}\n\n"
                return StreamingHttpResponse(stream_off_topic_response(), content_type="text/event-stream")
        if is_ajax:
            return stream_lecture_response(request, lecture_name)

    return render(request, config['template'], {
        "chat_history": chat_history,
        "quizzes": quizzes,
        "transcripts": transcripts,
        "lecture_name": lecture_name,
        "lecture_title": config['title'],
        "lecture_config": lecture_config,
    })

@login_required
def stream_lecture_response(request, lecture_name):
    config = LECTURES.get(lecture_name)
    if not config:
        logger.error(f"Stream lecture not found: {lecture_name}")
        def error_stream():
            yield f"data: {json.dumps({'error': 'Lecture not found'})}\n\n"
        return StreamingHttpResponse(error_stream(), content_type="text/event-stream")

    user_input = request.POST.get("question", "").strip()
    if not user_input:
        logger.error("No question provided for streaming")
        def error_stream():
            yield f"data: {json.dumps({'error': 'No question provided'})}\n\n"
        return StreamingHttpResponse(error_stream(), content_type="text/event-stream")

    def extract_keywords(text):
        words = re.findall(r'\b\w+\b', text.lower())
        stop_words = {'what', 'is', 'a', 'does', 'the', 'mean', 'in', 'and', 'or', 'to'}
        keywords = [word for word in words if word not in stop_words and len(word) > 2]
        return set(keywords)

    def keyword_overlap(keywords1, keywords2):
        if not keywords1 or not keywords2:
            return 0.0
        intersection = len(keywords1 & keywords2)
        union = len(keywords1 | keywords2)
        return intersection / union if union > 0 else 0.0

    start_time = time.time()
    normalized_input = user_input.lower().strip()
    cache_key = f'model_response:{request.user.id}:{hashlib.md5(normalized_input.encode()).hexdigest()}'
    cached_response = cache.get(cache_key)
    logger.info(f"Checked exact cache for {cache_key}: {'Hit' if cached_response else 'Miss'}, time: {time.time() - start_time:.3f}s")

    if cached_response:
        logger.info(f"Streaming cached response for {normalized_input}")
        message_id = f"msg-{hashlib.md5(normalized_input.encode()).hexdigest()[:16]}"
        if not ChatHistory.objects.filter(
            user=request.user,
            lecture=config['lecture_id'],
            user_input=normalized_input
        ).exists():
            try:
                ChatHistory.objects.create(
                    user=request.user,
                    user_input=normalized_input,
                    bot_response=cached_response,
                    lecture=config['lecture_id'],
                    message_id=message_id
                )
                cache_key_history = f"chat_history:{request.user.id}:{lecture_name}"
                cache.delete(cache_key_history)
                chat_history_updated = ChatHistory.objects.filter(
                    user=request.user, lecture=config['lecture_id']
                ).order_by('created_at').distinct()
                cache.set(cache_key_history, list(chat_history_updated), timeout=3600)
                logger.info(f"Saved cached chat entry: {normalized_input}")
            except IntegrityError:
                logger.info(f"Duplicate cached chat entry skipped: {normalized_input}")
        def stream_cached_response():
            words = cached_response.split()
            chunk_size = 10
            for i in range(0, len(words), chunk_size):
                chunk = ' '.join(words[i:i + chunk_size])
                yield f"data: {json.dumps({'chunk': chunk, 'message_id': message_id})}\n\n"
                time.sleep(0.1)
            yield f"data: {json.dumps({'done': True, 'message_id': message_id})}\n\n"
        return StreamingHttpResponse(stream_cached_response(), content_type="text/event-stream")

    current_keywords = extract_keywords(normalized_input)
    keyword_cache_key = f'question_keywords:{request.user.id}:{lecture_name}'
    keyword_map = cache.get(keyword_cache_key, {})
    logger.debug(f"Keyword map for {keyword_cache_key}: {list(keyword_map.keys())}")

    for prev_question, prev_cache_key in keyword_map.items():
        prev_keywords = extract_keywords(prev_question)
        similarity = keyword_overlap(current_keywords, prev_keywords)
        logger.info(f"Similarity between '{normalized_input}' and '{prev_question}': {similarity:.2f}")
        if similarity >= 0.6:
            cached_response = cache.get(prev_cache_key)
            if cached_response:
                logger.info(f"Semantic cache hit for similar question: {prev_question}")
                message_id = f"msg-{hashlib.md5(normalized_input.encode()).hexdigest()[:16]}"
                if not ChatHistory.objects.filter(
                    user=request.user,
                    lecture=config['lecture_id'],
                    user_input=normalized_input
                ).exists():
                    try:
                        ChatHistory.objects.create(
                            user=request.user,
                            user_input=normalized_input,
                            bot_response=cached_response,
                            lecture=config['lecture_id'],
                            message_id=message_id
                        )
                        cache_key_history = f"chat_history:{request.user.id}:{lecture_name}"
                        cache.delete(cache_key_history)
                        chat_history_updated = ChatHistory.objects.filter(
                            user=request.user, lecture=config['lecture_id']
                        ).order_by('created_at').distinct()
                        cache.set(cache_key_history, list(chat_history_updated), timeout=3600)
                        logger.info(f"Saved semantic cached chat entry: {normalized_input}")
                    except IntegrityError:
                        logger.info(f"Duplicate semantic cached chat entry skipped: {normalized_input}")
                def stream_cached_response():
                    words = cached_response.split()
                    chunk_size = 10
                    for i in range(0, len(words), chunk_size):
                        chunk = ' '.join(words[i:i + chunk_size])
                        yield f"data: {json.dumps({'chunk': chunk, 'message_id': message_id})}\n\n"
                        time.sleep(0.1)
                    yield f"data: {json.dumps({'done': True, 'message_id': message_id})}\n\n"
                return StreamingHttpResponse(stream_cached_response(), content_type="text/event-stream")


    keyword_map[normalized_input] = cache_key
    cache.set(keyword_cache_key, keyword_map, timeout=86400)
    logger.info(f"Updated keyword map for {lecture_name} with {normalized_input}")

    prompt_path = os.path.join("prompts", config['prompt_file'])
    try:
        with open(prompt_path, "r") as f:
            base_prompt = f.read().strip()
        if not base_prompt:
            raise ValueError("Prompt file is empty")
    except (FileNotFoundError, ValueError) as e:
        base_prompt = f"You are a helpful CS tutor specializing in {lecture_name.replace('_', ' ').title()}."
        logger.error(f"Prompt error for {prompt_path}: {str(e)}")

    chat_history = ChatHistory.objects.filter(
        user=request.user, lecture=config['lecture_id']
    ).order_by('created_at').distinct()
    conversation = "\n".join(
        [f"You: {msg.user_input}\nBot: {msg.bot_response}" for msg in chat_history]
    )
    full_prompt = (
        f"{base_prompt}\n\n"
        f"{conversation}\n"
        f"You: {user_input}\n"
        f"Bot: Provide a clear, technical response focused strictly on the user's question. Do not include unrelated topics or suggestions."
    )

    data = {
        "model": "gemma3:1b",
        "prompt": full_prompt,
        "stream": True,
        "num_ctx": 512,
        "num_predict": 300
    }

    def stream_response():
        try:
            response = requests.post(
                "http://ollama:11434/api/generate",
                json=data,
                stream=True,
                timeout=60
            )
            response.raise_for_status()
            full_response = ""
            message_id = f"msg-{hashlib.md5(normalized_input.encode()).hexdigest()[:16]}"
            for line in response.iter_lines():
                if line:
                    try:
                        json_data = json.loads(line.decode('utf-8'))
                        chunk = json_data.get("response", "")
                        full_response += chunk
                        logger.debug(f"Streaming chunk: {chunk}")
                        yield f"data: {json.dumps({'chunk': chunk, 'message_id': message_id})}\n\n"
                        if json_data.get("done", False):
                            logger.info(f"Saving response for {user_input}, time: {time.time() - start_time:.3f}s")
                            if not ChatHistory.objects.filter(
                                user=request.user,
                                lecture=config['lecture_id'],
                                user_input=normalized_input
                            ).exists():
                                try:
                                    ChatHistory.objects.create(
                                        user=request.user,
                                        user_input=normalized_input,
                                        bot_response=full_response,
                                        lecture=config['lecture_id'],
                                        message_id=message_id
                                    )
                                    cache_key_history = f"chat_history:{request.user.id}:{lecture_name}"
                                    cache.delete(cache_key_history)
                                    chat_history_updated = ChatHistory.objects.filter(
                                        user=request.user, lecture=config['lecture_id']
                                    ).order_by('created_at').distinct()
                                    cache.set(cache_key_history, list(chat_history_updated), timeout=3600)
                                    logger.info(f"Saved chat entry: {normalized_input}")
                                    # Cache the response
                                    cache.set(cache_key, full_response, timeout=3600)
                                    logger.info(f"Cached response: {cache_key}")
                                except IntegrityError:
                                    logger.info(f"Duplicate chat entry skipped: {normalized_input}")
                            yield f"data: {json.dumps({'done': True, 'message_id': message_id})}\n\n"
                            break
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON decode error: {str(e)}")
                        yield f"data: {json.dumps({'error': 'Invalid response format', 'details': str(e)})}\n\n"
                        break
        except requests.RequestException as e:
            logger.error(f"Ollama API error: {str(e)}")
            yield f"data: {json.dumps({'error': 'Failed to connect to AI service', 'details': str(e)})}\n\n"

    logger.info(f"Streaming live response for {user_input}")
    return StreamingHttpResponse(
        stream_response(),
        content_type="text/event-stream"
    )

@login_required
def generate_quiz_view(request, lecture_name):
    config = LECTURES.get(lecture_name)
    if not config:
        logger.error(f"Lecture not found: {lecture_name}")
        return JsonResponse({'error': 'Lecture not found'}, status=404)

    if request.method == "POST":
        logger.info(f"Triggering quiz generation for user {request.user.id}, lecture {lecture_name}")
        prompt_path = os.path.join("prompts", config['prompt_file'])
        task = generate_quiz.delay(request.user.id, lecture_name, prompt_path)
        return JsonResponse({'task_id': task.id, 'status': 'Quiz generation started'})

    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def submit_quiz_answer(request, quiz_id):
    if request.method != "POST":
        return JsonResponse({'error': 'Invalid request method'}, status=400)

    quiz = get_object_or_404(Quiz, id=quiz_id, user=request.user)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    selected_answer = data.get('selected_answer', '')
    if selected_answer not in quiz.options:
        return JsonResponse({'error': 'Invalid answer'}, status=400)

    quiz.selected_answer = selected_answer
    quiz.save(update_fields=['selected_answer'])
    logger.info(f"Quiz {quiz.id} answered by user {request.user.id}: {selected_answer}")
    return JsonResponse({'status': 'success', 'correct': selected_answer == quiz.correct_answer})

@login_required
def retry_quiz(request, lecture_name):
    if request.method != "POST":
        return JsonResponse({'error': 'Invalid request method'}, status=400)
    if lecture_name not in LECTURES:
        return JsonResponse({'error': 'Lecture not found'}, status=404)

    updated = Quiz.objects.filter(user=request.user, lecture=lecture_name).update(selected_answer=None)
    logger.info(f"Quiz retry: user {request.user.id}, lecture {lecture_name}, {updated} question(s) reset")
    return JsonResponse({'status': 'success'})

@login_required
def upload_lecture_pdf(request, lecture_name):
    if request.method == "POST":
        logger.info("POST request received for PDF upload")

        lecture_name = request.POST.get('lecture_name')
        if lecture_name not in LECTURES:
            logger.error(f"Invalid lecture name: {lecture_name}")
            return JsonResponse({'error': 'Please select a valid lecture'}, status=400)
        
        if request.FILES.get('pdf_file'):
            pdf_file = request.FILES['pdf_file']
            if not pdf_file.name.lower().endswith('.pdf'):
                logger.error(f"Invalid file format: {pdf_file.name}")
                return JsonResponse({'error': 'Only PDF files are allowed'}, status=400)
            
            logger.info(f"PDF file received: {pdf_file.name}")
            try:
                pdf_bytes = pdf_file.read()
                pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
                pdf_hash = hashlib.md5(pdf_bytes).hexdigest()
                pdf_filename = pdf_file.name.rsplit('.', 1)[0]
                task = generate_transcript.delay(request.user.id, lecture_name, pdf_base64, pdf_hash, pdf_filename)
                logger.info(f"Task queued: {task.id}")
                return JsonResponse({'task_id': task.id, 'status': 'Transcript generation started'})
            except Exception as e:
                logger.error(f"Error processing PDF: {str(e)}")
                return JsonResponse({'error': 'Error processing PDF'}, status=500)
        else:
            logger.error("No PDF file provided")
            return JsonResponse({'error': 'Please select a PDF file'}, status=400)

    return redirect('lecture', lecture_name=lecture_name)
    
@login_required
def transcript_detail(request, transcript_id):
    transcript = get_object_or_404(Transcript, id=transcript_id, user=request.user)
    return render(request, 'transcript_detail.html', {'transcript': transcript})

def login_page(request):
    if request.user.is_authenticated:
        return redirect('lecture_list')
    if request.method == 'POST':
        form = UserLoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                return redirect('lecture_list')  # Removed success message
            else:
                messages.error(request, "Invalid username or password.")
        return render(request, 'login.html', {'form': form})
    else:
        form = UserLoginForm()
    return render(request, 'login.html', {'form': form})

def signup(request):
    if request.user.is_authenticated:
        return redirect('lecture_list')
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Account created successfully! You are now logged in.")
            return redirect('lecture_list')
        else:
            messages.error(request, "There was an error with your submission. Please check the form.")
            return render(request, 'signup.html', {'form': form})
    else:
        form = UserCreationForm()
    return render(request, 'signup.html', {'form': form})

def custom_logout(request):
    logout(request)
    return redirect('login')

@login_required
def task_status(request, task_id):
    task = AsyncResult(task_id)
    logger.info(f"Task {task_id} status: {task.state}")
    if task.state == 'SUCCESS':
        return JsonResponse({'status': 'SUCCESS'})
    elif task.state == 'FAILURE':
        return JsonResponse({'status': 'FAILURE', 'error': str(task.result)})
    return JsonResponse({'status': task.state})

@login_required
def save_chat(request, lecture_name):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            question = data.get("question", "").strip()
            answer = data.get("answer", "").strip()
            lecture = data.get("lecture", lecture_name)
            message_id = data.get("message_id")
            user = request.user

            normalized_question = question.lower().strip()
            logger.debug(
                f"save_chat: user_id={user.id}, lecture={lecture}, "
                f"message_id={message_id}, original_question={question}, "
                f"normalized_question={normalized_question}"
            )


            if not all([question, answer, lecture, message_id]):
                logger.error(
                    f"Missing fields in save_chat: "
                    f"question={bool(question)}, answer={bool(answer)}, "
                    f"lecture={bool(lecture)}, "
                    f"message_id={bool(message_id)}, received: {data}"
                )
                return JsonResponse({"status": "error", "error": "Missing required fields"}, status=400)

            existing_entry = ChatHistory.objects.filter(
                user=user,
                lecture=lecture,
                user_input=normalized_question
            ).first()
            if existing_entry:
                logger.info(
                    f"Duplicate chat entry detected for user {user.id}, "
                    f"lecture {lecture}, normalized_question={normalized_question}, "
                    f"existing entry: id={existing_entry.id}, message_id={existing_entry.message_id}"
                )
                return JsonResponse({"status": "success", "message_id": existing_entry.message_id})


            chat_entry = ChatHistory.objects.create(
                user=user,
                lecture=lecture,
                user_input=normalized_question,
                bot_response=answer,
                message_id=message_id
            )
            cache_key = f"chat_history:{user.id}:{lecture}"
            cache.delete(cache_key)
            logger.info(f"Saved chat entry {chat_entry.id} for user {user.id}, lecture {lecture}")
            return JsonResponse({"status": "success", "message_id": message_id})
        
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in save_chat: {str(e)}, body: {request.body[:500]}")
            return JsonResponse({"status": "error", "error": "Invalid JSON format"}, status=400)
        
        except IntegrityError as e:
            logger.error(f"Database integrity error in save_chat: {str(e)}, data: {data}")
            return JsonResponse({"status": "success", "message_id": message_id})
        
        except Exception as e:
            logger.error(f"Unexpected error in save_chat: {str(e)}, data: {data}", exc_info=True)
            return JsonResponse({"status": "error", "error": f"Server error: {str(e)}"}, status=500)
    
    logger.warning(f"Invalid method for save_chat: {request.method}")
    return JsonResponse({"status": "error", "error": "Method not allowed"}, status=405)