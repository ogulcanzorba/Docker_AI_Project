import logging
from io import BytesIO
import pdfplumber

logger = logging.getLogger(__name__)

def process_lecture_pdf(pdf_data, is_bytes=False):
    try:
        text = ""
        if is_bytes:
            pdf_file = BytesIO(pdf_data)
        else:
            pdf_file = pdf_data

        with pdfplumber.open(pdf_file) as pdf:
            max_pages = min(len(pdf.pages), 7)
            for page in pdf.pages[:max_pages]:
                page_text = page.extract_text() or ""
                if page_text:
                    text += page_text + "\n"

        if is_bytes:
            pdf_file.close()

        if not text.strip():
            logger.warning("Extracted text is empty")
            raise ValueError("No readable text found in PDF. The document may be scanned or image-based, requiring OCR.")

        logger.info(f"Extracted text length: {len(text)}")
        return text.strip()
    except Exception as e:
        logger.error(f"Error extracting text from PDF: {str(e)}")
        if is_bytes and 'pdf_file' in locals():
            pdf_file.close()
        raise