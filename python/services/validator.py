import re
import logging
import json
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# ── Material Auto-Correction ──────────────────────────────────────────────────
VALID_MATERIALS = ["C45", "C45+C", "C45K", "42CrMo4", "1.4301", "1.4305", "1.4571", "1.4404", "1.4057"]

# Known bad -> correct mappings
MATERIAL_FIX_MAP = {
    "P5K": "C45K",
    "P5C": "C45+C",
    "C45C": "C45+C",
    "P85-C45K": "C45K",
    "P885-C45C": "C45+C",
    "P885-C45+C": "C45+C",
    "P85-C45+C": "C45+C",
    "P85-C45C": "C45+C",
}

def fix_material(material: str) -> str:
    """
    Auto-corrects known bad material values.
    1. Check exact match in fix map
    2. Try cleaning P-prefixes
    3. Return original if already valid
    """
    if not material:
        return material
    
    # 1. Exact match in known fixes
    if material in MATERIAL_FIX_MAP:
        fixed = MATERIAL_FIX_MAP[material]
        logger.info(f"Material auto-corrected: '{material}' -> '{fixed}'")
        return fixed
    
    # 2. Already valid? Return as-is
    if material in VALID_MATERIALS:
        return material
    
    # 3. Try stripping common P-prefixes and re-checking
    cleaned = material
    for prefix in ["P885-", "P85-", "PF-", "P5", "P8"]:
        if cleaned.upper().startswith(prefix.upper()):
            cleaned = cleaned[len(prefix):]
            break
    
    # Check if cleaned version is valid
    if cleaned in VALID_MATERIALS:
        logger.info(f"Material auto-corrected: '{material}' -> '{cleaned}'")
        return cleaned
    
    # 4. Check if it's "C45C" style (missing +)
    if re.match(r'^C45[A-Z]?$', cleaned, re.IGNORECASE):
        if cleaned.upper() == "C45C":
            logger.info(f"Material auto-corrected: '{material}' -> 'C45+C'")
            return "C45+C"
        elif cleaned.upper() == "C45K":
            return "C45K"
    
    # 5. Nothing worked, return original (validator will penalize confidence)
    logger.warning(f"Unknown material '{material}' - could not auto-correct")
    return material

def parse_dimensions_from_string(text: str) -> Optional[Dict[str, float]]:
    """
    Extracts dimensions (WxHxL) from a string like '20x12x50' or '8H9x7x36'.
    Handles tolerance specs embedded in dimensions in 4 formats:
      Suffix-Width:  8h6x7x30  (tolerance AFTER width digit)
      Suffix-Height: 8x7h7x30  (tolerance AFTER height digit)
      Prefix-Width:  h68x7x30  (tolerance BEFORE width digit)
      Prefix-Height: 8xh68x30  (tolerance BEFORE height digit)
    Returns {width, height, length} or None.
    """
    # 1. Suffix on WIDTH: 8h6x7x30 or 8H9X7X36
    match = re.search(r'(\d+(?:[.,]\d+)?)[hH]\d+\s*[xX]\s*(\d+(?:[.,]\d+)?)\s*[xX]\s*(\d+(?:[.,]\d+)?)', text)
    if match:
        try:
            dims = [float(d.replace(',', '.')) for d in match.groups()]
            return {"width": dims[0], "height": dims[1], "length": dims[2]}
        except ValueError:
            pass
    
    # 2. Suffix on HEIGHT: 8x7h7x30
    match = re.search(r'(\d+(?:[.,]\d+)?)\s*[xX]\s*(\d+(?:[.,]\d+)?)[hH]\d+\s*[xX]\s*(\d+(?:[.,]\d+)?)', text)
    if match:
        try:
            dims = [float(d.replace(',', '.')) for d in match.groups()]
            return {"width": dims[0], "height": dims[1], "length": dims[2]}
        except ValueError:
            pass
    
    # 3. Prefix on HEIGHT: 8xh68x30 (h6 before height digit 8)
    match = re.search(r'(\d+(?:[.,]\d+)?)\s*[xX]\s*[hH][678]\s*(\d+(?:[.,]\d+)?)\s*[xX]\s*(\d+(?:[.,]\d+)?)', text)
    if match:
        try:
            dims = [float(d.replace(',', '.')) for d in match.groups()]
            return {"width": dims[0], "height": dims[1], "length": dims[2]}
        except ValueError:
            pass
    
    # 4. Prefix on WIDTH: h68x7x30 (h6 before width digit 8)
    match = re.search(r'[hH][678]\s*(\d+(?:[.,]\d+)?)\s*[xX]\s*(\d+(?:[.,]\d+)?)\s*[xX]\s*(\d+(?:[.,]\d+)?)', text)
    if match:
        try:
            dims = [float(d.replace(',', '.')) for d in match.groups()]
            return {"width": dims[0], "height": dims[1], "length": dims[2]}
        except ValueError:
            pass
    
    # 5. Standard 3D: 20x12x100
    match = re.search(r'(\d+(?:[.,]\d+)?)\s*[xX]\s*(\d+(?:[.,]\d+)?)\s*[xX]\s*(\d+(?:[.,]\d+)?)', text)
    if match:
        try:
            dims = [float(d.replace(',', '.')) for d in match.groups()]
            return {"width": dims[0], "height": dims[1], "length": dims[2]}
        except ValueError:
            pass
            
    # 6. Standard 2D: 20x12
    match = re.search(r'(\d+(?:[.,]\d+)?)\s*[xX]\s*(\d+(?:[.,]\d+)?)', text)
    if match:
        try:
            dims = [float(d.replace(',', '.')) for d in match.groups()]
            return {"width": dims[0], "height": dims[1], "length": None}
        except ValueError:
            pass

    return None

