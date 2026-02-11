import re
import logging
import json
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

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

def validate_and_fix_items(items: List[Dict[str, Any]], native_text: str, ocr_text: str) -> List[Dict[str, Any]]:
    """
    Validates and overrides AI extracted items using strict Regex on the source text.
    Prioritizes native_text if available, falls back to ocr_text.
    """
    source_text = native_text if native_text and len(native_text) > 20 else ocr_text
    
    # Split source text into lines for line-by-line searching
    source_lines = source_text.split('\n')
    
    for item in items:
        try:
            pos = str(item.get("pos", "")).strip()
            article_name_ai = item.get("article_name", "")
            config = item.get("config", {})
            
            target_line = ""
            
            # 1. Attempt to find the RAW line in source_text using Position
            # We look for a line starting with the position number (e.g. "12 " or "012")
            if pos:
                for line in source_lines:
                    # distinct start of line check, handling potential leading spaces
                    if re.match(rf"^\s*{re.escape(pos)}\s+", line):
                        target_line = line
                        logger.info(f"Validator: Found raw line for Pos {pos}: {target_line.strip()[:50]}...")
                        break
            
            # Fallback: If no Pos match, or Pos is empty, check if Article Name exists in a line
            if not target_line and article_name_ai:
                 # Try to find a line containing a significant chunk of the article name
                 # e.g. "DIN6885" and "20X12X50"
                 parts = article_name_ai.split('-')
                 significant_parts = [p for p in parts if len(p) > 3]
                 
                 for line in source_lines:
                     if len(significant_parts) >= 2 and all(part in line for part in significant_parts):
                         target_line = line
                         break
            
            # If we STILL don't have a raw line, fallback to checking the AI's article_name string
            # This is the "better than nothing" check we had before
            text_to_scan = target_line if target_line else article_name_ai
            
            if not text_to_scan:
                continue

            # 2. FIX DIMENSIONS (Using strict regex on the SOURCE text)
            strict_dims = parse_dimensions_from_string(text_to_scan)
            
            if strict_dims and strict_dims.get("length"):
                 item_dims = config.get("dimensions", {}) or {}
                 # Only override checking if values differ significantly? 
                 # No, trust Regex over AI for Dimensions.
                 logger.info(f"Validator: Forcing dimensions {strict_dims} from source text")
                 config["dimensions"] = strict_dims
            
            # 3. FIX FEATURES (M-Codes) (Using strict regex on the SOURCE text)
            strict_features = extract_features_from_string(text_to_scan)
            
            current_features = config.get("features", [])
            for sf in strict_features:
                if not any(cf.get("spec") == sf["spec"] for cf in current_features):
                    logger.info(f"Validator: Found missing feature {sf} in source text")
                    current_features.append(sf)
            
            config["features"] = current_features
            item["config"] = config
            
        except Exception as e:
            logger.error(f"Validator failed for item {item.get('pos')}: {e}")
            continue
            
    return items
