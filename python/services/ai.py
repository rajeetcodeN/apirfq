
import os
import json
import logging
import requests
from typing import Dict, Any

logger = logging.getLogger(__name__)

MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
MISTRAL_API_BASE = "https://api.mistral.ai/v1"

SYSTEM_PROMPT = """You are a document parsing assistant designed to extract structured data from purchase orders and RFQs for automated uploading and validation in a procurement system.

Extract the following fields from the text:

requested_items: List of all requested materials/articles in the document. For each item, extract:

pos: Position number. **IMPORTANT**: Maintain the original numbering exactly (e.g., if the document uses 10, 20, 30, use 10, 20, 30. Do not re-index to 1, 2, 3).

article_name: Name/description of the material (do not include codes inside description).

supplier_material_number: Supplier’s material number if present, else null.

customer_material_number: Customer’s material number if present, else null.

quantity: Number of parts requested.

unit: Unit of measure (pcs, kg, etc.).

delivery_date: Delivery date in YYYY-MM-DD format if present, else null.

config: A nested object containing technical specifications:
    - material_id: The structured material ID if present (Format: 100-xxx-xxx.xx-xx, e.g., "100-013-595.01-00").
    - standard: Standard or DIN (e.g., "DIN 6885").
    - form: The exact form letter from the product code (e.g., "A", "B", "C", "D", "E", "F", "G", "H", "J", "AS", "AB", "ABS", "CD", "EF").
      * Extract the form exactly as it appears in the article name or product code.
      * Common forms: A, B, C, D, E, F, G, H, J, AS, AB, ABS, CD, EF.
    - material: Material grade. Must match exactly (e.g., "C45", "C45+C", "1.4057", "1.4571").
    - dimensions: Object with `width`, `height`, `length` (numeric values).
    - features: List of features. Each feature is an object { "feature_type": "...", "spec": "..." }.
      * Extract "bore" sizes (M1 to M21) here.
      * Extract "thread", "coating", "heat_treatment" here.
    - weight_per_unit: Weight per single unit if available (numeric).

Important rules:

Ignore “Nosta” as customer; it can only appear under supplier_name.

Do not skip any requested item.

If a field is missing, return it as null (or empty list for features).

Extract values exactly as shown in the document.

Dates must always be normalized to YYYY-MM-DD.

Always return a single valid JSON object with the exact key names above.

✨ If an item is split across multiple pages, merge them into a single requested_items entry.

✨ Ensure all position numbers (pos) are in sequence.

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

def extract_data_from_text(text: str) -> Dict[str, Any]:
    """
    Sends the masked text to Mistral AI for extraction.
    """
    if not MISTRAL_API_KEY:
        raise ValueError("MISTRAL_API_KEY not set")

    if not text:
        raise ValueError("No text provided for extraction")
        
    logger.info("Sending request to Mistral AI...")
    
    headers = {
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "mistral-small-latest",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
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
