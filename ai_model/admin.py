from django.contrib import admin
from .models import Quiz, ChatHistory  # Import your models

# Register the Quiz model
class QuizAdmin(admin.ModelAdmin):
    list_display = ('user', 'lecture', 'question', 'created_at')  # Customize columns to display
    search_fields = ('question',)  # Add search functionality for the question field
    list_filter = ('lecture',)  # Add a filter for the lecture field

admin.site.register(Quiz, QuizAdmin)  # Register the Quiz model with the custom admin class

# Register the ChatHistory model
class ChatHistoryAdmin(admin.ModelAdmin):
    list_display = ('user', 'lecture', 'created_at')  # Customize columns to display
    search_fields = ('user_input', 'bot_response')  # Add search functionality for inputs and responses
    list_filter = ('lecture',)  # Add a filter for the lecture field

admin.site.register(ChatHistory, ChatHistoryAdmin)  # Register the ChatHistory model with the custom admin class
