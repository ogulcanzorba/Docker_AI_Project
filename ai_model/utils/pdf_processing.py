import PyPDF2
import os
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


def process_lecture_pdf(pdf_file_path):
    try:
        with open(pdf_file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            transcript_text = ""
            for page in pdf_reader.pages:
                text = page.extract_text()
                if text:
                    transcript_text += text + "\n"

            if not transcript_text.strip():
                logger.warning("No text extracted from PDF")
                return None

            # Add text processing from the notebook (e.g., cleaning, summarization)
            transcript_text = transcript_text.replace('\n', ' ').strip()
            return transcript_text
    except Exception as e:
        logger.error(f"PDF processing error: {str(e)}")
        return None