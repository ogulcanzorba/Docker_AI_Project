import PyPDF2
import logging

logger = logging.getLogger(__name__)

def process_lecture_pdf(pdf_file_path):
    try:
        with open(pdf_file_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            text = ""
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            if text.strip():
                logger.info(f"Extracted text from PDF: {text[:100]}...")
                return text
            else:
                logger.error("No text extracted from PDF")
                return None
    except Exception as e:
        logger.error(f"PDF processing error: {str(e)}")
        return None