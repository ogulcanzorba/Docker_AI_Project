from django.db import models
from django.contrib.auth.models import User

class ChatHistory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    lecture = models.CharField(max_length=100)
    user_input = models.TextField(blank=True)
    bot_response = models.TextField(blank=True)
    quiz_id = models.ForeignKey('Quiz', null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

class Quiz(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    lecture = models.CharField(max_length=100)
    question = models.TextField()
    options = models.JSONField()
    correct_answer = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)