def extract_features_from_string(text: str) -> List[Dict[str, str]]:
    """
    Extracts explicit features from the string:
    - M-codes (M4, M6, M8)
    - H-tolerances (H7, H9)
    - NZG (Nutenzugabe / groove allowance)
    """
    features = []
    
    # M-Code Pattern: M followed by digits (e.g., M6, M8, M10)
    m_code_pattern = r'(?:^|[\s\-])(M\d+)(?:[\s\-]|$)'
    m_matches = re.findall(m_code_pattern, text, re.IGNORECASE)
    for code in m_matches:
        if not any(f['spec'] == code.upper() for f in features):
            features.append({"feature_type": "thread", "spec": code.upper()})
    
    # H-Tolerance Pattern: H followed by digits (e.g., H7, H9) — ISO fit tolerance
    h_tol_pattern = r'(?:^|[\s\-\d])(H\d+)(?=[xX\s\-]|$)'
    h_matches = re.findall(h_tol_pattern, text)
    for code in h_matches:
        if not any(f['spec'] == code.upper() for f in features):
            features.append({"feature_type": "tolerance", "spec": code.upper()})
    
    # NZG Pattern: Nutenzugabe (groove allowance) -> Map to "coating" as requested
    if re.search(r'(?:^|[\s\-])NZG(?:[\s\-;,]|$)', text, re.IGNORECASE):
        if not any(f['spec'] == 'NZG' for f in features):
            features.append({"feature_type": "coating", "spec": "NZG"})
            
    return features


