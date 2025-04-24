from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from .forms import UserLoginForm
from .models import ChatHistory
from django.template.loader import render_to_string
from django.http import JsonResponse
import os
import requests

@login_required
def lecture_list(request):
    lectures = [
        {'name': 'algorithms_data_structures', 'title': 'Algorithms and Data Structures'},
        # Add more lectures here, e.g., {'name': 'operating_systems', 'title': 'Operating Systems'}
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
        # Add more lectures here
    }

    config = lecture_config.get(lecture_name)
    if not config:
        return render(request, '404.html', {'error': 'Lecture not found'}, status=404)

    chat_history = ChatHistory.objects.filter(
        user=request.user, lecture=config['lecture_id']
    ).order_by('created_at')

    if request.method == "POST":
        user_input = request.POST.get("question", "")
        prompt_path = os.path.join("prompts", config['prompt_file'])
        try:
            with open(prompt_path, "r") as f:
                base_prompt = f.read()
        except FileNotFoundError:
            return render(request, '404.html', {'error': 'Prompt not found'}, status=404)

        conversation = "\n".join(
            [f"You: {msg.user_input}\nBot: {msg.bot_response}" for msg in chat_history]
        )
        full_prompt = f"{base_prompt}\n\n{conversation}\nYou: {user_input}\nBot:"

        data = {
            "model": "gemma3:1b",
            "prompt": full_prompt,
            "stream": False
        }
        response = requests.post("http://ollama:11434/api/generate", json=data)
        bot_response = response.json().get("response", "Sorry, no response.")

        ChatHistory.objects.create(
            user=request.user,
            user_input=user_input,
            bot_response=bot_response,
            lecture=config['lecture_id']
        )

        if request.headers.get("x-requested-with") == "XMLHttpRequest":
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

def login_page(request):
    if request.user.is_authenticated:
        return redirect('lecture_list')  # Redirect to lecture list if logged in
    if request.method == 'POST':
        form = UserLoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                return redirect('lecture_list')  # Redirect to lecture list
            else:
                messages.error(request, "Invalid username or password.")
    else:
        form = UserLoginForm()
    return render(request, 'login.html', {'form': form})

def signup(request):
    if request.user.is_authenticated:
        return redirect('lecture_list')  # Redirect to lecture list
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('lecture_list')  # Redirect to lecture list
    else:
        form = UserCreationForm()
    return render(request, 'signup.html', {'form': form})

def custom_logout(request):
    logout(request)
    return redirect('login')