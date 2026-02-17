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
    Extracts dimensions (LxWxH or WxHxL) from a string like '20x12x50'.
    Returns {width, height, length} or None.
    Assumes standard format: 'Width x Height x Length' or 'Dimension x Dimension x Dimension'.
    """
    # Pattern for 3 dimensions: 20x12x100 or 20X12X100
    # Allow spaces: 20 x 12 x 100
    pattern_3d = r'(\d+(?:[.,]\d+)?)\s*[xX]\s*(\d+(?:[.,]\d+)?)\s*[xX]\s*(\d+(?:[.,]\d+)?)'
    
    match = re.search(pattern_3d, text)
    if match:
        try:
            dims = [float(d.replace(',', '.')) for d in match.groups()]
            # Heuristic: Largest dimension is usually Length (unless specified otherwise)
            # But standard notation is often Width x Height x Length for keys vs bars.
            # Let's trust the sequence: Width, Height, Length
            return {
                "width": dims[0],
                "height": dims[1],
                "length": dims[2]
            }
        except ValueError:
            pass
            
    # Pattern for 2 dimensions: 20x12
    pattern_2d = r'(\d+(?:[.,]\d+)?)\s*[xX]\s*(\d+(?:[.,]\d+)?)'
    match = re.search(pattern_2d, text)
    if match:
        try:
            dims = [float(d.replace(',', '.')) for d in match.groups()]
            return {
                "width": dims[0],
                "height": dims[1],
                "length": None # Missing length
            }
        except ValueError:
            pass

    return None

def extract_features_from_string(text: str) -> List[Dict[str, str]]:
    """
    Extracts explicit features like M-codes (M6) from the string.
    """
    features = []
    
    # M-Code Pattern: M followed by digits (e.g., M6, M8, M10)
    # Using \b boundary to avoid matching inside other words, but typically M6 is standalone or hyphenated (-M6)
    # Handle -M6 pattern specifically or just M6
    m_code_pattern = r'(?:^|[\s\-])(M\d+)(?:[\s\-]|$)'
    
    m_matches = re.findall(m_code_pattern, text, re.IGNORECASE)
    for code in m_matches:
        # Avoid duplicates
        if not any(f['spec'] == code.upper() for f in features):
            features.append({"feature_type": "thread", "spec": code.upper()})
            
    return features


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
    
    # 1. Check for Missing Dimensions if they seem present in text
    dims_in_text = parse_dimensions_from_string(raw_text_snippet)
    dims_in_json = config.get("dimensions", {})
    
    if dims_in_text and not dims_in_json:
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
            if pos:
                for line in source_lines:
                    # distinct start of line check
                    if re.match(rf"^\s*{re.escape(pos)}\s+", line):
                        target_line = line
                        logger.info(f"Validator: Found raw line for Pos {pos}: {target_line.strip()[:50]}...")
                        break
            
            if not target_line and article_name_ai:
                 parts = article_name_ai.split('-')
                 significant_parts = [p for p in parts if len(p) > 3]
                 
                 for line in source_lines:
                     if len(significant_parts) >= 2 and all(part in line for part in significant_parts):
                         target_line = line
                         break
            
            text_to_scan = target_line if target_line else article_name_ai
            
            # Store raw text snippet for the Verifier/Learner later
            item["metadata"]["raw_text_snippet"] = text_to_scan
            
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
            
            config["features"] = current_features
            item["config"] = config
            
            # 3b. FIX MATERIAL (Hard auto-correct known bad values)
            raw_material = config.get("material", "")
            if raw_material:
                fixed_material = fix_material(raw_material)
                if fixed_material != raw_material:
                    config["material"] = fixed_material
                    item["config"] = config
                    # Also fix article_name if it contains the bad material
                    article_name = item.get("article_name", "")
                    if raw_material in article_name:
                        item["article_name"] = article_name.replace(raw_material, fixed_material)
                    item["metadata"]["material_auto_corrected"] = f"{raw_material} -> {fixed_material}"
            
            # 4. CALCULATE CONFIDENCE
            confidence = calculate_confidence(item, text_to_scan)
            item["metadata"]["rule_confidence_score"] = confidence
            
        except Exception as e:
            logger.error(f"Validator failed for item {item.get('pos')}: {e}")
            continue
            
    return items