def extract_shaft_tolerance(text: str) -> Dict[str, str]:
    """
    Extracts shaft tolerance (h6, h7, h8) and determines which dimension it applies to.
    Handles both suffix (8h6x7x30) and prefix (h68x7x30, 8xh68x30) formats.
    
    Returns: {"spec": "h6", "position": "width"}
    """
    VALID_TOLERANCES = ["h6", "h7", "h8"]
    
    # --- SUFFIX patterns (tolerance AFTER the digit) ---
    
    # Suffix on HEIGHT: 8×7h7×30 (h7 after height digit)
    match = re.search(r'\d+(?:[.,]\d+)?\s*[xX]\s*\d+(?:[.,]\d+)?(h[678])\s*[xX]\s*\d+', text, re.IGNORECASE)
    if match:
        spec = match.group(1).lower()
        if spec in VALID_TOLERANCES:
            logger.info(f"Shaft tolerance '{spec}' detected (suffix on HEIGHT)")
            return {"spec": spec, "position": "height"}
    
    # Suffix on WIDTH: 8h6×7×30 (h6 after width digit, NOT preceded by xX)
    match = re.search(r'(?<![xX])\d+(?:[.,]\d+)?(h[678])\s*[xX]\s*\d+', text, re.IGNORECASE)
    if match:
        spec = match.group(1).lower()
        if spec in VALID_TOLERANCES:
            logger.info(f"Shaft tolerance '{spec}' detected (suffix on WIDTH)")
            return {"spec": spec, "position": "width"}
    
    # --- PREFIX patterns (tolerance BEFORE the digit) ---
    
    # Prefix on HEIGHT: 8xh68x30 (h6 before height digit, after x)
    match = re.search(r'\d+\s*[xX]\s*(h[678])\s*\d+\s*[xX]\s*\d+', text, re.IGNORECASE)
    if match:
        spec = match.group(1).lower()
        if spec in VALID_TOLERANCES:
            logger.info(f"Shaft tolerance '{spec}' detected (prefix on HEIGHT)")
            return {"spec": spec, "position": "height"}
    
    # Prefix on WIDTH: h68x7x30 (h6 before width digit, at start)
    match = re.search(r'(?:^|[\s\-])(h[678])\s*\d+\s*[xX]\s*\d+\s*[xX]\s*\d+', text, re.IGNORECASE)
    if match:
        spec = match.group(1).lower()
        if spec in VALID_TOLERANCES:
            logger.info(f"Shaft tolerance '{spec}' detected (prefix on WIDTH)")
            return {"spec": spec, "position": "width"}
    
    # --- STANDALONE (tolerance separated by space/letter, not glued to any digit) ---
    match = re.search(r'(?:^|[^\d])(h[678])(?:[^0-9xX]|$)', text, re.IGNORECASE)
    if match:
        spec = match.group(1).lower()
        if spec in VALID_TOLERANCES:
            logger.info(f"Shaft tolerance '{spec}' detected (standalone → defaults to WIDTH)")
            return {"spec": spec, "position": "width"}
    
    # Default: h9 on width
    return {"spec": "h9", "position": "width"}


def extract_heat_treatment(text: str) -> Optional[str]:
    """
    Extracts heat treatment designations like geh.50-55HRC, verg. Rm 900-1000 N/mm², nitriert, etc.
    Supports unitless ranges (geh.45-48), depth specs (0,3-0,5), and HRA.
    """
    # Pattern for ranges with optional units and optional case depth: geh. 50-55 HRC, verg. 900-1100, geh.56-60 0,3-0,5
    pattern = r'(?i)(?:geh\.?|verg\.?)\s*(?:Rm\s*)?(?:HRA\s*)?\d{1,4}(?:[-+]\d{1,4})?(?:\+/-?\d+)?\s*(?:HRC|HRA|HV\d*|N/mm²|%)?(?:\s*\d+,\d+-\d+,\d+)?'
    match = re.search(pattern, text)
    if match:
        extracted = match.group(0).strip()
        return extracted
    
    # Pattern for specific norms: geh. N533.05 or just N533
    norm_match = re.search(r'(?i)(geh\.?)\s*(?:n\.?\s*Norm\s*)?(N\d{3}(?:\.\d+)?)', text)
    if norm_match:
        # Return the whole string "geh. N533"
        return re.sub(r'\s+', ' ', norm_match.group(0).strip())
        
    # Sometimes it just says N533 standalone
    if re.search(r'(?i)\bN\d{3}(?:\.\d+)?\b', text):
        standalone_match = re.search(r'(?i)\bN\d{3}(?:\.\d+)?\b', text)
        # If it's standing alone, we still consider it a heat treatment norm
        return standalone_match.group(0).strip()
        
    # Generic prefix fallback if followed by nothing (only if isolated)
    generic_match = re.search(r'(?i)\b(geh\.|verg\.)(?:\s|$)', text)
    if generic_match:
        return generic_match.group(1).strip()
        
    return None

