
import os
import logging
import uvicorn
from fastapi import FastAPI, File, UploadFile, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from typing import Dict, Any, Optional
from pydantic import BaseModel

# Load env - check current dir first (Docker), then parent dir (local dev)
import pathlib
env_path = pathlib.Path(".env.local")
if not env_path.exists():
    env_path = pathlib.Path("../.env.local")
load_dotenv(dotenv_path=str(env_path))

from services.ingestion import route_ingestion
from services.masking import process_document
from services.ai import extract_data_from_text
from services.audit import audit_service
from services.correction_service import CorrectionService

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("rfq-backend")

app = FastAPI(title="RFQ Intelligence Backend", version="1.0.0")

# Instantiate Services
correction_service = CorrectionService()

# Models
class CorrectionRequest(BaseModel):
    raw_text_snippet: str
    correct_json: Dict[str, Any]
    full_text_context: str = ""

class ReExtractionRequest(BaseModel):
    raw_text: str
    user_feedback: str
    native_text: Optional[str] = None

# CORS (Allow everything for dev)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "https://apirfq.onrender.com"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def health_check():
    """Basic health check for UptimeRobot pings - fast response"""
    return {"status": "ok", "service": "rfq-intelligence-python-backend"}

@app.get("/health")
def detailed_health_check():
    """
    Comprehensive health check that verifies all critical components.
    Use this for debugging and monitoring dashboards.
    """
    health_status = {
        "status": "healthy",
        "service": "rfq-intelligence-python-backend",
        "version": "1.0.0",
        "checks": {}
    }
    
    all_healthy = True
    
    # 1. Check Mistral API Key
    mistral_key = os.getenv("MISTRAL_API_KEY")
    if mistral_key and len(mistral_key) > 10:
        health_status["checks"]["mistral_api_key"] = {"status": "ok", "message": "API key configured"}
    else:
        health_status["checks"]["mistral_api_key"] = {"status": "error", "message": "API key missing or invalid"}
        all_healthy = False
    
    # 2. Check Spacy/Presidio NLP Engine
    try:
        from services.masking import get_masker
        masker = get_masker()
        if masker.nlp_available:
            health_status["checks"]["nlp_engine"] = {"status": "ok", "message": "Spacy German model loaded"}
        else:
            health_status["checks"]["nlp_engine"] = {"status": "warning", "message": "Running in regex-only mode (Spacy not loaded)"}
    except Exception as e:
        health_status["checks"]["nlp_engine"] = {"status": "error", "message": str(e)}
        all_healthy = False
    
    # 3. Check Audit Logging
    try:
        from services.audit import audit_service
        health_status["checks"]["audit_logging"] = {"status": "ok", "message": "Audit service ready"}
    except Exception as e:
        health_status["checks"]["audit_logging"] = {"status": "error", "message": str(e)}
        all_healthy = False
    
    # 4. Check OCR Service Import
    try:
        from services.ocr import perform_mistral_ocr
        health_status["checks"]["ocr_service"] = {"status": "ok", "message": "Mistral OCR service ready"}
    except Exception as e:
        health_status["checks"]["ocr_service"] = {"status": "error", "message": str(e)}
        all_healthy = False
    
    # 5. Check Ingestion Service
    try:
        from services.ingestion import route_ingestion
        health_status["checks"]["ingestion_service"] = {"status": "ok", "message": "Ingestion router ready"}
    except Exception as e:
        health_status["checks"]["ingestion_service"] = {"status": "error", "message": str(e)}
        all_healthy = False
    
    # 6. Check AI Service
    try:
        from services.ai import extract_data_from_text
        health_status["checks"]["ai_service"] = {"status": "ok", "message": "AI extraction service ready"}
    except Exception as e:
        health_status["checks"]["ai_service"] = {"status": "error", "message": str(e)}
        all_healthy = False
    
    # Set overall status
    if not all_healthy:
        health_status["status"] = "degraded"
    
    return health_status

