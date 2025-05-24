from celery import shared_task
from django.core.cache import cache
from django.contrib.auth.models import User
from .models import ChatHistory, Quiz, Transcript
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import re
import logging
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from .utils.pdf_processing import process_lecture_pdf
logger = logging.getLogger(__name__)

@shared_task
def generate_quiz(user_id, lecture_name, lecture_prompt_path):
    logger.info(f"Starting quiz generation for user {user_id}, lecture {lecture_name}")
    try:
        try:
            with open(lecture_prompt_path, "r") as f:
                base_prompt = f.read().strip()
            if not base_prompt:
                raise ValueError("Prompt file is empty")
        except (FileNotFoundError, ValueError) as e:
            base_prompt = f"You are a helpful CS tutor specializing in {lecture_name.replace('_', ' ').title()}."
            logger.error(f"Prompt error for {lecture_prompt_path}: {str(e)}")

        chat_history = ChatHistory.objects.filter(user_id=user_id, lecture=lecture_name).order_by('created_at')
        if not chat_history.exists():
            logger.error("No chat history available")
            return {"status": "error", "error": "No chat history available"}

        conversation = ""
        for msg in chat_history:
            if msg.user_input:
                conversation += f"User: {msg.user_input.strip()}\n"
            if msg.bot_response:
                conversation += f"Bot: {msg.bot_response.strip()}\n"
        logger.info(f"Using {len(chat_history)} chat history messages for quiz")

        prompt = (
            f"{base_prompt}\n\n"
            f"You are creating a quiz for the topic: \"{lecture_name.replace('_', ' ').title()}\".\n"
            "Based on the following conversation history, generate exactly 5 multiple-choice questions. "
            "Each question must have 4 options and one correct answer, in this strict format:\n\n"
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
            "Instructions:\n"
            "- Include content from all user questions and bot responses, including explanations of uploaded documents (e.g., OS_Report).\n"
            "- Do NOT include introductions, explanations, or summaries.\n"
            "- Do NOT use markdown, JSON, emojis, or extra text outside the format.\n"
            "- Ensure all 5 questions are numbered 1 to 5, each with exactly 4 options and one Correct line.\n\n"
            "Example Output:\n"
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
        )

        response = requests.post(
            "http://ollama:11434/api/generate",
            json={"model": "gemma3:1b", "prompt": prompt, "stream": False},
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
            logger.error(f"Unexpected cleaned quiz format: {cleaned_text[:500]}...")
            raise ValueError(f"Unexpected cleaned response format")

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

        for item in quiz_data:
            Quiz.objects.create(
                user_id=user_id,
                lecture=lecture_name,
                question=item["question"],
                options=item["options"],
                correct_answer=item["correct_answer"]
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

@shared_task
def generate_transcript(user_id, lecture, pdf_base64, pdf_hash, pdf_filename=None):
    logger.info(f"Starting summary generation for user {user_id}, lecture {lecture}")
    try:
        cache_key = f"transcript:{user_id}:{lecture}:{pdf_hash}"
        cached_data = cache.get(cache_key)
        if cached_data:
            logger.info("Returning cached summary")
            user_obj = User.objects.get(id=user_id)
            transcript = Transcript.objects.create(
                user=user_obj,
                lecture=lecture,
                title=cached_data['title'],
                transcript_text=cached_data['transcript_text']
            )
            return {
                'status': 'success',
                'transcript_id': transcript.id,
                'lecture': lecture,
                'transcript_text': cached_data['transcript_text']
            }

        pdf_bytes = base64.b64decode(pdf_base64)

        try:
            transcript_text = process_lecture_pdf(pdf_bytes, is_bytes=True)
        except ValueError as e:
            logger.error(f"Text extraction failed: {str(e)}")
            return {'status': 'error', 'message': str(e)}

        chunk_size = 2000
        chunks = [transcript_text[i:i + chunk_size] for i in range(0, len(transcript_text), chunk_size)]

        results = []
        with ThreadPoolExecutor(max_workers=6) as executor:
            future_to_chunk = {executor.submit(process_with_gemma, chunk): chunk for chunk in chunks}
            for future in as_completed(future_to_chunk):
                try:
                    result = future.result()
                    if result and "Error:" not in result:
                        results.append(result)
                except Exception as e:
                    logger.error(f"Chunk processing failed: {str(e)}")

        final_summary = "\n".join(results)
        if not final_summary:
            logger.error("No valid summary generated")
            return {'status': 'error', 'message': 'Failed to generate summary.'}

        cleaned_text = " ".join(list(dict.fromkeys(final_summary.strip().split())))

        user_obj = User.objects.get(id=user_id)
        base_title = pdf_filename
        title = base_title
        suffix = 1
        while Transcript.objects.filter(user=user_obj, lecture=lecture, title=title).exists():
            title = f"{base_title}_{suffix}"
            suffix += 1

        transcript = Transcript.objects.create(
            user=user_obj,
            lecture=lecture,
            title=title,
            transcript_text=cleaned_text
        )
        logger.info(f"Summary saved with ID {transcript.id}")

        cache_data = {'title': title, 'transcript_text': cleaned_text}
        cache.set(cache_key, cache_data, timeout=86400)
        logger.info(f"Cached summary: {cache_key}")

        return {
            'status': 'success',
            'transcript_id': transcript.id,
            'lecture': lecture,
            'transcript_text': cleaned_text
        }

    except requests.RequestException as e:
        logger.error(f"Ollama API timeout or connection error: {str(e)}")
        return {'status': 'error', 'message': str(e)}
    except Exception as e:
        logger.error(f"Summary generation failed: {str(e)}")
        return {'status': 'error', 'message': str(e)}

def process_with_gemma(chunk, model_name='gemma3:1b'):
    prompt = f"Summarize the technical content in 75-100 words, focusing on core concepts. Use clear, natural language without introductory phrases, task references, or repetitive wording.\n{chunk}"
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    session.mount('http://', HTTPAdapter(max_retries=retries))
    try:
        response = session.post(
            "http://ollama:11434/api/generate",
            json={
                "model": model_name,
            "prompt": prompt,
                "stream": False,
                "num_ctx": 1024,
                "num_predict": 120
            },
            timeout=60
        )
        response.raise_for_status()
        result = response.json().get("response", "")
        return result.strip() if result else "Error: Empty response"
    except requests.RequestException as e:
        logger.error(f"Ollama API error: {str(e)}")
        return f"Error: {str(e)}"