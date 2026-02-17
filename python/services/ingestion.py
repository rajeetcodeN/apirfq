
import pdfplumber  # Superior table extraction
import logging
import io
import pandas as pd
from docx import Document
from typing import Dict, Any, List
from tabulate import tabulate

from services.ocr import perform_mistral_ocr

logger = logging.getLogger(__name__)

class InsufficientTextError(Exception):
    """Raised when PDF text layer is missing or too sparse."""
    pass

def ingest_pdf_native(file_bytes: bytes) -> tuple[str, List[Dict[str, Any]]]:
    """
    Extracts text AND structured tables natively from a PDF file using pdfplumber.
    Returns: (full_text, list_of_markdown_tables)
    """
    try:
        full_text = ""
        structured_tables = []
        
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for i, page in enumerate(pdf.pages):
                # 1. Extract Text (layout=True preserves visual spacing)
                text = page.extract_text(layout=True) or ""
                full_text += f"--- Page {i + 1} ---\n{text}\n\n"
                
                # 2. Extract Tables (Strict Structure)
                # settings={"vertical_strategy": "lines", "horizontal_strategy": "lines"} # strict grid
                # Just use default for broad compatibility first
                tables = page.extract_tables()
                
                for table in tables:
                    if not table: continue
                    # Clean None values to empty strings
                    cleaned_table = [[cell or "" for cell in row] for row in table]
                    
                    # Convert to Markdown using tabulate
                    # We assume first row is header if it looks header-ish, otherwise just grid
                    try:
                        md = tabulate(cleaned_table, headers="firstrow", tablefmt="github")
                        structured_tables.append({
                            "markdown": md,
                            "page": i + 1,
                            "rows": len(cleaned_table)
                        })
                    except Exception as e:
                        logger.warning(f"Failed to tabulate table on page {i+1}: {e}")

        trimmed_text = full_text.strip()
        return trimmed_text, structured_tables
        
    except Exception as e:
        logger.error(f"Native PDF extraction failed: {e}")
        return "", []  # Return empty on failure


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
            # STRATEGY: Mistral OCR ALWAYS (Primary). Native Text (Secondary/Backup).
            # User reverted "Native First" due to accuracy issues.
            
            # 1. Native Extraction (pdfplumber) - Returns (text, tables)
            # We still keep this for the Validator (regex check on native text)
            try:
                native_text, native_tables = ingest_pdf_native(file_bytes)
            except Exception as e:
                logger.warning(f"Native extraction failed: {e}")
                native_text, native_tables = "", []

            # 2. Mistral OCR (Primary)
            # Always run OCR to ensure layout perfection and table accuracy
            logger.info("Running Mistral OCR (Primary Strategy)...")
            ocr_result = perform_mistral_ocr(file_bytes, filename)
            
            # ocr_result is now a dict: {text, tables, page_count}
            ocr_text = ocr_result["text"] if isinstance(ocr_result, dict) else ocr_result
            ocr_tables = ocr_result.get("tables", []) if isinstance(ocr_result, dict) else []

            # FALLBACK: If OCR misses tables, use Native Tables (pdfplumber)
            if not ocr_tables and native_tables:
                logger.info(f"Mistral OCR found no tables. Falling back to {len(native_tables)} native tables.")
                ocr_tables = native_tables
            
            return {
                "source": "hybrid_pdf",
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
