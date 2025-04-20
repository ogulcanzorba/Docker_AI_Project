from django.shortcuts import render
from django.contrib.auth.forms import UserCreationForm
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login
from .forms import UserLoginForm
from django.contrib import messages
import requests
from .models import ChatHistory
from django.template.loader import render_to_string
from django.http import JsonResponse

@login_required
def index(request):
    chat_history = ChatHistory.objects.filter(user=request.user).order_by('created_at')

    if request.method == "POST":
        user_input = request.POST.get("question", "")
        conversation = "\n".join(
            [f"You: {msg.user_input}\nBot: {msg.bot_response}" for msg in chat_history]
        )
        full_prompt = f"{conversation}\nYou: {user_input}\nBot:"

        url = "http://ollama:11434/api/generate"
        data = {
            "model": "gemma3:1b",
            "prompt": full_prompt,
            "stream": False
        }
        response = requests.post(url, json=data)
        bot_response = response.json().get("response", "Sorry, no response.")

        ChatHistory.objects.create(user=request.user, user_input=user_input, bot_response=bot_response)

        # AJAX partial update
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            chat_history = ChatHistory.objects.filter(user=request.user).order_by('created_at')
            html = render_to_string("partials/chat_box.html", {"chat_history": chat_history})
            return JsonResponse({'html': html})

    return render(request, "index.html", {"chat_history": chat_history})



def login_page(request):
    if request.method == 'POST':
        form = UserLoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                return redirect('chat')
            else:
                messages.error(request, "Invalid username or password.")
    else:
        form = UserLoginForm()

    return render(request, 'login.html', {'form': form})



def signup(request):
    if request.user.is_authenticated:
        return redirect('chat')  # Redirect if already logged in

    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('chat')  # Redirect to chatbot after signup
    else:
        form = UserCreationForm()
    return render(request, 'signup.html', {'form': form})


# Fetch AI response
def generate_ai_response(request):
    user_prompt = request.GET.get('prompt', 'Explain AI')

    url = "http://ollama:11434/api/generate"
    data = {
        "model": "gemma3:1b",
        "prompt": user_prompt,
        "stream": False
    }

    response = requests.post(url, json=data)
    print("Status Code:", response.status_code)
    print("Response Text:", response.text)

    return JsonResponse(response.json())


from django.contrib.auth import logout

def custom_logout(request):
    logout(request)
    return redirect('login_page')
