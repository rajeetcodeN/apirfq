
import os
import requests
import logging
import json
from typing import Optional

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

def call_ocr_api(document_url: str) -> str:
    """Step 3: Call OCR endpoint"""
    logger.info("Mistral OCR: Processing document...")
    
    headers = {
        "Authorization": f"Bearer {get_api_key()}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "mistral-ocr-latest",
        "document": {
            "document_url": document_url
        },
        "include_image_base64": False
    }
    
    response = requests.post(f"{MISTRAL_API_BASE}/ocr", headers=headers, json=payload)
    
    if not response.ok:
        raise Exception(f"Mistral OCR failed: {response.status_code} - {response.text}")
        
    result = response.json()
    
    # Combine pages
    pages = result.get("pages", [])
    extracted_text = "\n\n".join([f"--- Page {p['index'] + 1} ---\n{p['markdown']}" for p in pages])
    
    logger.info(f"Mistral OCR: Processed {len(pages)} pages.")
    return extracted_text

def delete_from_mistral(file_id: str):
    """Step 4: Cleanup (GDPR)"""
    logger.info("Mistral OCR: Deleting file from storage...")
    try:
        headers = {"Authorization": f"Bearer {get_api_key()}"}
        requests.delete(f"{MISTRAL_API_BASE}/files/{file_id}", headers=headers)
    except Exception as e:
        logger.warning(f"Mistral OCR: File deletion failed: {e}")

def perform_mistral_ocr(file_bytes: bytes, filename: str = "document") -> str:
    """Orchestrate the full OCR flow"""
    file_id = None
    try:
        # 1. Upload
        file_id = upload_to_mistral(file_bytes, filename)
        
        # 2. Get URL
        signed_url = get_signed_url(file_id)
        
        # 3. OCR
        text = call_ocr_api(signed_url)
        return text
        
    except Exception as e:
        logger.error(f"Mistral OCR failed: {e}")
        return f"[OCR ERROR: {str(e)}]"
        
    finally:
        # 4. Cleanup
        if file_id:
            delete_from_mistral(file_id)
