from django.http import JsonResponse
from django.shortcuts import render
import requests

def index(request):
    # Chat geçmişini session'dan al
    chat_history = request.session.get('chat_history', [])

    if request.method == "POST":
        user_input = request.POST.get("question", "")

        # Konuşma geçmişini tek bir prompt içinde birleştir
        conversation = "\n".join([f"You: {msg['user']}\nBot: {msg['bot']}" for msg in chat_history])
        full_prompt = f"{conversation}\nYou: {user_input}\nBot:"

        # Ollama API çağrısı
        url = "http://localhost:11434/api/generate"
        data = {
            "model": "gemma3:1b",
            "prompt": full_prompt,
            "stream": False
        }
        response = requests.post(url, json=data)
        bot_response = response.json().get("response", "Üzgünüm, yanıt üretemedim.")

        # Yeni mesajı geçmişe ekle
        chat_history.append({"user": user_input, "bot": bot_response})
        request.session["chat_history"] = chat_history  # Session'a kaydet

    return render(request, "index.html", {"chat_history": chat_history})



# Fetch AI response
def generate_ai_response(request):
    user_prompt = request.GET.get('prompt', 'Explain AI')

    url = "http://localhost:11434/api/generate"
    data = {
        "model": "gemma3:1b",
        "prompt": user_prompt,
        "stream": False
    }

    response = requests.post(url, json=data)
    return JsonResponse(response.json())
