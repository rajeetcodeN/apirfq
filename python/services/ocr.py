
import os
import requests
import logging
import json
from typing import Optional, Dict

logger = logging.getLogger(__name__)

MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
MISTRAL_API_BASE = "https://api.mistral.ai/v1"

def get_api_key():
    if not MISTRAL_API_KEY:
        raise ValueError("MISTRAL_API_KEY not configured")
    return MISTRAL_API_KEY

def upload_to_mistral(file_bytes: bytes, filename: str = "document.pdf") -> str:
    """Step 1: Upload file to Mistral"""
    logger.info("Mistral OCR: Uploading file...")
    
    headers = {"Authorization": f"Bearer {get_api_key()}"}
    files = {
        "file": (filename, file_bytes),
        "purpose": (None, "ocr")
    }
    
    response = requests.post(f"{MISTRAL_API_BASE}/files", headers=headers, files=files)
    
    if not response.ok:
        raise Exception(f"Mistral upload failed: {response.status_code} - {response.text}")
        
    result = response.json()
    return result["id"]

def get_signed_url(file_id: str) -> str:
    """Step 2: Get signed URL"""
    logger.info("Mistral OCR: Getting signed URL...")
    
    headers = {"Authorization": f"Bearer {get_api_key()}"}
    response = requests.get(f"{MISTRAL_API_BASE}/files/{file_id}/url?expiry=1", headers=headers)
    
    if not response.ok:
        raise Exception(f"Mistral signed URL failed: {response.status_code} - {response.text}")
        
    result = response.json()
    return result["url"]

def call_ocr_api(document_url: str) -> Dict:
    """Step 3: Call OCR endpoint with table_format=markdown for structured tables"""
    logger.info("Mistral OCR: Processing document with table extraction...")
    
    headers = {
        "Authorization": f"Bearer {get_api_key()}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "mistral-ocr-latest",
        "document": {
            "document_url": document_url
        },
        "table_format": "markdown",
        "include_image_base64": False
    }
    
    response = requests.post(f"{MISTRAL_API_BASE}/ocr", headers=headers, json=payload)
    
    if not response.ok:
        raise Exception(f"Mistral OCR failed: {response.status_code} - {response.text}")
        
    result = response.json()
    
    pages = result.get("pages", [])
    
    # Extract main text from all pages
    extracted_text = "\n\n".join([f"--- Page {p['index'] + 1} ---\n{p['markdown']}" for p in pages])
    
    # Extract tables separately (these are clean markdown tables with proper columns)
    all_tables = []
    for page in pages:
        page_tables = page.get("tables", [])
        for t in page_tables:
            table_content = t.get("markdown", t.get("content", ""))
            if table_content:
                all_tables.append({
                    "page": page["index"] + 1,
                    "markdown": table_content
                })
    
    if all_tables:
        logger.info(f"Mistral OCR: Found {len(all_tables)} structured tables across {len(pages)} pages.")
    else:
        logger.info(f"Mistral OCR: No structured tables found. Processed {len(pages)} pages.")
    
    return {
        "text": extracted_text,
        "tables": all_tables,
        "page_count": len(pages)
    }

def delete_from_mistral(file_id: str):
    """Step 4: Cleanup (GDPR)"""
    logger.info("Mistral OCR: Deleting file from storage...")
    try:
        headers = {"Authorization": f"Bearer {get_api_key()}"}
        requests.delete(f"{MISTRAL_API_BASE}/files/{file_id}", headers=headers)
    except Exception as e:
        logger.warning(f"Mistral OCR: File deletion failed: {e}")

def perform_mistral_ocr(file_bytes: bytes, filename: str = "document") -> Dict:
    """Orchestrate the full OCR flow. Returns dict with text, tables, page_count."""
    file_id = None
    try:
        # 1. Upload
        file_id = upload_to_mistral(file_bytes, filename)
        
        # 2. Get URL
        signed_url = get_signed_url(file_id)
        
        # 3. OCR with table extraction
        ocr_result = call_ocr_api(signed_url)
        return ocr_result
        
    except Exception as e:
        logger.error(f"Mistral OCR failed: {e}")
        return {
            "text": f"[OCR ERROR: {str(e)}]",
            "tables": [],
            "page_count": 0
        }
        
    finally:
        # 4. Cleanup
        if file_id:
            delete_from_mistral(file_id)
