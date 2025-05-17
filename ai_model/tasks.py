from celery import shared_task
from django.core.cache import cache
from django.conf import settings
from django.contrib.auth.models import User
from .models import ChatHistory, Quiz, Transcript
import requests
import re
import logging
from .utils.pdf_processing import process_lecture_pdf
import os

logger = logging.getLogger(__name__)

@shared_task
def generate_quiz(user_id, lecture_name, lecture_prompt_path):
    logger.info(f"Starting quiz generation for user {user_id}, lecture {lecture_name}")

    try:
        with open(lecture_prompt_path, "r") as f:
            base_prompt = f.read().strip()
        if not base_prompt:
            raise ValueError("Prompt file is empty")
    except (FileNotFoundError, ValueError) as e:
        base_prompt = f"You are a helpful CS tutor specializing in {lecture_name.replace('_', ' ').title()}."
        logger.error(f"Prompt error for {lecture_prompt_path}: {str(e)}")

    cache_key = f"chat_history:{user_id}:{lecture_name}"
    chat_history = cache.get(cache_key)
    conversation = ""

    if chat_history:
        recent_history = chat_history[-5:]
        conversation_lines = []
        total_chars = 0
        max_chars = 1000
        for msg in recent_history:
            user_input = msg.user_input.strip()
            bot_response = msg.bot_response.strip()
            if user_input.endswith("?") or any(
                    kw in user_input.lower() for kw in ["explain", "how does", "why", "what is"]):
                line = f"User question: {user_input}"
            else:
                line = f"You: {user_input}\nBot: {bot_response}"
            if total_chars + len(line) <= max_chars:
                conversation_lines.append(line)
                total_chars += len(line)
            else:
                break
        conversation = "\n".join(conversation_lines)
        logger.info(f"Using Redis chat history: {len(recent_history)} messages, {total_chars} chars")
    else:
        logger.info("Redis cache miss, falling back to SQLite")
        db_history = ChatHistory.objects.filter(user_id=user_id, lecture=lecture_name).order_by('created_at')
        conversation_lines = []
        total_chars = 0
        max_chars = 1000
        for msg in db_history:
            user_input = msg.user_input.strip()
            bot_response = msg.bot_response.strip()
            if user_input.endswith("?") or any(
                    keyword in user_input.lower() for keyword in ["explain", "how", "why", "what is", "difference"]):
                line = f"User question: {user_input}"
            else:
                line = f"You: {user_input}\nBot: {bot_response}"
            if total_chars + len(line) <= max_chars:
                conversation_lines.append(line)
                total_chars += len(line)
            else:
                break
        conversation = "\n".join(conversation_lines)
        logger.info(f"Using SQLite chat history: {len(db_history)} messages, {total_chars} chars")

    quiz_prompt = (
        f"You are a helpful computer science tutor creating a quiz for the topic: \"{lecture_name.replace('_', ' ').title()}\".\n\n"
        "Based on the following lecture and conversation history, generate exactly 5 multiple-choice questions. Each question must follow this strict format:\n\n"
        "1. Question text\n"
        "A) Option A\n"
        "B) Option B\n"
        "C) Option C\n"
        "D) Option D\n"
        "Correct: X\n\n"
        "Where X is one of A, B, C, or D.\n\n"
        "=== Conversation History ===\n"
        f"{conversation}\n"
        "=== End ===\n\n"
        "⚠️ Instructions:\n"
        "- Do NOT include introductions, explanations, or summaries.\n"
        "- Do NOT include markdown (like **bold**, `code`, or ### headers).\n"
        "- Do NOT output JSON, emojis, or anything outside the format.\n"
        "- Do NOT say \"Here is your quiz\", \"1)\" instead of \"1.\", or label correct answers in the options.\n"
        "- Ensure all 5 questions are clearly numbered 1 to 5 and each has exactly 4 choices and one Correct line.\n\n"
        "🎯 Correct Output Example:\n\n"
        "1. What is the capital of France?\n"
        "A) Berlin\n"
        "B) Madrid\n"
        "C) Paris\n"
        "D) Rome\n"
        "Correct: C\n\n"
        "2. Which data structure uses LIFO?\n"
        "A) Queue\n"
        "B) Array\n"
        "C) Stack\n"
        "D) Linked List\n"
        "Correct: C\n\n"
        "Now, generate the quiz using only the format shown above."
    )

    try:
        response = requests.post(
            "http://ollama:11434/api/generate",
            json={"model": "gemma3:1b", "prompt": quiz_prompt, "stream": False},
            timeout=60
        )
        response.raise_for_status()
        ollama_data = response.json()
        quiz_text = ollama_data.get("response", "")
        logger.info(f"Raw Ollama response: {quiz_text[:500]}...")
        if not quiz_text:
            logger.error("Empty response from Ollama")
            raise ValueError("Empty response from Ollama")

        cleaned_text = ""
        lines = quiz_text.strip().split('\n')
        in_question_block = False
        question_lines = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if re.match(r'^\d+\.\s', line):
                if question_lines:
                    cleaned_text += '\n'.join(question_lines) + '\n\n'
                    question_lines = []
                in_question_block = True
                question_lines.append(line)
            elif in_question_block and (re.match(r'^[A-D]\)', line) or line.startswith("Correct:")):
                question_lines.append(line)
            elif in_question_block and line.startswith("Correct:"):
                question_lines.append(line)
                in_question_block = False
        if question_lines:
            cleaned_text += '\n'.join(question_lines)

        logger.info(f"Cleaned Ollama response: {cleaned_text[:500]}...")
        if not cleaned_text.startswith("1."):
            logger.error(f"Unexpected cleaned quiz format: {cleaned_text}")
            raise ValueError(f"Unexpected cleaned response format: {cleaned_text}")

        quiz_data = []
        lines = cleaned_text.strip().split('\n')
        current_question = None
        current_options = []
        current_correct = None
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if re.match(r'^\d+\.\s', line):
                if current_question and len(current_options) == 4 and current_correct:
                    quiz_data.append({
                        "question": current_question,
                        "options": current_options,
                        "correct_answer": current_correct
                    })
                current_question = re.sub(r'^\d+\.\s*', '', line)
                current_options = []
                current_correct = None
                continue
            if re.match(r'^[A-D]\)', line):
                option_text = line[2:].strip()
                if option_text and len(current_options) < 4:
                    current_options.append(option_text)
                continue
            if line.startswith("Correct:"):
                correct_letter = line[len("Correct:"):].strip()
                if correct_letter in 'ABCD' and len(current_options) == 4:
                    correct_index = ord(correct_letter) - ord('A')
                    current_correct = current_options[correct_index]
                continue
        if current_question and len(current_options) == 4 and current_correct:
            quiz_data.append({
                "question": current_question,
                "options": current_options,
                "correct_answer": current_correct
            })
            logger.info(f"Parsed question: {current_question[:100]}")

        if len(quiz_data) < 5:
            logger.error(f"Expected 5 questions, got {len(quiz_data)}")
            if quiz_data:
                for item in quiz_data:
                    Quiz.objects.create(
                        user_id=user_id,
                        lecture=lecture_name,
                        question=item["question"],
                        options=item["options"],
                        correct_answer=item["correct_answer"]
                    )
                logger.info(f"Saved partial quiz with {len(quiz_data)} questions")
            raise ValueError(f"Expected 5 questions, got {len(quiz_data)}")

        quiz_ids = []
        for item in quiz_data:
            quiz = Quiz.objects.create(
                user_id=user_id,
                lecture=lecture_name,
                question=item["question"],
                options=item["options"],
                correct_answer=item["correct_answer"]
            )
            quiz_ids.append(quiz.id)

        ChatHistory.objects.create(
            user_id=user_id,
            lecture=lecture_name,
            quiz_id=Quiz.objects.get(id=quiz_ids[0])
        )
        logger.info(f"Generated and saved quiz for user {user_id}, lecture {lecture_name}")
        cache.delete(f"chat_history:{user_id}:{lecture_name}")
        return {"status": "success", "lecture": lecture_name, "question_count": len(quiz_data)}
    except requests.RequestException as e:
        logger.error(f"Ollama API timeout or connection error: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Quiz generation failed: {str(e)}")
        return {"status": "error", "error": str(e)}

