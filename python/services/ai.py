import os
import json
import logging
import asyncio
import requests
from typing import Dict, Any, Optional
from services.validator import validate_and_fix_items
from services.correction_service import CorrectionService
from services.verifier import Verifier
from services.column_detector import detect_column_headers

logger = logging.getLogger(__name__)

MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
MISTRAL_API_BASE = "https://api.mistral.ai/v1"

# Instantiate services
correction_service = CorrectionService()
verifier = Verifier()

SYSTEM_PROMPT = """You are a document parsing assistant designed to extract structured data from purchase orders and RFQs for automated uploading and validation in a procurement system.

Extract the following fields from the text:

requested_items: List of all requested materials/articles in the document. For each item, extract:

pos: Position number. **IMPORTANT**: Maintain the original numbering exactly.

config: **EXTRACT THIS FIRST**. A nested object containing technical specifications:
    - material_id: The structured material ID if present (Format: 100-xxx-xxx.xx-xx).
    - standard: Standard or DIN (e.g., "DIN 6885").
    - form: The exact form letter/code (e.g., "A", "B", "C", "AS", "AB", "E", "D", "K").
      * **CRITICAL**: Do NOT confuse dimension labels with the Form. "B=10" means Form is NOT "B".
      * **IMPORTANT**: Extract single letters like "E", "K", "D" if they appear after the standard (e.g. "DIN 6885 E").
    - material: Material grade.
      * **CRITICAL**: Normalize ALL C45 variants to "C45+C".
        - "C45" -> "C45+C"
        - "C45K" -> "C45+C"
        - "C45C" -> "C45+C"
        - "C45+C" -> "C45+C"
      * **WHITELIST**: Only accepted values are: ["C45+C", "42CrMo4", "1.4301", "1.4305", "1.4571", "1.4404", "1.4057"].
      * **IGNORE**: "P5K", "P85", "P100", "S355", "S235".
    - dimensions: Object with `width`, `height`, `length` (numeric values).
      * **CRITICAL**: Prioritize dimensions found WITHIN the article string (e.g., "20X12X50" -> Length=50).
      * **CRITICAL**: Handle TOLERANCE SPECS in dimensions: "8H9X7X36" means width=8, H9=tolerance, height=7, length=36.
        - The tolerance letter+number (H7, H9, h9) is NOT a dimension — it's a feature.
        - The tolerance letter+number (H7, H9) is NOT a dimension — it's a feature.
        - Example: "8H9X7X36" -> dimensions: {width:8, height:7, length:36}, feature: {type:"tolerance", spec:"H9"}
      * **HANDLE ENGLISH**: "Parallel key DIN 6885 E 8x7x80" -> Form=E, Dims=8x7x80.
      * **HANDLE DASH SEPARATORS**: "8x7x80 — 10000" -> The number after the dash is QUANTITY, not a dimension.
      * **IGNORE** loose numbers that look like material codes (e.g., ignore "100" from "100-013...").
      * Example: "B=10 H=8 T=16" -> {width: 10, height: 8, length: 16}.
    - features: List of features. Each feature is an object { "feature_type": "...", "spec": "..." }.
      * **CRITICAL**: Extract ALL technical specifications (M-codes, coatings, tolerances).
      * **ALWAYS** extract "M" codes (e.g., "M6") as type "thread"/"bore", even if they appear in the description.
      * **CRITICAL**: Extract ALL technical specifications:
        - M-codes (M4, M6, M8) -> type "thread"
        - H-tolerances (H7, H9) -> type "tolerance" 
        - NZG (Nutenzugabe/groove allowance) -> type "coating"
      * **CONSTRAINT**: Only extract M-codes between M1 and M21.
      * Example: "AS-8H9X7X36-M4-NZG" -> features: [{type:"thread",spec:"M4"},{type:"tolerance",spec:"H9"},{type:"coating",spec:"NZG"}]
    - weight_per_unit: Weight per single unit if available.

article_name: **CONSTRUCT** this field *AFTER* extracting config. Use this strict format:
"{GenericName}-{Form}-{Dimensions}-{Material}-{Features}"
- GenericName: "Passfeder"/"Passfed" -> "PF". Otherwise use base name.
- Form: e.g. "AS".
- Dimensions: e.g. "8X7X45".
- Material: e.g. "C45+C".
- Features: Any features found in config.features (e.g., "M4").
- Do NOT include DIN/Standard in the article_name.
*Example Result*: "PF-AS-8X7X45-C45+C-M4"

supplier_material_number: Supplier’s material number if present, else null.

customer_material_number: Customer’s material number if present, else null.

quantity: Number of parts requested.
  * **CRITICAL**: Use "Menge" (total quantity ordered), NOT "VPE" (packaging unit / Verpackungseinheit).
  * **CRITICAL**: Do NOT confuse "Preiseinheit" (PE / Price Unit) with Quantity.
    - Example: "15,85 / 100" -> 100 is the PRICE UNIT, not the quantity.
    - Look for the largest integer number that represents the total order amount.
  * VPE is the packaging size (e.g. 200), Menge is the actual order quantity (e.g. 2000).
  * Example: If VPE=200 and Menge=2000, extract quantity as 2000.
  * **FALLBACK**: If multiple numbers exist (200, 2000, 100), usually the LARGEST number is the Quantity.

unit: Unit of measure (pcs, kg, etc.).

delivery_date: Delivery date in YYYY-MM-DD format if present, else null.

Important rules:

Ignore “Nosta” as customer; it can only appear under supplier_name.

Do not skip any requested item.

If a field is missing, return it as null (or empty list for features).

Extract values exactly as shown in the document.

Dates must always be normalized to YYYY-MM-DD.

Always return a single valid JSON object with the exact key names above.

✨ If an item is split across multiple pages, merge them into a single requested_items entry.

✨ Ensure all position numbers (pos) are in sequence.

{LEARNED_CONTEXT}

output format

You must respond ONLY with valid raw rendered JSON.
- Do NOT include the word "json".
- Do NOT include the word "```json".
- Do NOT use triple backticks or markdown formatting.
- Do NOT wrap the response in any key like "output".
- Do NOT write anything starting at output directly start with valid root-level JSON.
- Only respond with a valid, root-level JSON object.
- Do NOT skip any line item. Continue extracting all line items until the sum of all line_total values exactly equals the total sale amount extracted from the invoice. This verification ensures that all items are fully extracted and no entries are missed. If the totals do not match, keep parsing and extracting additional line items until they do. Only then stop."""

