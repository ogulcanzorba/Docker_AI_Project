
import logging
import pdfplumber
from PyPDF2 import PdfReader

logger = logging.getLogger(__name__)

def process_lecture_pdf(pdf_file_path):
    """
    Extracts text from a PDF file, ignoring images and focusing on textual content.
    Limits extraction to the first 2 pages for performance.
    """
    try:
        text = ""
        with pdfplumber.open(pdf_file_path) as pdf:
            max_pages = min(len(pdf.pages), 7)
            for page in pdf.pages[:max_pages]:
                page_text = page.extract_text() or ""
                if page_text:
                    text += page_text + "\n"
        logger.info(f"Extracted {len(text)} characters from PDF")
        return text.strip()
    except Exception as e:
        logger.error(f"Error processing PDF: {str(e)}")
        return ""
