import re
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Known Column Keywords (German + English) ──────────────────────────────────
# Maps raw header text to a semantic label the AI can understand
COLUMN_KEYWORDS = {
    # Quantity (USE this)
    "menge": {"label": "QUANTITY (use this for quantity)", "priority": "high"},
    "qty": {"label": "QUANTITY (use this for quantity)", "priority": "high"},
    "quantity": {"label": "QUANTITY (use this for quantity)", "priority": "high"},
    "bestellmenge": {"label": "QUANTITY (use this for quantity)", "priority": "high"},
    "stück": {"label": "QUANTITY (use this for quantity)", "priority": "high"},
    "stk": {"label": "QUANTITY (use this for quantity)", "priority": "high"},
    
    # VPE (IGNORE for quantity)
    "vpe": {"label": "PACKAGING UNIT (ignore for quantity)", "priority": "high"},
    "verpackungseinheit": {"label": "PACKAGING UNIT (ignore for quantity)", "priority": "high"},
    "pack": {"label": "PACKAGING UNIT (ignore for quantity)", "priority": "high"},
    
    # Position
    "pos": {"label": "POSITION NUMBER", "priority": "medium"},
    "pos.": {"label": "POSITION NUMBER", "priority": "medium"},
    "position": {"label": "POSITION NUMBER", "priority": "medium"},
    "lfd": {"label": "POSITION NUMBER", "priority": "medium"},
    
    # Material/Article
    "material": {"label": "MATERIAL DESCRIPTION", "priority": "medium"},
    "materialnr": {"label": "MATERIAL NUMBER", "priority": "medium"},
    "artikel": {"label": "ARTICLE NAME", "priority": "medium"},
    "artikelnr": {"label": "ARTICLE NUMBER", "priority": "medium"},
    "bezeichnung": {"label": "DESCRIPTION", "priority": "medium"},
    
    # Price
    "preis": {"label": "UNIT PRICE", "priority": "medium"},
    "price": {"label": "UNIT PRICE", "priority": "medium"},
    "einzelpreis": {"label": "UNIT PRICE", "priority": "medium"},
    "preiseinheit": {"label": "PRICE UNIT (per 100, per 1000 etc)", "priority": "medium"},
    "pe": {"label": "PRICE UNIT", "priority": "medium"},
    
    # Total
    "nettowert": {"label": "NET VALUE (total line amount)", "priority": "medium"},
    "gesamtpreis": {"label": "TOTAL PRICE", "priority": "medium"},
    "betrag": {"label": "AMOUNT", "priority": "medium"},
    "netto": {"label": "NET VALUE", "priority": "medium"},
    
    # Delivery
    "liefertermin": {"label": "DELIVERY DATE", "priority": "medium"},
    "lieferdatum": {"label": "DELIVERY DATE", "priority": "medium"},
    "termin": {"label": "DELIVERY DATE", "priority": "medium"},
    "bereitstellungsdatum": {"label": "DELIVERY DATE", "priority": "medium"},
    
    # Unit
    "einheit": {"label": "UNIT OF MEASURE", "priority": "low"},
    "me": {"label": "UNIT OF MEASURE", "priority": "low"},
    "eur": {"label": "CURRENCY", "priority": "low"},
}


def detect_column_headers(text: str) -> str:
    """
    Analyzes OCR text to find the column header row and returns
    a structured hint string for the AI prompt.
    
    Returns a string like:
    "DETECTED COLUMNS: Col1=POSITION NUMBER, Col2=MATERIAL DESCRIPTION, 
     Col3=PACKAGING UNIT (ignore for quantity), Col4=QUANTITY (use this for quantity)"
    """
    if not text:
        return ""
    
    lines = text.split('\n')
    
    # Strategy: Find the line with the most column keyword matches
    best_line = ""
    best_score = 0
    best_matches = []
    
    for line in lines[:30]:  # Only scan first 30 lines (headers are at the top)
        line_clean = line.strip()
        if not line_clean or len(line_clean) < 5:
            continue
        
        matches = _find_keywords_in_line(line_clean)
        score = len(matches)
        
        # Bonus for high-priority matches
        for m in matches:
            if m["priority"] == "high":
                score += 2
        
        if score > best_score:
            best_score = score
            best_line = line_clean
            best_matches = matches
    
    if best_score < 2:
        # Not enough confidence that we found a header row
        logger.info("Column detector: No clear header row found")
        return ""
    
    # Build the hint string
    logger.info(f"Column detector: Found header row: '{best_line[:80]}...'")
    
    hint = "\n\n📊 DETECTED COLUMN HEADERS FROM DOCUMENT:\n"
    hint += f"Header row: \"{best_line}\"\n"
    hint += "Column mapping:\n"
    
    for i, match in enumerate(best_matches):
        hint += f"  - \"{match['keyword']}\" = {match['label']}\n"
    
    # Add critical reminders based on what we found
    has_vpe = any(m["keyword"].lower() in ["vpe", "verpackungseinheit"] for m in best_matches)
    has_menge = any(m["keyword"].lower() in ["menge", "qty", "quantity", "bestellmenge", "stück", "stk"] for m in best_matches)
    
    if has_vpe and has_menge:
        hint += "\n⚠️ CRITICAL: This document has BOTH 'VPE' and 'Menge' columns.\n"
        hint += "  - Use 'Menge' for quantity.\n"
        hint += "  - 'VPE' is packaging unit — IGNORE it for quantity.\n"
    elif has_vpe and not has_menge:
        hint += "\n⚠️ WARNING: Only 'VPE' found. Look for a separate quantity/Menge column.\n"
    
    has_pe = any(m["keyword"].lower() in ["preiseinheit", "pe"] for m in best_matches)
    if has_pe:
        hint += "  - 'Preiseinheit'/'PE' = price per X units (e.g., per 100). Use this context.\n"
    
    return hint


def _find_keywords_in_line(line: str) -> List[Dict]:
    """Find all known column keywords in a single line."""
    matches = []
    line_lower = line.lower()
    
    # Split by common delimiters (tabs, multiple spaces, pipes)
    # But also check the whole line for keywords
    words = re.split(r'[\t|]+|\s{2,}', line_lower)
    words = [w.strip() for w in words if w.strip()]
    
    seen_labels = set()
    
    for word in words:
        # Check each word against our keyword map
        # Also check partial matches (e.g., "materialnr." should match "materialnr")
        clean_word = word.strip('.,:;/\\')
        
        if clean_word in COLUMN_KEYWORDS:
            info = COLUMN_KEYWORDS[clean_word]
            if info["label"] not in seen_labels:
                matches.append({
                    "keyword": word,
                    "label": info["label"],
                    "priority": info["priority"]
                })
                seen_labels.add(info["label"])
    
    return matches
