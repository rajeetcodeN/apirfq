import os
import json
import logging
import asyncio
import requests
import re
from typing import Dict, Any, Optional, List
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
    - form: The exact form letter/code.
      * MUST be one of: "A", "B", "C", "D", "E", "F", "AB", "AS", "BS", "ABS", "CD", "EF", "K".
      * If the text contains an invalid form (e.g. "FC", "PF"), DO NOT extract it as a form. Return null instead.
      * Pay attention to multi-letter forms like "ABS", "CD", "EF", "BS".
      * **CRITICAL**: Do NOT confuse dimension labels with the Form. "B=10" means Form is NOT "B".
      * **IMPORTANT**: Extract single letters like "E", "K", "D" if they appear after the standard (e.g. "DIN 6885 E").
    - material: Material grade (extract exactly as written).
      * **CRITICAL**: Extract the EXACT material name or DIN number from the text. Do NOT guess or default to C45+C.
      * Common materials include:
        - Carbon Steel: C40, C45, C45+C, C45E, C45R, C50, C50E, C60E
        - Alloy Steel: 16MnCr5, 17Cr3, 20MnCr5, 25CrMo4, 30CrMo4, 34CrMo4, 34CrNiMo6, 41Cr4, 42CrMo4
        - Bearing/Tool Steel: 100Cr6, 100CrMn6, 102Cr6, 95MnWCr5, X100CrMoV5, X153CrMoV12, X40CrMoV5-1
        - High-Speed Steel: HS6-5-2, HS2-9-1-8, HS10-4-3-10
        - Stainless Steel: X5CrNi18-9, X2CrNiMo17-12-2, X6CrNiMoTi17-12-2, X10CrNiS18-9, X17CrNi16-2, X20Cr13
        - Structural Steel: S235JR, S235J2, S275JR, S355JR, S355J2, S355K2, S420N
        - International: ASTM A36, GB Q235, JIS SCM440
      * **DIN NUMBERS**: Also extract material numbers like 1.4301, 1.4571, 1.7225, 1.0503, etc.
      * **KEYWORDS**: "VA", "V2A", "V4A", "STAINLESS" all refer to stainless steel.
      * **C45 VARIANTS**: Normalize ALL C45 variants (C45, C45K, C45C, C45E, C45R) and the number "1.0503" -> "C45+C".
      * **SUFFIXES**: If a material has suffixes separated by '+' (e.g. "1.4057+QT800+2H", "1.4301+C700"), extract ONLY the base material (e.g. "1.4057", "1.4301"). Completely DROP the '+' suffixes. They are NOT treatments.
      * **IGNORE**: "P5K", "P85", "P100" (these are packaging/position codes, NOT materials).
    - dimensions: Object with `width`, `height`, `length` (numeric values).
      * **CRITICAL**: Prioritize dimensions found WITHIN the article string (e.g., "20X12X50" -> Length=50).
      * **CRITICAL**: Handle TOLERANCE SPECS in dimensions. The tolerance (h6, h7, h8, H7, H9) is NOT a dimension — STRIP IT before extracting width/height/length.
        - "8H9X7X36" -> width=8, height=7, length=36 (H9 is a tolerance, NOT height)
        - "8h6x7x30" -> width=8, height=7, length=30 (h6 is a tolerance on width, NOT a dimension)
        - "8xh68x30" -> width=8, height=8, length=30 (h6 is a tolerance PREFIX on height=8, the "6" is NOT height)
        - "h65x7x30" -> width=5, height=7, length=30 (h6 is a tolerance PREFIX on width=5, the "6" is NOT width)
      * **DANGER**: DO NOT confuse the digit in the tolerance spec (e.g., "6" from "h6") with a dimension value!
        - WRONG: "8xh68x30" -> height=6 (INCORRECT, "6" is part of "h6")
        - RIGHT: "8xh68x30" -> height=8 (CORRECT, "8" is the actual height, "h6" is the tolerance)
      * **HANDLE ENGLISH**: "Parallel key DIN 6885 E 8x7x80" -> Form=E, Dims=8x7x80.
      * **HANDLE DASH SEPARATORS**: "8x7x80 — 10000" -> The number after the dash is QUANTITY, not a dimension.
      * **IGNORE** loose numbers that look like material codes (e.g., ignore "100" from "100-013...").
      * Example: "B=10 H=8 T=16" -> {width: 10, height: 8, length: 16}.
    - features: List of features. Each feature is an object { "feature_type": "...", "spec": "...", "position": "..." }.
      * **CRITICAL**: Extract ALL technical specifications (M-codes, coatings, tolerances).
      * **ALWAYS** extract "M" codes (e.g., "M6") as type "thread"/"bore", even if they appear in the description.
      * **CRITICAL**: Extract ALL technical specifications:
        - M-codes (M4, M6, M8) -> type "thread"
        - H-tolerances (H7, H9) -> type "tolerance" 
        - Shaft tolerances (h6, h7, h8) -> type "tolerance" with "position" field
        - NZG (Nutenzugabe/groove allowance) -> type "coating"
      * **SHAFT TOLERANCE (h6/h7/h8/h9)**: Extract the shaft tolerance and identify WHICH dimension it applies to.
        - You may find MULTIPLE tolerances in one string (e.g. "8h8x7h8x30" -> h8 on width, h8 on height). Extract BOTH if present.
        There are 5 possible formats:
        1. Suffix on width:  "8h6x7x30"  -> spec=h6, position=width  (h6 AFTER width digit)
        2. Suffix on height: "8x7h7x30"  -> spec=h7, position=height (h7 AFTER height digit)
        3. Prefix on width:  "h68x7x30"  -> spec=h6, position=width  (h6 BEFORE width digit)
        4. Prefix on height: "8xh68x30"  -> spec=h6, position=height (h6 BEFORE height digit)
        5. Standalone:       "h6 8x7x30" -> spec=h6, position=width  (h6 separated by space)
        - **CRITICAL — ITEM ISOLATION**: Each line item is COMPLETELY INDEPENDENT. You must evaluate each item's tolerance ONLY from the characters written in that specific item's text. NEVER copy, inherit, or infer a tolerance from a different item, even if the items look similar.
        - **DEFAULT RULE**: If and ONLY if no shaft tolerance (h6/h7/h8/h9) is physically written for this specific item -> default to {type:"tolerance", spec:"h9", position:"width"}.
        - **WRONG EXAMPLE**: Item 6 has "10x8h7x50" (h7). Items 1-4 have NO tolerance in text. Do NOT apply h7 to items 1-4. They must default to h9 on width.
        - **RIGHT EXAMPLE**: Item 1 "PF C 12x8x50 C60" -> no tolerance written -> features: [{type:"tolerance", spec:"h9", position:"width"}]
      * **CONSTRAINT**: Only extract M-codes between M1 and M21.
      * Example: "AS-8h6X7X36-M4-NZG" -> features: [{type:"tolerance",spec:"h6",position:"width"},{type:"thread",spec:"M4"},{type:"coating",spec:"NZG"}]
    - heat_treatment: Extracted heat treatment spec (e.g., "geh.50-55HRC", "verg.90-100", "geh.56-60 0,3-0,5", "N533"). Units like HRC/HV may be omitted.
    - surface_treatment: Extracted surface treatment spec (e.g., "poliert", "verzinkt", "QT 800", "carb", "carbo.50-54", "nitriert", "salzbadnitriert", "Oberflächenbehandlung", "Oberfläche", "Oberfl."). **DO NOT EXTRACT** testing methods (like "Wirb.") or packaging units (like "VP200").
    - marking: Extracted marking spec. **CRITICAL**: ONLY extract if it starts with "KZ", "KX", "SS", "HC", "T", "Ken.", "Kennz.", "gekennz.", "Kennzeich.", "gekennzeichnet", or "marking gek.". DO NOT extract anything else. "NEU", "*NEUTEIL*", "VP100", "QS APZ3.1", "PREN>40", "C700" are NOT markings. If no explicitly labeled marking exists, RETURN NULL. Do not guess.
    - weight_per_unit: Weight per single unit if available.

