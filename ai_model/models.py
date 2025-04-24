from django.db import models
from django.contrib.auth.models import User

class ChatHistory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    user_input = models.TextField()
    bot_response = models.TextField()
    lecture = models.CharField(max_length=100, default="general")
    created_at = models.DateTimeField(auto_now_add=True)
