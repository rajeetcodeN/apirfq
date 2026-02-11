
import fitz  # PyMuPDF
import logging
import io
import pandas as pd
from docx import Document
from typing import Dict, Any

from services.ocr import perform_mistral_ocr

logger = logging.getLogger(__name__)

class InsufficientTextError(Exception):
    """Raised when PDF text layer is missing or too sparse."""
    pass

def ingest_pdf_native(file_bytes: bytes) -> str:
    """Extracts text natively from a PDF file using PyMuPDF."""
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        full_text = ""
        for page_num, page in enumerate(doc):
            text = page.get_text()
            full_text += f"--- Page {page_num + 1} ---\n{text}\n\n"
        doc.close()
        
        trimmed_text = full_text.strip()
        return trimmed_text
    except Exception as e:
        logger.error(f"Native PDF extraction failed: {e}")
        return ""  # Return empty string on failure, don't raise


def ingest_excel(file_bytes: bytes) -> str:
    """Converts Excel sheets to Markdown tables using Pandas."""
    try:
        dfs = pd.read_excel(io.BytesIO(file_bytes), sheet_name=None)
        output = []
        for sheet_name, df in dfs.items():
            markdown_table = df.to_markdown(index=False)
            output.append(f"## Sheet: {sheet_name}\n\n{markdown_table}")
        return "\n\n".join(output)
    except Exception as e:
        logger.error(f"Excel extraction failed: {e}")
        raise ValueError(f"Excel parsing error: {e}")

def ingest_docx(file_bytes: bytes) -> str:
    """Extracts text from Word documents."""
    try:
        doc = Document(io.BytesIO(file_bytes))
        return "\n".join([para.text for para in doc.paragraphs])
    except Exception as e:
        logger.error(f"Docx extraction failed: {e}")
        raise ValueError(f"Word parsing error: {e}")

async def route_ingestion(file_bytes: bytes, mime_type: str, filename: str) -> Dict[str, Any]:
    """Routes ingestion based on file type."""
    extension = filename.split('.')[-1].lower() if '.' in filename else ''
    
    logger.info(f"Ingesting file: {filename} ({mime_type})")

    try:
        # 1. PDF
        if mime_type == 'application/pdf' or extension == 'pdf':
            # Dual Extraction Strategy for Hybrid Accuracy
            
            # 1. Native Extraction (Fast, Character-Perfect)
            native_text = ingest_pdf_native(file_bytes)
            
            # 2. Mistral OCR (Slow, Layout-Perfect)
            # We enforce OCR now to ensure optimal AI comprehension of tables
            ocr_text = perform_mistral_ocr(file_bytes, filename)
            
            return {
                "source": "hybrid_pdf",
                "native_text": native_text,
                "ocr_text": ocr_text,
                "mime_type": mime_type
            }

        # 2. Excel
        if extension in ['xlsx', 'xls'] or 'sheet' in mime_type:
            text = ingest_excel(file_bytes)
            return {"raw_data": text, "source": "native_excel", "mime_type": mime_type}

        # 3. Word
        if extension in ['docx'] or 'word' in mime_type:
            text = ingest_docx(file_bytes)
            return {"raw_data": text, "source": "native_docx", "mime_type": mime_type}

        # 4. Text / CSV
        if extension in ['txt', 'csv'] or mime_type.startswith('text/'):
            text = file_bytes.decode('utf-8', errors='ignore')
            return {"raw_data": text, "source": "native_text", "mime_type": mime_type}

        # 5. Images (JPG, PNG, TIFF) - Use Mistral OCR directly
        if mime_type.startswith('image/') or extension in ['jpg', 'jpeg', 'png', 'tiff', 'tif', 'bmp']:
            text = perform_mistral_ocr(file_bytes, filename)
            return {"raw_data": text, "source": "mistral_ocr", "mime_type": mime_type}

        raise ValueError(f"Unsupported file type: {extension}")

    except Exception as e:
        logger.error(f"Ingestion routing failed: {e}")
        raise e