article_name: **CONSTRUCT** this field *AFTER* extracting config. Use this strict format:
"{GenericName}-{Form}-{Dimensions}-{Material}-{Features}-{HeatTreatment}-{SurfaceTreatment}-{Marking}"
- GenericName: "Passfeder"/"Passfed" -> "PF". Otherwise use base name.
- Form: e.g. "AS".
- Dimensions: e.g. "8X7X45".
- Material: e.g. "C45+C".
- Features: Any features found in config.features (e.g., "M4").
- HeatTreatment: Any heat treatment found (e.g. "geh.50-55HRC"). Ignore if null.
- SurfaceTreatment: Any surface treatment found (e.g. "verzinkt"). Ignore if null.
- Marking: Any marking found (e.g. "KZ"). Ignore if null.
- Do NOT include DIN/Standard in the article_name.
*Example Result*: "PF-AS-8X7X45-C45+C-M4-geh.50-55HRC-verzinkt-KZ"

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

# --- Batch Processing Helpers ---

def identify_item_positions(text: str) -> List[int]:
    """
    Scans text for line item 'anchors' (Pos 1, 1., 0010, etc.)
    Returns a list of character indices where each item likely starts.
    """
    # Patterns likely to indicate a new position:
    # 1. "Pos 1" or "Pos. 1" or "Position 1"
    # 2. Start of line "1." or "01." or "001."
    # 3. "1 " at the beginning of a line (risky, but common in simple txt)
    
    anchors = []
    
    # regexes = [
    #     r'(?i)(?:^|[\n])\s*(?:Pos\.?|Position)?\s*(\d+)\s*[\.\s]', # Pos 1 or 1.
    #     r'(?i)(?:^|[\n])\s*(\d{3,4})\s+', # 0010 style
    # ]
    
    # For now, let's use a robust sequential anchor search
    lines = text.split('\n')
    current_idx = 0
    
    for line in lines:
        # 1. Position based: "Pos 1", "1.", "0010"
        pos_match = re.match(r'^\s*(?:Pos\.?|Position)?\s*\d+[\.\s]', line, re.IGNORECASE) or re.match(r'^\s*\d{2,4}\s+', line)
        
        # 2. Article based: "-PF", "PF", "Passfeder", "Parallel key"
        article_match = re.match(r'^\s*[\-\*•]?\s*(?:PF|Passfeder|Paßfeder|Parallel\s*key|Fitting\s*key)', line, re.IGNORECASE)
        
        if pos_match or article_match:
            anchors.append(current_idx)
        current_idx += len(line) + 1 # +1 for newline
        
    # Deduplicate: if multiple anchors are within 20 chars, keep only the first
    if not anchors: return []
    
    clean_anchors = [anchors[0]]
    for a in anchors[1:]:
        if a - clean_anchors[-1] > 15: # Minimum 15 chars per item assumption
            clean_anchors.append(a)
            
    return clean_anchors

