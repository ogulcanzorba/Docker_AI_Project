import PyPDF2
import logging
from PyPDF2 import PdfReader

logger = logging.getLogger(__name__)

def process_lecture_pdf(pdf_file_path):
    try:
        reader = PdfReader(pdf_file_path)
        text = ""
        max_pages = min(len(reader.pages), 7)
        for page in reader.pages[:max_pages]:
            page_text = page.extract_text() or ""
            text += page_text + "\n"
        logger.info(f"Extracted {len(text)} characters from PDF")
        return text.strip()
    except Exception as e:
        logger.error(f"Error processing PDF: {str(e)}")
        return ""


