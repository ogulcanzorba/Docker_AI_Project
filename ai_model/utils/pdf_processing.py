import PyPDF2
import os
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


def process_lecture_pdf(pdf_file_path):
    logger.info(f"Processing PDF: {pdf_file_path}, size: {os.path.getsize(pdf_file_path)} bytes")
    try:
        with open(pdf_file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            transcript_text = ""
            max_pages = 50
            for i, page in enumerate(pdf_reader.pages[:max_pages]):
                logger.info(f"Processing page {i+1}/{min(len(pdf_reader.pages), max_pages)}")
                text = page.extract_text()
                if text:
                    transcript_text += text + "\n"
            if not transcript_text.strip():
                logger.warning("No text extracted from PDF")
                return None
            transcript_text = transcript_text.replace('\n', ' ').strip()
            logger.info(f"Extracted text: {transcript_text[:100]}...")
            return transcript_text
    except Exception as e:
        logger.error(f"PDF processing error: {str(e)}")
        raise