@app.post("/process")
async def process_file(file: UploadFile = File(...)):
    """
    Main pipeline endpoint:
    1. Ingestion (Native/OCR)
    2. Header Extraction
    3. PII Masking
    4. AI Extraction
    5. Merge & Return
    """
    logger.info(f"Processing file: {file.filename} ({file.content_type})")
    
    try:
        # Read file bytes
        file_bytes = await file.read()
        
        # 1. Ingestion
        try:
            audit_service.log_event("INGESTION_START", file.filename, "STARTED", {"size_bytes": len(file_bytes), "mime_type": file.content_type})
            
            ingestion_result = await route_ingestion(file_bytes, file.content_type, file.filename)
            source = ingestion_result["source"]
            
            # Handle Hybrid PDF logic
            if source == "hybrid_pdf":
                raw_text = ingestion_result["ocr_text"]   # Primary for AI/Masking
                native_text = ingestion_result["native_text"] # Secondary for Validator
                ocr_tables = ingestion_result.get("ocr_tables", [])
            else:
                raw_text = ingestion_result["raw_data"]
                native_text = None
                ocr_tables = ingestion_result.get("ocr_tables", [])

            # If structured tables were extracted, append them to the text
            # This gives the AI clean, column-labeled data to work with
            if ocr_tables:
                table_section = "\n\n=== STRUCTURED TABLES (extracted by OCR) ===\n"
                for i, tbl in enumerate(ocr_tables):
                    table_section += f"\n--- Table {i+1} (Page {tbl.get('page', '?')}) ---\n"
                    table_section += tbl["markdown"] + "\n"
                raw_text += table_section
                logger.info(f"Appended {len(ocr_tables)} structured tables to raw text")

            logger.info(f"Ingestion complete. Source: {source}, Length: {len(raw_text)}")
            
            audit_service.log_event("INGESTION_COMPLETE", file.filename, "SUCCESS", {"source": source, "extracted_chars": len(raw_text)})
        except Exception as e:
            logger.error(f"Ingestion failed: {e}")
            audit_service.log_event("INGESTION_FAILED", file.filename, "FAILURE", {"error": str(e)})
            raise HTTPException(status_code=400, detail=f"Ingestion failed: {str(e)}")

        # 2. Masking & Header Extraction
        try:
            masking_result = process_document(raw_text)
            header = masking_result["header"]
            masked_text = masking_result["masked_text"]
            token_map = masking_result["token_map"]
            logger.info(f"Masking complete. Header: {header['rfq_number']}")
            
            # Log PII Stats
            audit_service.log_pii_masking(file.filename, token_map)
            
        except Exception as e:
            logger.error(f"Masking failed: {e}")
            audit_service.log_event("MASKING_FAILED", file.filename, "FAILURE", {"error": str(e)})
            raise HTTPException(status_code=500, detail=f"Masking failed: {str(e)}")

        # 3. AI Extraction
        try:
            audit_service.log_event("AI_PROCESSING_START", file.filename, "STARTED")
            ai_data = extract_data_from_text(masked_text, native_text=native_text)
            logger.info("AI extraction successful.")
            audit_service.log_event("AI_PROCESSING_COMPLETE", file.filename, "SUCCESS")
        except Exception as e:
            logger.error(f"AI Extraction failed: {e}")
            audit_service.log_event("AI_PROCESSING_FAILED", file.filename, "FAILURE", {"error": str(e)})
            raise HTTPException(status_code=502, detail=f"AI/LLM processing failed: {str(e)}")

        # 4. Final Response Construction
        # We merge the header (extracted locally) with the line items (from AI)
        response_payload = {
            "status": "success",
            "metadata": {
                "source": source,
                "document_type": header["document_type"]
            },
            "header": header,
            "data": ai_data, # Contains requested_items
            "debug": {
                "tokens_masked": len(token_map)
            }
        }
        
        return response_payload

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Unhandled error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.post("/re-extract")
async def re_extract_data(request: ReExtractionRequest):
    """
    Interactive Refinement Endpoint.
    Allows the user to send back the text with specific feedback (e.g. "You missed the second column")
    and get an immediate re-processed result.
    """
    logger.info(f"Received re-extraction request with feedback: {request.user_feedback}")
    
    try:
        # NOTE: In a real scenario you might want to re-mask here if raw_text contains freshly entered PII.
        # Check security compliance requirements.
        
        ai_data = extract_data_from_text(
            request.raw_text, 
            native_text=request.native_text,
            user_feedback=request.user_feedback
        )
        
        return {
            "status": "success",
            "data": ai_data,
            "message": "Re-extraction complete based on your feedback."
        }
        
    except Exception as e:
        logger.error(f"Re-extraction failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/correct")
async def submit_correction(request: CorrectionRequest):
    """
    Receives user corrections from the UI and saves them to the Learning Store.
    This enables the AI to learn from mistakes and improve over time.
    """
    try:
        correction_service.save_correction(
            request.raw_text_snippet,
            request.correct_json,
            request.full_text_context
        )
        logger.info(f"Correction saved from UI for snippet: {request.raw_text_snippet[:30]}...")
        return {"status": "success", "message": "Correction saved. The system has learned from this feedback."}
    except Exception as e:
        logger.error(f"Failed to save correction: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
