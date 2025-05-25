from django.contrib import admin
from .models import Quiz, ChatHistory,Transcript


class QuizAdmin(admin.ModelAdmin):
    list_display = ('user', 'lecture', 'question', 'created_at')
    search_fields = ('question',)
    list_filter = ('lecture',)

admin.site.register(Quiz, QuizAdmin)


class ChatHistoryAdmin(admin.ModelAdmin):
    list_display = ('user', 'lecture', 'created_at')
    search_fields = ('user_input', 'bot_response')
    list_filter = ('lecture',)

admin.site.register(ChatHistory, ChatHistoryAdmin)


class TranscriptAdmin(admin.ModelAdmin):
    list_display = ('user', 'lecture', 'created_at', )
    search_fields = ('transcript_text', 'lecture', 'user__username')
    list_filter = ('lecture', 'created_at')
    readonly_fields = ('transcript_text', 'created_at')


admin.site.register(Transcript, TranscriptAdmin)  