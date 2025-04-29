from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from .forms import UserLoginForm
from .models import ChatHistory, Quiz
from django.template.loader import render_to_string
from django.http import JsonResponse, StreamingHttpResponse
from django.core.cache import cache
import os
import requests
import json
import logging
import hashlib
import time
from collections import Counter
import re
from .tasks import generate_quiz
from celery.result import AsyncResult


logger = logging.getLogger(__name__)

@login_required
def lecture_list(request):
    lectures = [
        {'name': 'algorithms_data_structures', 'title': 'Algorithms and Data Structures'},
        {'name': 'networking', 'title': 'Networking'},
        {'name': 'operating_systems', 'title': 'Operating Systems'},
    ]
    return render(request, 'index.html', {'lectures': lectures})

@login_required
def lecture_view(request, lecture_name):
    lecture_config = {
        'algorithms_data_structures': {
            'prompt_file': 'algorithms_data_structures.txt',
            'template': 'lecture_chat.html',
            'lecture_id': 'algorithms_data_structures'
        },
        'networking': {
            'prompt_file': 'networking.txt',
            'template': 'lecture_chat.html',
            'lecture_id': 'networking'
        },
        'operating_systems': {
            'prompt_file': 'operating_systems.txt',
            'template': 'lecture_chat.html',
            'lecture_id': 'operating_systems'
        },
    }

    config = lecture_config.get(lecture_name)
    if not config:
        logger.error(f"Lecture not found: {lecture_name}")
        return render(request, '404.html', {'error': 'Lecture not found'}, status=404)

    start_time = time.time()
    cache_key = f'chat_history:{request.user.id}:{lecture_name}'
    cached_history = cache.get(cache_key)
    if cached_history:
        logger.info(f"Cache hit for {cache_key}, time: {time.time() - start_time:.3f}s")
        chat_history = cached_history
    else:
        logger.info(f"Cache miss for {cache_key}, querying SQLite")
        chat_history = ChatHistory.objects.filter(
            user=request.user, lecture=config['lecture_id']
        ).order_by('created_at')
        cache.set(cache_key, list(chat_history), timeout=3600)
        logger.info(f"Cached {cache_key}, time: {time.time() - start_time:.3f}s")

    # Fetch quizzes for the lecture
    quizzes = Quiz.objects.filter(user=request.user, lecture=lecture_name).order_by('created_at')

    if request.method == "POST":
        user_input = request.POST.get("question", "").lower()
        logger.info(f"Received question: {user_input}")

        off_topic_responses = {
            'networking': {
                'keywords': ['hash table', 'array', 'linked list', 'tree', 'graph', 'sorting', 'searching', 'process', 'memory management', 'file system', 'scheduling', 'virtualization'],
                'response': "I specialize in Networking. Please ask about network protocols, layers, security, or troubleshooting. For data structures like hash tables, try the Algorithms and Data Structures lecture, or for system processes, try Operating Systems."
            },
            'operating_systems': {
                'keywords': ['hash table', 'array', 'linked list', 'tree', 'graph', 'sorting', 'searching', 'tcp', 'udp', 'ip', 'dns', 'routing', 'switching', 'network security', 'cable', 'coax', 'ethernet', 'wifi', 'protocol'],
                'response': "I specialize in Operating Systems. Please ask about processes, memory management, or file systems. For networking topics, try the Networking lecture, or for data structures, try Algorithms and Data Structures."
            },
            'algorithms_data_structures': {
                'keywords': ['tcp', 'udp', 'ip', 'dns', 'routing', 'switching', 'network security', 'cable', 'coax', 'ethernet', 'wifi', 'protocol', 'process', 'memory management', 'file system', 'scheduling', 'virtualization'],
                'response': "This lecture focuses on Algorithms and Data Structures. Please ask about sorting, searching, or data structures like hash tables. For networking, try the Networking lecture, or for system processes, try Operating Systems."
            }
        }

        off_topic_config = off_topic_responses.get(lecture_name)
        is_ajax = request.headers.get("x-requested-with") == "XMLHttpRequest"

        if off_topic_config and any(keyword in user_input for keyword in off_topic_config['keywords']):
            logger.info(f"Off-topic question detected: {user_input}")
            bot_response = off_topic_config['response']
            ChatHistory.objects.create(
                user=request.user,
                user_input=user_input,
                bot_response=bot_response,
                lecture=config['lecture_id']
            )
            cache.delete(cache_key)
            logger.info(f"Invalidated cache: {cache_key}")
            chat_history = ChatHistory.objects.filter(
                user=request.user, lecture=config['lecture_id']
            ).order_by('created_at')
            cache.set(cache_key, list(chat_history), timeout=3600)
            logger.info(f"Re-cached {cache_key}")
            if is_ajax:
                html = render_to_string("partials/lecture_chat.html", {"chat_history": chat_history, "quizzes": quizzes})
                return JsonResponse({'html': html})
        else:
            request.session['last_question'] = user_input
            request.session.modified = True
            logger.info(f"Stored question in session: {user_input}")
            if is_ajax:
                chat_history = ChatHistory.objects.filter(
                    user=request.user, lecture=config['lecture_id']
                ).order_by('created_at')
                html = render_to_string("partials/lecture_chat.html", {"chat_history": chat_history, "quizzes": quizzes})
                return JsonResponse({'html': html})

    return render(request, config['template'], {
        "chat_history": chat_history,
        "quizzes": quizzes,
        "lecture_name": lecture_name,
        "lecture_title": lecture_name.replace('_', ' ').title(),
    })