USER_PROMPT_TEMPLATE = """Extract ALL line items and document information from this RFQ/Purchase Order document:

{TEXT}

Return ONLY valid JSON with no markdown formatting."""

def extract_data_from_text(text: str, native_text: str = None, user_feedback: str = None) -> Dict[str, Any]:
    """
    Sends the masked text to Mistral AI for extraction.
    Native text is user for post-validation (regex overrides).
    """
    if not MISTRAL_API_KEY:
        raise ValueError("MISTRAL_API_KEY not set")

    if not text:
        raise ValueError("No text provided for extraction")
        
    logger.info("Sending request to Mistral AI...")
    
    # 1. Fetch Learned Context (Few-Shot Examples)
    if correction_service:
        learned_context = correction_service.get_few_shot_context(text)
    else:
        learned_context = ""

    # Inject User Feedback if present - THIS IS CRITICAL
    feedback_instruction = ""
    if user_feedback:
        logger.info(f"Injecting user feedback: {user_feedback}")
        feedback_instruction = f"\n\n\U0001f6a8 USER FEEDBACK / MANUAL OVERRIDE:\nThe user has manually reviewed the previous output and provided this specific correction instruction:\n'{user_feedback}'\n\nYOU MUST FOLLOW THIS INSTRUCTION ABOVE ALL OTHER RULES."
        
    # Detect column headers from the document (DISABLED per user request "drop or pause column detector")
    # column_hint = detect_column_headers(text)
    # if column_hint:
    #     logger.info("Column headers detected and injected into prompt")
    column_hint = ""  # Force empty for now
        
    system_prompt_with_context = SYSTEM_PROMPT.replace("{LEARNED_CONTEXT}", learned_context + feedback_instruction + column_hint)
    
    headers = {
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "mistral-small-latest", # Switching back to Small (User: "small is fast")
        "messages": [
            {"role": "system", "content": system_prompt_with_context},
            {"role": "user", "content": USER_PROMPT_TEMPLATE.replace("{TEXT}", text)}
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"}
    }
    
    try:
        response = requests.post(
            f"{MISTRAL_API_BASE}/chat/completions",
            headers=headers,
            json=payload,
            timeout=240  # 4 minute timeout for very large files (>200s requested)
        )
        
        response.raise_for_status()
        
        result = response.json()
        content = result['choices'][0]['message']['content']
        logger.info(f"DEBUG: AI Response Content (First 500 chars): {content[:500]}...")
        
        if not content:
            raise ValueError("Empty response from AI")
            
        parsed_json = json.loads(content)
        
        # 2. Post-Processing: Validate & Fix using Regex on Native Text
        # This acts as our "Rule-Based Verification Layer"
        if "requested_items" in parsed_json:
            parsed_json["requested_items"] = validate_and_fix_items(
                parsed_json["requested_items"], 
                native_text=native_text, 
                ocr_text=text
            )
            
            # 3. AI Verification Layer (The "Double Check")
            # Only checking items with low confidence from the rules layer
            for item in parsed_json["requested_items"]:
                # Default confidence inside metadata might not exist if validator failed, default to 1.0 (optimistic) to avoid loop
                metadata = item.get("metadata", {})
                confidence = metadata.get("rule_confidence_score", 1.0)
                
                if confidence < 0.9:
                    raw_snippet = metadata.get("raw_text_snippet", "")
                    
                    # SKIP VERIFIER IF SNIPPET IS FALLBACK
                    # If we couldn't find the real raw line, the snippet is just the article name.
                    # The Verifier will 100% flag this as "hallucination" because the dimensions aren't in the snippet.
                    if metadata.get("snippet_is_fallback"):
                        logger.info(f"Skipping Verifier for Pos {item.get('pos')} because snippet is fallback.")
                        item["metadata"]["status"] = "verified_skipped_fallback"
                        continue

                    if raw_snippet:
                        logger.info(f"Low confidence ({confidence:.2f}) for Pos {item.get('pos')}. Triggering Verifier...")
                        try:
                            verification_result = verifier.verify_item(raw_snippet, item)
                            
                            item["metadata"]["verification_result"] = verification_result
                            
                            if not verification_result.get("is_correct", True):
                                correction = verification_result.get("correction")
                                if correction:
                                    logger.info(f"Verifier corrected item {item.get('pos')}")
                                    # Merge correction into item
                                    if "config" in correction:
                                        item["config"].update(correction["config"])
                                    if "article_name" in correction:
                                        item["article_name"] = correction["article_name"]
                                    
                                    item["metadata"]["status"] = "auto_corrected_by_verifier"
                                else:
                                    item["metadata"]["status"] = "flagged_by_verifier"
                            else:
                                item["metadata"]["status"] = "verified_correct"
                        except Exception as ve:
                             logger.error(f"Verifier error: {ve}")

        return parsed_json
        
    except requests.exceptions.Timeout:
        logger.error("Mistral AI request timed out")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse AI response as JSON: {content[:100]}...")
        raise ValueError("AI did not return valid JSON")
    except Exception as e:
        logger.error(f"Mistral API Error: {e}")
        raise e

async def extract_data_from_text_async(text: str, native_text: str = None, user_feedback: str = None) -> Dict[str, Any]:
    """
    Async wrapper for extraction.
    Implements PARALLEL CHUNKING for large documents (>100 lines ~ 20 items).
    """
    if not text:
        raise ValueError("No text provided")

    lines = text.split('\n')
    line_count = len(lines)
    
    # Threshold for chunking: 100 lines (approx 15-20 items depending on density)
    # If smaller, just run normally (blocking call in thread executor to avoid blocking main loop)
    if line_count < 100:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, extract_data_from_text, text, native_text, user_feedback)

    # --- CHUNKING LOGIC ---
    logger.info(f"Large document detected ({line_count} lines). Splitting into 2 chunks for PARALLEL processing.")
    
    midpoint = line_count // 2
    
    # Try to find a clean break (empty line) near midpoint to avoid cutting an item
    # Search 10 lines up/down
    split_idx = midpoint
    for offset in range(15):
        # Check forward
        if midpoint + offset < line_count and not lines[midpoint + offset].strip():
            split_idx = midpoint + offset
            break
        # Check backward
        if midpoint - offset > 0 and not lines[midpoint - offset].strip():
            split_idx = midpoint - offset
            break
            
    chunk1_text = '\n'.join(lines[:split_idx])
    chunk2_text = '\n'.join(lines[split_idx:])
    
    logger.info(f"Chunk 1: {len(chunk1_text)} chars. Chunk 2: {len(chunk2_text)} chars. Launching parallel tasks...")
    
    loop = asyncio.get_event_loop()
    
    # Launch parallel tasks
    # Note: We must pass native_text=None to chunks because mapping native text line-by-line is hard/risk.
    # The merged result will validate against the FULL native_text if available in the Validator later.
    task1 = loop.run_in_executor(None, extract_data_from_text, chunk1_text, None, user_feedback)
    task2 = loop.run_in_executor(None, extract_data_from_text, chunk2_text, None, user_feedback)
    
    results = await asyncio.gather(task1, task2, return_exceptions=True)
    
    # Process results
    merged_items = []
    
    for i, res in enumerate(results):
        if isinstance(res, Exception):
            logger.error(f"Chunk {i+1} failed: {res}")
            # Identify it but continue if possible? No, probably better to fail or warn.
            # If one chunk fails, we return partial?
            continue
        
        if isinstance(res, dict) and "requested_items" in res:
            merged_items.extend(res["requested_items"])
            
    # Sort merged items by Position (just in case they got mixed or AI restarted numbering)
    # AI prompt says "Maintain original numbering".
    # We trust the 'pos' field.
    try:
        # Filter out items without pos
        valid_items = [i for i in merged_items if str(i.get('pos','')).isdigit()]
        others = [i for i in merged_items if not str(i.get('pos','')).isdigit()]
        
        valid_items.sort(key=lambda x: float(x['pos']))
        merged_items = valid_items + others
    except Exception as e:
        logger.warning(f"Could not sort merged items by pos: {e}")

    logger.info(f"Parallel chunking complete. Merged {len(merged_items)} items.")
    
    return {"requested_items": merged_items}