def chunk_text_by_anchors(text: str, items_per_chunk: int = 25) -> List[str]:
    """
    Splits text into chunks, each containing approximately items_per_chunk.
    """
    anchors = identify_item_positions(text)
    
    if not anchors or len(anchors) <= items_per_chunk:
        return [text]
        
    chunks = []
    for i in range(0, len(anchors), items_per_chunk):
        start_idx = anchors[i]
        # End index is the start of the next chunk's first anchor, or end of string
        if i + items_per_chunk < len(anchors):
            end_idx = anchors[i + items_per_chunk]
            chunks.append(text[start_idx:end_idx])
        else:
            chunks.append(text[start_idx:])
            
    # If the first chunk missed some header text, prepend it
    if anchors[0] > 0:
        header_text = text[:anchors[0]]
        chunks[0] = header_text + chunks[0]
        
    logger.info(f"Chunking: Divided text into {len(chunks)} chunks (Total items detected: ~{len(anchors)})")
    return chunks


USER_PROMPT_TEMPLATE = """Extract ALL line items and document information from this RFQ/Purchase Order document:

{TEXT}

Return ONLY valid JSON with no markdown formatting."""

def extract_data_from_text(text: str, native_text: Optional[str] = None, user_feedback: Optional[str] = None, is_chunk: bool = False) -> Dict[str, Any]:
    """
    Sends the masked text to Mistral AI for extraction.
    Native text is used for post-validation (regex overrides).
    """
    if not MISTRAL_API_KEY:
        raise ValueError("MISTRAL_API_KEY not set")

    if not text:
        raise ValueError("No text provided for extraction")
        
    logger.info(f"Sending request to Mistral AI (is_chunk={is_chunk})...")
    
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
        
    # If this is a chunk (not the first chunk), tell AI to skip headers to save time
    chunk_instruction = ""
    if is_chunk:
        chunk_instruction = "\n\n**IMPORTANT**: This is a partial text chunk. Focus ONLY on extracting line items (requested_items). You can return null or empty values for the header/document information fields (supplier_name, rfq_number, etc.) as they are already extracted."

    system_prompt_with_context = SYSTEM_PROMPT.replace("{LEARNED_CONTEXT}", learned_context + feedback_instruction + column_hint + chunk_instruction)

    
    headers = {
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "mistral-medium-latest", # Reverting to Medium per user override
        "messages": [
            {"role": "system", "content": system_prompt_with_context},
            {"role": "user", "content": USER_PROMPT_TEMPLATE.replace("{TEXT}", text)}
        ],
        "temperature": 0.1,
    "response_format": {"type": "json_object"}
    }

    try: # This is the new try block wrapping the entire API call and processing
        max_retries = 3
        retry_delay = 2

        for attempt in range(max_retries + 1):
            try:
                response = requests.post(
                    f"{MISTRAL_API_BASE}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=240  # 4 minute timeout for very large files (>200s requested)
                )

                if response.status_code == 429:
                    if attempt < max_retries:
                        wait_time = retry_delay * (2 ** attempt)
                        logger.warning(f"Mistral AI Rate Limit (429) hit. Retrying in {wait_time}s (Attempt {attempt+1}/{max_retries})...")
                        import time
                        time.sleep(wait_time)
                        continue
                    else:
                        logger.error("Mistral AI Rate Limit (429) persistent after multiple retries.")
                        response.raise_for_status()

                response.raise_for_status()
                break # Success
            except requests.exceptions.RequestException as re:
                if attempt == max_retries:
                    raise re
                logger.warning(f"Mistral API request failed: {re}. Retrying...")
                import time
                time.sleep(2)

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

