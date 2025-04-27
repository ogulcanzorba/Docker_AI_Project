from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from .forms import UserLoginForm
from .models import ChatHistory
from django.template.loader import render_to_string
from django.http import JsonResponse, StreamingHttpResponse
import os
import requests
import json
import logging

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
        return render(request, '404.html', {'error': 'Lecture not found'}, status=404)

    chat_history = ChatHistory.objects.filter(
        user=request.user, lecture=config['lecture_id']
    ).order_by('created_at')

    if request.method == "POST":
        user_input = request.POST.get("question", "").lower()

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
            bot_response = off_topic_config['response']
            ChatHistory.objects.create(
                user=request.user,
                user_input=user_input,
                bot_response=bot_response,
                lecture=config['lecture_id']
            )
            if is_ajax:
                chat_history = ChatHistory.objects.filter(
                    user=request.user, lecture=config['lecture_id']
                ).order_by('created_at')
                html = render_to_string("partials/lecture_chat.html", {"chat_history": chat_history})
                return JsonResponse({'html': html})
        else:
            # Store question in session for streaming
            request.session['last_question'] = user_input
            request.session.modified = True
            if is_ajax:
                chat_history = ChatHistory.objects.filter(
                    user=request.user, lecture=config['lecture_id']
                ).order_by('created_at')
                html = render_to_string("partials/lecture_chat.html", {"chat_history": chat_history})
                return JsonResponse({'html': html})

    return render(request, config['template'], {
        "chat_history": chat_history,
        "lecture_name": lecture_name,
        "lecture_title": lecture_name.replace('_', ' ').title()
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
        def error_stream():
            yield f"data: {json.dumps({'error': 'Lecture not found'})}\n\n"
        return StreamingHttpResponse(error_stream(), content_type="text/event-stream")

    # Get question from POST or session
    user_input = request.POST.get("question", request.session.get('last_question', "")).lower()
    if not user_input:
        def error_stream():
            yield f"data: {json.dumps({'error': 'No question provided'})}\n\n"
        return StreamingHttpResponse(error_stream(), content_type="text/event-stream")

    chat_history = ChatHistory.objects.filter(
        user=request.user, lecture=config['lecture_id']
    ).order_by('created_at')

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
                timeout=30
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
                            ChatHistory.objects.create(
                                user=request.user,
                                user_input=user_input,
                                bot_response=full_response,
                                lecture=config['lecture_id']
                            )
                            yield f"data: {json.dumps({'done': True})}\n\n"
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON decode error: {str(e)}")
                        yield f"data: {json.dumps({'error': 'Invalid response format'})}\n\n"
        except requests.RequestException as e:
            logger.error(f"Ollama API error: {str(e)}")
            yield f"data: {json.dumps({'error': 'Failed to connect to AI service'})}\n\n"

    return StreamingHttpResponse(
        stream_response(),
        content_type="text/event-stream"
    )

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