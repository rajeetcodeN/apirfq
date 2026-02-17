
import pdfplumber  # Superior table extraction
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
    """Extracts text natively from a PDF file using pdfplumber."""
    try:
        full_text = ""
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for i, page in enumerate(pdf.pages):
                # extract_text(layout=True) is key for preserving table structure
                text = page.extract_text(layout=True) or ""
                full_text += f"--- Page {i + 1} ---\n{text}\n\n"
        
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
            # STRATEGY: Native Extraction FIRST (Fast, Accurate). Fallback to OCR if scanned (slow).
            
            # 1. Native Extraction (pdfplumber)
            native_text = ingest_pdf_native(file_bytes)
            
            # Check if text is sufficient (not scanned/image)
            # Threshold: < 50 chars total usually means scanned image or empty
            if len(native_text) > 100:
                logger.info("Native PDF text detected. Skipping OCR.")
                return {
                    "source": "hybrid_pdf", # Use hybrid_pdf so main.py processes it correctly
                    "native_text": native_text,
                    "ocr_text": native_text, # Use native as primary
                    "ocr_tables": [], 
                    "mime_type": mime_type
                }
            
            # 2. Mistral OCR Fallback (Slow, Layout-Perfect)
            logger.info("Insufficient native text detected. Falling back to Mistral OCR...")
            ocr_result = perform_mistral_ocr(file_bytes, filename)
            
            # ocr_result is now a dict: {text, tables, page_count}
            ocr_text = ocr_result["text"] if isinstance(ocr_result, dict) else ocr_result
            ocr_tables = ocr_result.get("tables", []) if isinstance(ocr_result, dict) else []
            
            return {
                "source": "hybrid_pdf", # Use hybrid_pdf
                "native_text": native_text, 
                "ocr_text": ocr_text,
                "ocr_tables": ocr_tables,
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
            ocr_result = perform_mistral_ocr(file_bytes, filename)
            text = ocr_result["text"] if isinstance(ocr_result, dict) else ocr_result
            tables = ocr_result.get("tables", []) if isinstance(ocr_result, dict) else []
            return {"raw_data": text, "ocr_tables": tables, "source": "mistral_ocr", "mime_type": mime_type}

        raise ValueError(f"Unsupported file type: {extension}")

    except Exception as e:
        logger.error(f"Ingestion routing failed: {e}")
        raise e