async def extract_data_from_text_async(text: str, native_text: Optional[str] = None, user_feedback: Optional[str] = None) -> Dict[str, Any]:
    """
    Async wrapper for extraction. Performs parallel chunking for large documents (70-500 items).
    Chunks text into batches of 25 items and processes them simultaneously.
    """
    if not text:
        raise ValueError("No text provided")

    # 1. Chunk the text
    # We use 10 items per chunk to ensure each request finishes well within the 4min timeout
    # and to maximize parallel throughput with our concurrency limit of 5.
    chunks = chunk_text_by_anchors(text, items_per_chunk=10)
    
    if len(chunks) == 1:
        # Fallback to standard single call for small files
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, extract_data_from_text, text, native_text, user_feedback)

    logger.info(f"Starting parallel extraction for {len(chunks)} chunks...")
    
    # We use a semaphore to limit concurrency (e.g., 4 simultaneous requests MAX)
    # to avoid hitting Mistral API rate limits (TPM/RPM)
    semaphore = asyncio.Semaphore(4)
    loop = asyncio.get_event_loop()

    async def process_chunk(chunk_text: str, index: int):
        async with semaphore:
            # Stagger the start of each chunk to avoid a burst of 5 requests at once
            if index > 0:
                wait_time = index * 1.5 # 1.5s delay between chunk starts
                logger.info(f"Staggering chunk {index+1}: Waiting {wait_time}s before start...")
                await asyncio.sleep(wait_time)
                
            # First chunk is NOT marked as 'is_chunk' because we want it to extract the header fields
            is_chunk_flag = (index > 0)
            return await loop.run_in_executor(None, extract_data_from_text, chunk_text, native_text, user_feedback, is_chunk_flag)

    tasks = [process_chunk(chunk, i) for i, chunk in enumerate(chunks)]
    
    # 3. Gather results
    results = await asyncio.gather(*tasks)
    
    # 4. Merge results
    if not results:
        raise ValueError("Parallel extraction returned no results")
        
    # The first result contains our master header/metadata
    master_result = results[0]
    all_items = []
    
    for i, res in enumerate(results):
        items = res.get("requested_items", [])
        if items:
            all_items.extend(items)
            
    # Re-sequence 'pos' to ensure it's 1, 2, 3... in case AI reset it per chunk
    for idx, item in enumerate(all_items):
        item["pos"] = idx + 1
        
    master_result["requested_items"] = all_items
    
    # Add batch metadata
    if "metadata" not in master_result: master_result["metadata"] = {}
    master_result["metadata"]["batch_count"] = len(chunks)
    master_result["metadata"]["total_items_extracted"] = len(all_items)
    master_result["metadata"]["processing_mode"] = "parallel_burst"
    
    logger.info(f"Parallel extraction complete. Merged {len(all_items)} items from {len(chunks)} chunks.")
    return master_result

