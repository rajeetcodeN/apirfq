
import os
import logging
import uvicorn
from fastapi import FastAPI, File, UploadFile, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from typing import Dict, Any, Optional
from pydantic import BaseModel
import httpx
import asyncio

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

# n8n Webhook for parallel safety extraction
N8N_WEBHOOK_URL = "https://nosta.app.n8n.cloud/webhook/60573ec2-ab96-4470-9c3c-dcba96c5264e"

async def send_to_n8n(file_bytes: bytes, filename: str) -> dict:
    """Send raw file to n8n webhook and wait for extracted data response."""
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            files = {"file": (filename, file_bytes)}
            response = await client.post(N8N_WEBHOOK_URL, files=files)
            logger.info(f"n8n webhook response: {response.status_code}")
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"n8n returned non-200: {response.status_code}")
                return None
    except Exception as e:
        logger.warning(f"n8n webhook failed (non-critical): {e}")
        return None

def cross_validate(our_items: list, n8n_data: dict) -> list:
    """
    Compare our extraction with n8n's extraction.
    Flag mismatches on key fields: quantity, material, dimensions.
    """
    if not n8n_data:
        return our_items
    
    # Try to get n8n items - adapt to whatever format n8n returns
    n8n_items = []
    if isinstance(n8n_data, list):
        n8n_items = n8n_data
    elif isinstance(n8n_data, dict):
        n8n_items = n8n_data.get("items", n8n_data.get("requested_items", n8n_data.get("data", [])))
        if isinstance(n8n_items, dict):
            n8n_items = n8n_items.get("requested_items", [])
    
    if not n8n_items:
        logger.info("n8n cross-validation: No items from n8n to compare")
        return our_items
    
    logger.info(f"n8n cross-validation: Comparing {len(our_items)} our items vs {len(n8n_items)} n8n items")
    
    # Build n8n lookup by position
    n8n_by_pos = {}
    for item in n8n_items:
        pos = str(item.get("pos", item.get("position", ""))).strip()
        if pos:
            n8n_by_pos[pos] = item
    
    for item in our_items:
        pos = str(item.get("pos", "")).strip()
        n8n_item = n8n_by_pos.get(pos)
        
        if not n8n_item:
            continue
        
        mismatches = []
        config = item.get("config", {})
        n8n_config = n8n_item.get("config", n8n_item)  # n8n might not nest under config
        
        # Compare quantity
        our_qty = item.get("quantity")
        n8n_qty = n8n_item.get("quantity", n8n_item.get("menge"))
        if our_qty and n8n_qty and str(our_qty) != str(n8n_qty):
            mismatches.append(f"quantity: ours={our_qty} vs n8n={n8n_qty}")
        
        # Compare material
        our_mat = config.get("material", "")
        n8n_mat = n8n_config.get("material", "")
        if our_mat and n8n_mat and our_mat.lower() != str(n8n_mat).lower():
            mismatches.append(f"material: ours={our_mat} vs n8n={n8n_mat}")
        
        # Compare dimensions (numeric comparison to avoid 22.0 vs 22 false positives)
        our_dims = config.get("dimensions", {}) or {}
        n8n_dims = n8n_config.get("dimensions", {}) or {}
        if our_dims and n8n_dims:
            for key in ["width", "height", "length"]:
                ov = our_dims.get(key)
                nv = n8n_dims.get(key)
                if ov is not None and nv is not None:
                    try:
                        if float(ov) != float(nv):
                            mismatches.append(f"{key}: ours={ov} vs n8n={nv}")
                    except (ValueError, TypeError):
                        if str(ov) != str(nv):
                            mismatches.append(f"{key}: ours={ov} vs n8n={nv}")
        
        # Apply results
        if mismatches:
            if "metadata" not in item:
                item["metadata"] = {}
            item["metadata"]["n8n_mismatches"] = mismatches
            item["metadata"]["n8n_flag"] = True
            # Lower confidence for mismatched items
            current_conf = item["metadata"].get("rule_confidence_score", 1.0)
            item["metadata"]["rule_confidence_score"] = min(current_conf, 0.5)
            logger.warning(f"Pos {pos}: n8n mismatch detected: {mismatches}")
    
    return our_items

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
        
        # Start n8n extraction in parallel (runs while our pipeline processes)
        n8n_task = asyncio.create_task(send_to_n8n(file_bytes, file.filename))
        
        # 1. Ingestion
        try:
            audit_service.log_event("INGESTION_START", file.filename, "STARTED", {"size_bytes": len(file_bytes), "mime_type": file.content_type})
            
            ingestion_result = await route_ingestion(file_bytes, file.content_type, file.filename)
            source = ingestion_result["source"]
            
            # Handle Hybrid PDF logic
            # STRATEGY: OCR is PRIMARY (understands visual table layout + table_format=markdown)
            # Native text is secondary for validator cross-checking
            if source == "hybrid_pdf":
                raw_text = ingestion_result["ocr_text"]        # OCR = primary (table-aware)
                native_text = ingestion_result["native_text"]  # Native = secondary for validator
                ocr_tables = ingestion_result.get("ocr_tables", [])
            else:
                raw_text = ingestion_result["raw_data"]
                native_text = None
                ocr_tables = ingestion_result.get("ocr_tables", [])

            # If structured tables were extracted by OCR, append as supplementary data
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
        
        # 5. Cross-validate with n8n results (n8n_task was started in parallel earlier)
        # We wait MAX 120 seconds for n8n (User requested > 200s capability for large file holistic processing).
        try:
            n8n_data = await asyncio.wait_for(n8n_task, timeout=120.0)
            if n8n_data and "requested_items" in ai_data:
                ai_data["requested_items"] = cross_validate(ai_data["requested_items"], n8n_data)
                logger.info("n8n cross-validation complete")
        except asyncio.TimeoutError:
            logger.warning(f"n8n cross-validation TIMED OUT (>120s): Returning AI data without cross-check.")
        except Exception as e:
            logger.warning(f"n8n cross-validation skipped: {e}")
        
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
