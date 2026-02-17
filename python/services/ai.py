import os
import json
import logging
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
    - form: The exact form letter/code (e.g., "A", "B", "C", "AS", "AB").
      * **CRITICAL**: Do NOT confuse dimension labels with the Form. "B=10" means Form is NOT "B".
    - material: Material grade.
      * **WHITELIST**: Only accepted values are: ["C45", "C45+C", "C45K", "42CrMo4", "1.4301", "1.4305", "1.4571", "1.4404", "1.4057"].
      * **CLEANING**: Remove prefixes like "P", "PF", "P85", "P885" if attached to material.
        - Example: "P885-C45C" -> "C45+C"
        - Example: "P5K" -> "C45K"
        - Example: "P5C" -> "C45+C"
        - Example: "C45C" -> "C45+C"
      * **CRITICAL**: If the text contains "C45+C", extracted material MUST be "C45+C".
      * **IGNORE**: "P5K", "P85", "P100", "S355", "S235" -> These are NOT valid.
      * If multiple valid materials appear (e.g. "C45+C / 1.4301"), output them with a slash.
    - dimensions: Object with `width`, `height`, `length` (numeric values).
      * **CRITICAL**: Prioritize dimensions found WITHIN the article string (e.g., "20X12X50" -> Length=50).
      * **CRITICAL**: Handle TOLERANCE SPECS in dimensions: "8H9X7X36" means width=8, H9=tolerance, height=7, length=36.
        - The tolerance letter+number (H7, H9, h9) is NOT a dimension — it's a feature.
        - Example: "8H9X7X36" -> dimensions: {width:8, height:7, length:36}, feature: {type:"tolerance", spec:"H9"}
      * **IGNORE** loose numbers that look like material codes (e.g., ignore "100" from "100-013...").
      * Example: "B=10 H=8 T=16" -> {width: 10, height: 8, length: 16}.
    - features: List of features. Each feature is an object { "feature_type": "...", "spec": "..." }.
      * **CRITICAL**: Extract ALL technical specifications (M-codes, coatings, tolerances).
      * **ALWAYS** extract "M" codes (e.g., "M6") as type "thread"/"bore", even if they appear in the description.
      * **CONSTRAINT**: Only extract M-codes between M1 and M21. Ignore smaller (e.g. M0.5) or larger (e.g. M30).
      * Extract H-tolerances (H7, H9) -> type "tolerance"
      * Extract NZG (Nutenzugabe/groove allowance) -> type "groove_allowance"
      * Example: "PF...-20x12x100-M6" -> features: [{"feature_type": "thread", "spec": "M6"}]
      * Example: "AS-8H9X7X36-M4-NZG" -> features: [{type:"thread",spec:"M4"},{type:"tolerance",spec:"H9"},{type:"groove_allowance",spec:"NZG"}]
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
  * VPE is the packaging size, Menge is the actual order quantity.
  * Example: If VPE=200 and Menge=2000, extract quantity as 2000.

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
        
    # Detect column headers from the document
    column_hint = detect_column_headers(text)
    if column_hint:
        logger.info("Column headers detected and injected into prompt")
        
    system_prompt_with_context = SYSTEM_PROMPT.replace("{LEARNED_CONTEXT}", learned_context + feedback_instruction + column_hint)
    
    headers = {
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "mistral-medium-latest",
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
            timeout=120  # 2 minute timeout (Python can handle it)
        )
        
        response.raise_for_status()
        
        result = response.json()
        content = result['choices'][0]['message']['content']
        
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