def extract_surface_treatment(text: str) -> Optional[str]:
    """
    Extracts surface treatments using a pattern dictionary and maps them to canonical forms.
    """
    mapping = {
        r'poliert': 'poliert',
        r'verzinkt': 'verzinkt',
        r'verz\.': 'verz.',
        r'VZ': 'VZ',
        r'brün\.': 'brün.',
        r'brüniert': 'Brüniert',
        r'Geomet321A': 'Geomet321A',
        r'geo\.': 'geo.',
        r'DBL': 'DBL',
        r'passiviert': 'passiviert',
        r'passiv\.': 'passiv.',
        r'vernickelt\s*DNC\s*520(?:-5[µu])?': 'vernickelt DNC 520-5µ',
        r'vernickelt': 'vernickelt',
        r'zink[\s\-]?nickel': 'Zink-Nickel',
        r'zink[\s\-]?nickl': 'Zink-Nickel',
        r'zinkphosphatiert': 'zinkphosphatiert',
        r'phosph\.': 'phosph',
        r'phosph': 'phosph',
        r'phos\.': 'phos.',
        r'PREN\s*>\s*40': 'PREN >40',
        r'\+?QT\s*800': 'QT 800',
        r'carbo(?:\.\s*\d+(?:-\d+)?)?(?:HRC)?': 'carbo',
        r'carb': 'carb',
        r'salzbad(?:nitrier(?:t|en|ung)?)?': 'salzbadnitriert',
        r'nitrier(?:t|en|ung)?': 'nitriert',
    }
    
    # We want to check longer patterns first so 'vernickelt DNC 520' matches before 'vernickelt'
    sorted_patterns = sorted(mapping.keys(), key=len, reverse=True)
    
    for pat in sorted_patterns:
        # Use boundary logic: 
        # (?:^|[\s,\-\+\.\(\[]) + pattern + (?:\s|$|,|\"|\*|\-|\)|\]|\.)
        regex = r'(?:^|[\s,\-\+\.\(\[])(' + pat + r')(?:\s|$|,|\"|\*|\-|\)|\]|\.)'
        match = re.search(regex, text, re.IGNORECASE)
        if match:
            return mapping[pat]
            
    return None

def extract_marking(text: str) -> Optional[str]:
    """
    Extracts marking designations using literal keywords.
    """
    mapping = {
        r'gek\.\s*DD': 'gek. DD',
        r'gekennz\.': 'gekennz.',
        r'Kennzeich\.': 'Kennzeich.',
        r'gekennzeichnet': 'gekennzeichnet',
        r'KZ': 'KZ'
    }
    
    sorted_patterns = sorted(mapping.keys(), key=len, reverse=True)
    
    for pat in sorted_patterns:
        regex = r'(?:^|[\s,\-\+\.\(\[])(' + pat + r')(?:\s|$|,|\"|\*|\-|\)|\]|\.)'
        match = re.search(regex, text, re.IGNORECASE)
        if match:
            return mapping[pat]
            
    return None


def calculate_confidence(item: Dict[str, Any], raw_text_snippet: str) -> float:
    """
    Calculates a rule-based confidence score (0.0 to 1.0) for an item.
    """
    score = 1.0
    issues = []
    
    config = item.get("config", {})
    
    # Check if raw_text_snippet is None or empty
    if not raw_text_snippet:
        return 0.5 # Default low confidence if no text to check against
    
    # 1. Check for NULL / Empty Dimensions (Passfeder MUST have dimensions)
    dims_in_json = config.get("dimensions", {}) or {}
    has_any_dim = any(v is not None and v != 0 for v in dims_in_json.values()) if dims_in_json else False
    
    if not has_any_dim:
        score -= 0.4
        issues.append("All dimensions are null/empty - Passfeder must have dimensions")
    
    # 1b. Check for Missing Dimensions if they seem present in text
    dims_in_text = parse_dimensions_from_string(raw_text_snippet)
    
    if dims_in_text and not has_any_dim:
        score -= 0.3
        issues.append("Dimensions found in text but missed in JSON")
        
    # 2. Check for Feature Mismatches (e.g. M-codes)
    text_features = extract_features_from_string(raw_text_snippet)
    json_features = config.get("features", [])
    
    for tf in text_features:
        if not any(jf.get("spec") == tf["spec"] for jf in json_features):
            score -= 0.2
            issues.append(f"Feature {tf['spec']} missed")
            
    # 3. Check for weird Form codes (single letters that might be dimensions labels)
    form = config.get("form", "")
    if form and len(form) == 1 and f"{form}=" in raw_text_snippet.replace(" ", ""):
        # e.g. Form="B" but text has "B=20"
        score -= 0.4
        issues.append(f"Form '{form}' matches dimension label pattern")
        
    # Check for Form/Dimension confusion (e.g., config has Form="B" but text has "B=...")
    if config.get("form") == "B" and "B=" in raw_text_snippet:
        score -= 0.4
        issues.append("Potential Form/Dimension confusion (Form B vs B=Width)")

    # Check for Invalid Materials (Strict Whitelist)
    # The whitelist logic: If a material is extracted, verify it against known valid codes.
    VALID_MATERIALS = ["C45", "C45+C", "C45K", "42CrMo4", "1.4301", "1.4305", "1.4571", "1.4404", "1.4057"]
    mat = config.get("material", "")
    if mat:
        # Check if it's a valid slash-separated combo or single value
        # Normalize by stripping spaces
        parts = [m.strip() for m in mat.split("/")]
        # If ANY part is invalid, penalize
        if not all(p in VALID_MATERIALS for p in parts):
            score -= 0.3
            issues.append(f"Invalid material detected: {mat}")

    # Check for Invalid M-Codes (Range M1 - M21)
    features = config.get("features", [])
    for feat in features:
        spec = feat.get("spec", "").strip().upper()
        if spec.startswith("M"):
            try:
                # Extract number part (e.g. "M6" -> 6, "M10X1" -> 10)
                # Handle standard threads "M6" and fine threads "M10x1"
                num_part = ""
                for char in spec[1:]:
                    if char.isdigit() or char == '.':
                        num_part += char
                    else:
                        break # Stop at 'x' or other non-digit
                
                if num_part:
                    val = float(num_part)
                    if not (1 <= val <= 21): # Strict Range M1 - M21
                        score -= 0.3
                        issues.append(f"M-code out of range (M1-M21): {spec}")
            except Exception:
                pass # Ignore parsing errors

    # 4. Check for Empty Form if "Form" keyword is in text
    if "Form" in raw_text_snippet and not form:
        score -= 0.1
        issues.append("Form keyword present but not extracted")

    if score < 1.0:
        logger.info(f"Validator Confidence Reduced for {item.get('pos')}: {score:.2f} -> Issues: {issues}")
        
    return max(0.0, score)