def split_text_into_chunks(text, chunk_size=2000):
    chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
    logger.info(f"Text split into {len(chunks)} chunks")
    return chunks

def process_with_gemma(chunk, model_name='gemma3:1b'):
    prompt = f"""
    Summarize the following text in 50-100 words, focusing only on core technical concepts for a computer science lecture. Start with "The key concept is…" and use a concise tone. Exclude examples, anecdotes, non-technical details, introductions, or explanations. Output ONLY the summary text starting with "The key concept is…":

    {chunk}
    """
    try:
        response = requests.post(
            "http://ollama:11434/api/generate",
            json={"model": model_name, "prompt": prompt, "stream": False},
            timeout=60
        )
        response.raise_for_status()
        ollama_data = response.json()
        chunk_text = ollama_data.get("response", "")
        logger.info(f"Gemma response received for chunk: {chunk_text[:100]}...")
        if not chunk_text:
            logger.error("Empty response from Ollama for chunk")
            raise ValueError("Empty response from Ollama")
        return chunk_text
    except requests.RequestException as e:
        logger.error(f"Ollama API timeout or connection error for chunk: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Error processing chunk with Gemma: {str(e)}")
        return f"Error processing chunk: {str(e)}"

def finalize_transcript(chunks_results):
    combined = "\n".join(chunks_results)
    final_prompt = f"""
    Combine the following summaries into a single summary for a computer science lecture. Start with "The key concepts are…" and use a concise tone. Focus only on core technical concepts, keeping the length 200-300 words. Exclude examples, anecdotes, non-technical details, introductions, or explanations. Output ONLY the summary text starting with "The key concepts are…":

    {combined}
    """
    try:
        response = requests.post(
            "http://ollama:11434/api/generate",
            json={"model": "gemma3:1b", "prompt": final_prompt, "stream": False},
            timeout=60
        )
        response.raise_for_status()
        ollama_data = response.json()
        final_text = ollama_data.get("response", "")
        logger.info(f"Final summary generated: {final_text[:100]}...")
        if not final_text:
            logger.error("Empty response from Ollama for final summary")
            raise ValueError("Empty response from Ollama")
        return final_text
    except requests.RequestException as e:
        logger.error(f"Ollama API timeout or connection error for final summary: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Error finalizing summary: {str(e)}")
        return f"Error in final summary: {str(e)}"

