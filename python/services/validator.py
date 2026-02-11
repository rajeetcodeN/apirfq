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
    
    for item in items:
        # Get the Article Name / Description extracted by AI
        # (We assume the AI gets the *string* mostly right, or we scan the whole text line)
        try:
            article_name = item.get("article_name", "")
            config = item.get("config", {})
            
            if not article_name:
                continue
                
            # 1. FIX DIMENSIONS
            # Check if strict dimensions exist in the article name string
            strict_dims = parse_dimensions_from_string(article_name)
            
            if strict_dims and strict_dims.get("length"):
                 # Override AI's dimensions with strict regex dimensions
                 # This fixes the "Length 100" vs "Length 50" issue
                 item_dims = config.get("dimensions", {}) or {}
                 
                 # Only override not-null values or distinct values
                 # Actually, FORCE override for Length if regex is confident
                 logger.info(f"Validator: Forcing dimensions {strict_dims} over {item_dims}")
                 
                 config["dimensions"] = strict_dims
            
            # 2. FIX FEATURES (M-Codes)
            # Scan article name for M-codes
            strict_features = extract_features_from_string(article_name)
            
            current_features = config.get("features", [])
            for sf in strict_features:
                # Add if missing
                if not any(cf.get("spec") == sf["spec"] for cf in current_features):
                    logger.info(f"Validator: Adding missing feature {sf}")
                    current_features.append(sf)
            
            config["features"] = current_features
            item["config"] = config
            
        except Exception as e:
            logger.error(f"Validator failed for item: {e}")
            continue
            
    return items
