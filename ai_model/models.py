from django.db import models
from django.contrib.auth.models import User
import hashlib

class ChatHistory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    lecture = models.CharField(max_length=100)
    user_input = models.TextField()
    bot_response = models.TextField()
    message_id = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'lecture', 'user_input'],
                name='unique_chat_entry'
            )
        ]

    def __str__(self):
        return f"{self.user.username} - {self.lecture} - {self.user_input[:50]}"

class Quiz(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    lecture = models.CharField(max_length=100)
    question = models.TextField()
    options = models.JSONField()
    correct_answer = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

class Transcript(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    lecture = models.CharField(max_length=100)
    title = models.CharField(max_length=255)
    transcript_text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']