@shared_task
def generate_transcript(user, lecture, pdf_file):
    logger.info(f"Starting summary generation for user {user}, lecture {lecture}, file {pdf_file}")
    try:
        # PDF'den metni çıkar
        transcript_text = process_lecture_pdf(pdf_file)
        if not transcript_text:
            logger.error("No text extracted from PDF")
            return {'status': 'error', 'message': 'No text extracted from PDF'}

        # Metni chunk'lara böl
        chunks = split_text_into_chunks(transcript_text, chunk_size=2000)

        # Her chunk için özet üret
        results = []
        for i, chunk in enumerate(chunks):
            logger.info(f"Processing chunk {i+1}/{len(chunks)}")
            result = process_with_gemma(chunk, model_name='gemma3:1b')
            results.append(result)

        # Nihai özeti birleştir
        final_summary = finalize_transcript(results)

        # Özeti temizle
        cleaned_text = " ".join(final_summary.strip().split())
        logger.info(f"Cleaned summary: {cleaned_text[:500]}...")

        # Özeti veritabanına kaydet
        user = User.objects.get(id=user)
        # pdf_file'ı FileField için uygun hale getir
        pdf_file_name = os.path.basename(pdf_file) if isinstance(pdf_file, str) else pdf_file.name
        transcript = Transcript.objects.create(
            user=user,
            lecture=lecture,
            transcript_text=cleaned_text,
            pdf_file=pdf_file
        )
        logger.info(f"Summary saved with ID {transcript.id}")

        return {
            'status': 'success',
            'transcript_id': transcript.id,
            'lecture': lecture,
            'transcript_text': cleaned_text
        }
    except requests.RequestException as e:
        logger.error(f"Ollama API timeout or connection error: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Summary generation failed: {str(e)}")
        return {'status': 'error', 'message': str(e)}