@login_required
def stream_lecture_response(request, lecture_name):
    lecture_config = {
        'algorithms_data_structures': {
            'prompt_file': 'algorithms_data_structures.txt',
            'lecture_id': 'algorithms_data_structures'
        },
        'networking': {
            'prompt_file': 'networking.txt',
            'lecture_id': 'networking'
        },
        'operating_systems': {
            'prompt_file': 'operating_systems.txt',
            'lecture_id': 'operating_systems'
        },
    }

    config = lecture_config.get(lecture_name)
    if not config:
        logger.error(f"Stream lecture not found: {lecture_name}")
        def error_stream():
            yield f"data: {json.dumps({'error': 'Lecture not found'})}\n\n"
        return StreamingHttpResponse(error_stream(), content_type="text/event-stream")

    user_input = request.POST.get("question", request.session.get('last_question', "")).lower()
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
    normalized_question = user_input.lower().strip()
    cache_key = f'model_response:{hashlib.md5(normalized_question.encode()).hexdigest()}'
    cached_response = cache.get(cache_key)
    logger.info(f"Checked exact cache for {cache_key}: {'Hit' if cached_response else 'Miss'}, time: {time.time() - start_time:.3f}s")

    chat_history = ChatHistory.objects.filter(
        user=request.user, lecture=config['lecture_id']
    ).order_by('created_at')

    if not cached_response:
        current_keywords = extract_keywords(user_input)
        keyword_cache_key = f'question_keywords:{lecture_name}'
        keyword_map = cache.get(keyword_cache_key, {})
        
        for prev_question, prev_cache_key in keyword_map.items():
            prev_keywords = extract_keywords(prev_question)
            similarity = keyword_overlap(current_keywords, prev_keywords)
            logger.info(f"Similarity between '{user_input}' and '{prev_question}': {similarity:.2f}")
            if similarity >= 0.6:
                cached_response = cache.get(prev_cache_key)
                if cached_response:
                    logger.info(f"Semantic cache hit for similar question: {prev_question}")
                    cache_key = prev_cache_key
                    break

    if cached_response:
        logger.info(f"Streaming cached response for {normalized_question}")
        ChatHistory.objects.create(
            user=request.user,
            user_input=user_input,
            bot_response=cached_response,
            lecture=config['lecture_id']
        )
        chat_cache_key = f'chat_history:{request.user.id}:{lecture_name}'
        cache.delete(chat_cache_key)
        logger.info(f"Invalidated cache: {chat_cache_key}")
        def stream_cached_response():
            words = cached_response.split()
            chunk_size = 10
            for i in range(0, len(words), chunk_size):
                chunk = ' '.join(words[i:i + chunk_size])
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
                time.sleep(0.1)
            yield f"data: {json.dumps({'done': True})}\n\n"
        return StreamingHttpResponse(stream_cached_response(), content_type="text/event-stream")

    current_keywords = extract_keywords(user_input)
    keyword_cache_key = f'question_keywords:{lecture_name}'
    keyword_map = cache.get(keyword_cache_key, {})
    keyword_map[normalized_question] = cache_key
    cache.set(keyword_cache_key, keyword_map, timeout=86400)
    logger.info(f"Updated keyword map for {lecture_name}")

    prompt_path = os.path.join("prompts", config['prompt_file'])
    try:
        with open(prompt_path, "r") as f:
            base_prompt = f.read().strip()
        if not base_prompt:
            raise ValueError("Prompt file is empty")
    except (FileNotFoundError, ValueError) as e:
        base_prompt = f"You are a helpful CS tutor specializing in {lecture_name.replace('_', ' ').title()}."
        logger.error(f"Prompt error for {prompt_path}: {str(e)}")

    conversation = "\n".join(
        [f"You: {msg.user_input}\nBot: {msg.bot_response}" for msg in chat_history]
    )
    full_prompt = f"{base_prompt}\n\n{conversation}\nYou: {user_input}\nBot:"

    data = {
        "model": "gemma3:1b",
        "prompt": full_prompt,
        "stream": True
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
            for line in response.iter_lines():
                if line:
                    try:
                        json_data = json.loads(line.decode('utf-8'))
                        chunk = json_data.get("response", "")
                        full_response += chunk
                        yield f"data: {json.dumps({'chunk': chunk})}\n\n"
                        if json_data.get("done", False):
                            logger.info(f"Saving response for {user_input}, time: {time.time() - start_time:.3f}s")
                            ChatHistory.objects.create(
                                user=request.user,
                                user_input=user_input,
                                bot_response=full_response,
                                lecture=config['lecture_id']
                            )
                            cache.set(cache_key, full_response, timeout=86400)
                            logger.info(f"Cached response: {cache_key}")
                            chat_cache_key = f'chat_history:{request.user.id}:{lecture_name}'
                            cache.delete(chat_cache_key)
                            logger.info(f"Invalidated cache: {chat_cache_key}")
                            yield f"data: {json.dumps({'done': True})}\n\n"
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON decode error: {str(e)}")
                        yield f"data: {json.dumps({'error': 'Invalid response format'})}\n\n"
        except requests.RequestException as e:
            logger.error(f"Ollama API error: {str(e)}")
            yield f"data: {json.dumps({'error': 'Failed to connect to AI service'})}\n\n"

    logger.info(f"Streaming live response for {user_input}")
    return StreamingHttpResponse(
        stream_response(),
        content_type="text/event-stream"
    )

@login_required
def generate_quiz_view(request, lecture_name):
    lecture_config = {
        'algorithms_data_structures': {
            'prompt_file': 'algorithms_data_structures.txt',
            'lecture_id': 'algorithms_data_structures'
        },
        'networking': {
            'prompt_file': 'networking.txt',
            'lecture_id': 'networking'
        },
        'operating_systems': {
            'prompt_file': 'operating_systems.txt',
            'lecture_id': 'operating_systems'
        },
    }

    config = lecture_config.get(lecture_name)
    if not config:
        logger.error(f"Lecture not found: {lecture_name}")
        return JsonResponse({'error': 'Lecture not found'}, status=404)

    if request.method == "POST":
        logger.info(f"Triggering quiz generation for user {request.user.id}, lecture {lecture_name}")
        prompt_path = os.path.join("prompts", config['prompt_file'])
        task = generate_quiz.delay(request.user.id, lecture_name, prompt_path)
        return JsonResponse({'task_id': task.id, 'status': 'Quiz generation started'})
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

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
                return redirect('lecture_list')
            else:
                messages.error(request, "Invalid username or password.")
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
            return redirect('lecture_list')
    else:
        form = UserCreationForm()
    return render(request, 'signup.html', {'form': form})

def custom_logout(request):
    logout(request)
    return redirect('login')


@login_required
def task_status(request, task_id):
    task = AsyncResult(task_id)
    if task.state == 'SUCCESS':
        return JsonResponse({'status': 'SUCCESS'})
    elif task.state == 'FAILURE':
        return JsonResponse({'status': 'FAILURE', 'error': str(task.result)})
    return JsonResponse({'status': task.state})