def validate_and_fix_items(items: List[Dict[str, Any]], native_text: str, ocr_text: str) -> List[Dict[str, Any]]:
    """
    Validates and overrides AI extracted items using strict Regex on the source text.
    Prioritizes native_text if available, falls back to ocr_text.
    Also appends 'metadata' with 'rule_confidence_score' and 'raw_text_snippet'.
    """
    source_text = native_text if native_text and len(native_text) > 20 else ocr_text
    
    # Split source text into lines for line-by-line searching
    source_lines = source_text.split('\n')
    
    for item in items:
        # Initialize metadata if not present
        if "metadata" not in item:
            item["metadata"] = {}
            
        try:
            pos = str(item.get("pos", "")).strip()
            article_name_ai = item.get("article_name", "")
            config = item.get("config", {})
            
            target_line = ""
            
            # 1. Attempt to find the RAW line in source_text
            # Grab the position line + 5 lines below (description, DIN code, EAN, etc.)
            if pos:
                for idx, line in enumerate(source_lines):
                    # distinct start of line check
                    if re.match(rf"^\s*{re.escape(pos)}\s+", line):
                        end_idx = min(len(source_lines), idx + 6)
                        context_lines = source_lines[idx:end_idx]
                        target_line = "\n".join(context_lines)
                        logger.info(f"Validator: Found raw context for Pos {pos} ({len(context_lines)} lines)")
                        break
            
            # Try searching by material_id (more unique than pos number)
            # IMPORTANT: material_id line is usually at the BOTTOM of a position block.
            # The actual product description (dimensions, form, material) is ABOVE it.
            # So we grab 5 lines above the match as context.
            if not target_line:
                mat_id = config.get("material_id", "")
                if mat_id and len(mat_id) > 5:
                    for idx, line in enumerate(source_lines):
                        if mat_id in line:
                            # Grab context: 5 lines above + the match line itself
                            start_idx = max(0, idx - 5)
                            context_lines = source_lines[start_idx:idx + 1]
                            target_line = "\n".join(context_lines)
                            logger.info(f"Validator: Found raw context by material_id for Pos {pos} ({len(context_lines)} lines)")
                            break
            
            if not target_line and article_name_ai:
                 parts = article_name_ai.split('-')
                 significant_parts = [p for p in parts if len(p) > 3]
                 
                 for line in source_lines:
                     if len(significant_parts) >= 2 and all(part in line for part in significant_parts):
                         target_line = line
                         break
            
            # If we still couldn't find the raw line, flag it
            used_fallback = False
            if target_line:
                text_to_scan = target_line
            elif article_name_ai:
                text_to_scan = article_name_ai
                used_fallback = True
                logger.warning(f"Validator: Could not find raw line for Pos {pos}, falling back to article_name (unreliable)")
            else:
                text_to_scan = ""
            
            # Store raw text snippet for the Verifier/Learner later
            item["metadata"]["raw_text_snippet"] = text_to_scan
            if used_fallback:
                item["metadata"]["snippet_is_fallback"] = True
            
            if not text_to_scan:
                # Default high confidence if we can't find source text to invalidate it?
                # No, standard 0.5 because we are flying blind.
                item["metadata"]["rule_confidence_score"] = 0.5
                continue

            # 2. FIX DIMENSIONS (Using strict regex on the SOURCE text)
            strict_dims = parse_dimensions_from_string(text_to_scan)
            if strict_dims and strict_dims.get("length"):
                 item_dims = config.get("dimensions", {}) or {}
                 # Only override checking if values differ significantly? 
                 # Trust Regex over AI for Dimensions.
                 config["dimensions"] = strict_dims
            
            # 3. FIX FEATURES (M-Codes) (Using strict regex on the SOURCE text)
            strict_features = extract_features_from_string(text_to_scan)
            current_features = config.get("features", [])
            for sf in strict_features:
                if not any(cf.get("spec") == sf["spec"] for cf in current_features):
                    current_features.append(sf)
            
            # 3a. EXTRACT SHAFT TOLERANCE (h6/h7/h8, default h9)
            shaft_tol = extract_shaft_tolerance(text_to_scan)
            # If we got the default h9 and the snippet was a fallback,
            # also try the full source_text — the tolerance might be elsewhere in the line
            if shaft_tol["spec"] == "h9" and source_text:
                shaft_tol_full = extract_shaft_tolerance(source_text)
                if shaft_tol_full["spec"] != "h9":
                    shaft_tol = shaft_tol_full
                    logger.info(f"Validator: Shaft tolerance found in full source text (fallback recovery)")
            # Remove any existing shaft tolerance feature to avoid duplicates
            current_features = [f for f in current_features if not (
                f.get("feature_type") == "tolerance" and f.get("spec", "").lower().startswith("h") and f.get("spec", "").lower() in ["h6", "h7", "h8", "h9"]
            )]
            current_features.append({
                "feature_type": "tolerance",
                "spec": shaft_tol["spec"],
                "position": shaft_tol["position"]
            })
            logger.info(f"Validator: Shaft tolerance for Pos {pos}: {shaft_tol['spec']} on {shaft_tol['position']}")
            
            config["features"] = current_features
            item["config"] = config
            
            # 3b. FIX MATERIAL (Hard auto-correct known bad values)
            raw_material = config.get("material", "")
            if raw_material:
                fixed_material = fix_material(raw_material)
                if fixed_material != raw_material:
                    config["material"] = fixed_material
                    item["config"] = config
                    item["metadata"]["material_auto_corrected"] = f"{raw_material} -> {fixed_material}"
            
            # 3c. EXTRACT FORM from raw text if AI missed it
            if not config.get("form") and text_to_scan:
                # Check for "DIN 6885 X" pattern (space separated)
                din_form_match = re.search(r'DIN\s*6885\s+([A-Z]{1,2})(?=\s|$)', text_to_scan, re.IGNORECASE)
                if din_form_match:
                    config["form"] = din_form_match.group(1).upper()
                    item["config"] = config
                    logger.info(f"Validator: Extracted Form '{config['form']}' from DIN pattern for Pos {pos}")
                else:
                    # Check common dash-separated forms
                    for form_candidate in ["AS", "AB", "A", "B", "C", "E", "D", "K"]:
                        if f"-{form_candidate}-" in text_to_scan or text_to_scan.startswith(f"{form_candidate}-"):
                            config["form"] = form_candidate
                            item["config"] = config
                            logger.info(f"Validator: Extracted Form '{form_candidate}' from raw text for Pos {pos}")
                            break
            
            # 3d. EXTRACT MATERIAL from raw text if AI missed it
            VALID_MATERIALS = ["C45+C", "C45K", "C45", "42CrMo4", "1.4301", "1.4305", "1.4571", "1.4404", "1.4057"]
            if not config.get("material") and text_to_scan:
                for mat in VALID_MATERIALS:
                    if mat in text_to_scan:
                        config["material"] = mat
                        item["config"] = config
                        logger.info(f"Validator: Extracted Material '{mat}' from raw text for Pos {pos}")
                        break
                # Also try common OCR misreads
                if not config.get("material"):
                    text_upper = text_to_scan.upper()
                    if "C45C" in text_upper or "C45+C" in text_upper:
                        config["material"] = "C45+C"
                        item["config"] = config
                    elif "C45K" in text_upper:
                        config["material"] = "C45K"
                        item["config"] = config
            
            # 3f. EXTRACT TREATMENTS AND ALWAYS OVERRIDE AI
            text_to_scan_fallback = text_to_scan or ""
            
            # Map surface treatment
            st = extract_surface_treatment(text_to_scan_fallback)
            if st:
                config["surface_treatment"] = st
                logger.info(f"Validator: Extracted Surface Treatment '{st}' for Pos {pos}")
            elif config.get("surface_treatment"):
                # If AI found it but text_to_scan didn't, try normalizing AI's value directly
                clean_st = extract_surface_treatment(config["surface_treatment"])
                if clean_st:
                    config["surface_treatment"] = clean_st

            # Map heat treatment
            ht = extract_heat_treatment(text_to_scan_fallback)
            if ht:
                config["heat_treatment"] = ht
                logger.info(f"Validator: Extracted Heat Treatment '{ht}' for Pos {pos}")
            elif config.get("heat_treatment"):
                # Check if AI put a Surface Treatment inside Heat Treatment (e.g. QT 800)
                ai_ht = config["heat_treatment"]
                clean_st = extract_surface_treatment(ai_ht)
                if clean_st:
                    config["surface_treatment"] = clean_st
                    config["heat_treatment"] = None
                    logger.info(f"Validator: Moved AI Heat Treatment '{ai_ht}' to Surface Treatment '{clean_st}'")
                else:
                    clean_ht = extract_heat_treatment(ai_ht)
                    if clean_ht:
                        config["heat_treatment"] = clean_ht
            
            # 3g. STRICTLY SANITIZE MARKING
            mk = extract_marking(text_to_scan_fallback)
            if mk:
                config["marking"] = mk
                logger.info(f"Validator: Found Explicit Marking '{mk}' for Pos {pos}")
            else:
                hallucinated = config.get("marking")
                if hallucinated:
                    clean_mk = extract_marking(hallucinated)
                    if clean_mk:
                        config["marking"] = clean_mk
                        logger.info(f"Validator: Cleaned AI Marking to '{clean_mk}' for Pos {pos}")
                    else:
                        logger.warning(f"Validator: Wiping out hallucinated marking '{hallucinated}' for Pos {pos}")
                        config["marking"] = None
            
            item["config"] = config

            # 3e. ALWAYS CONSTRUCT article_name — never send null
            dims = config.get("dimensions", {}) or {}
            form = config.get("form", "")
            material = config.get("material", "")
            features = config.get("features", [])
            
            # Build dimensions string
            dim_parts = []
            for key in ["width", "height", "length"]:
                v = dims.get(key)
                if v is not None:
                    dim_parts.append(str(int(v)) if float(v) == int(float(v)) else str(v))
            dim_str = "X".join(dim_parts) if dim_parts else ""
            
            # Build features string
            feat_str = "-".join([f.get("spec", "") for f in features if f.get("spec")]) if features else ""
            
            # Construct: PF-{Form}-{Dimensions}-{Material}-{Features}-{HeatTreatment}-{SurfaceTreatment}-{Marking}
            name_parts = ["PF"]
            if form:
                name_parts.append(form)
            if dim_str:
                name_parts.append(dim_str)
            if material:
                name_parts.append(material)
            if feat_str:
                name_parts.append(feat_str)
            if config.get("heat_treatment"):
                name_parts.append(config.get("heat_treatment"))
            if config.get("surface_treatment"):
                name_parts.append(config.get("surface_treatment"))
            if config.get("marking"):
                name_parts.append(config.get("marking"))
            
            constructed_name = "-".join(name_parts)
            
            # Only use constructed name if we have at least form or dimensions
            if len(name_parts) >= 3:  # PF + at least 2 more parts
                item["article_name"] = constructed_name
            elif not item.get("article_name"):
                item["article_name"] = constructed_name  # Even partial is better than null
            
            # 4. CALCULATE CONFIDENCE
            confidence = calculate_confidence(item, text_to_scan)
            
            # Extra penalty if we couldn't find the real raw line
            if used_fallback:
                confidence = min(confidence, 0.6)
                item["metadata"]["status"] = "raw_line_not_found"
            
            item["metadata"]["rule_confidence_score"] = confidence
            
        except Exception as e:
            logger.error(f"Validator failed for item {item.get('pos')}: {e}")
            continue
            
    return items
