import re
import logging
import json
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# ── Material Auto-Correction ──────────────────────────────────────────────────

# Full material catalog: name -> number
MATERIAL_NUMBER_MAP = {
    # Stainless Steel (density ~7.9-8.0)
    "X10CrNiS18-9": "1.4305",
    "X2CrNi18-9": "1.4307",
    "X2CrNiMo17-12-2": "1.4404",
    "X5CrNi18-9": "1.4301",
    "X5CrNiMo17-12-2": "1.4401",
    "X6CrNiMoTi17-12-2": "1.4571",
    "X2CrMoTi18-2": "1.4521",
    "X2CrTiNb18": "1.4509",
    "X6Cr17": "1.4016",
    "X17CrNi16-2": "1.4057",
    "X20Cr13": "1.4021",
    "X2CrNiMoN22-5-3": "1.4462",
    # Steel (density 7.85)
    "C40": "1.0511",
    "C45": "1.0503",
    "C45+C": "1.1191",
    "C45E": "1.1201",
    "C45R": None,
    "C50": "1.0540",
    "C50E": "1.1206",
    "C60E": "1.1221",
    "16MnCr5": "1.7131",
    "16MnCrS5": "1.7139",
    "17Cr3": "1.7016",
    "20MnCr5": "1.7147",
    "25CrMo4": "1.7218",
    "30CrMo4": "1.7216",
    "30CrNiMo8": "1.6580",
    "34CrMo4": "1.7220",
    "34CrNiMo6": "1.6582",
    "41Cr4": "1.7035",
    "42CrMo4": "1.7225",
    "100Cr6": "1.3505",
    "100CrMn6": "1.3520",
    "102Cr6": "1.2067",
    "95MnWCr5": "1.2510",
    "S235J2": "1.0038",
    "S235JR": "1.0044",
    "S275JR": "1.0117",
    "S355J2": "1.0577",
    "S355JR": "1.0045",
    "S355K2": "1.0596",
    "S420N": "1.8902",
    # Tool / High-Speed Steel
    "HS6-5-2": "1.3343",
    "HS2-9-1-8": "1.3247",
    "HS10-4-3-10": "1.3207",
    "X100CrMoV5": "1.2363",
    "X153CrMoV12": "1.2379",
    "X40CrMoV5-1": "1.2344",
    # International Standards
    "ASTM A36": None,
    "GB Q235": None,
    "JIS SCM440": None,
}

# Reverse lookup: number -> name (skip entries without a number)
NUMBER_TO_MATERIAL = {v: k for k, v in MATERIAL_NUMBER_MAP.items() if v}

# All valid material names AND numbers
VALID_MATERIALS = set(MATERIAL_NUMBER_MAP.keys()) | {v for v in MATERIAL_NUMBER_MAP.values() if v}

# Known bad -> correct mappings
MATERIAL_FIX_MAP = {
    # C45 variants all map to C45+C
    "1.0503": "C45+C",
    "C45E": "C45+C",
    "C45K": "C45+C",
    "C45C": "C45+C",
    "P5K": "C45+C",
    "P5C": "C45+C",
    "P85-C45K": "C45+C",
    "P885-C45C": "C45+C",
    "P885-C45+C": "C45+C",
    "P85-C45+C": "C45+C",
    "P85-C45C": "C45+C",
    "C60": "C60E",
    # Stainless keywords
    "VA": "1.4301",
    "STAINLESS": "1.4301",
    "EDELSTAHL": "1.4301",
    "ROSTFREI": "1.4301",
}

def fix_material(material: str) -> str:
    """
    Auto-corrects known bad material values.
    1. Check exact match in fix map
    2. Check if already valid (name or number)
    3. Try cleaning P-prefixes
    4. Check for DIN material number patterns (1.xxxx)
    5. Check for VA/STAINLESS keywords
    """
    if not material:
        return material
    
    material_clean = material.strip()
    
    # 1. Strip + suffixes (e.g. 1.4057+QT800+2H -> 1.4057), but keep C45+C
    if '+' in material_clean and material_clean.upper() != "C45+C":
        material_clean = material_clean.split('+')[0].strip()
        logger.info(f"Validator: Stripped '+' suffixes from material: '{material}' -> '{material_clean}'")
    elif material_clean.upper() == "C45+C":
        material_clean = "C45+C"

    # 2. Exact match in known fixes
    if material_clean in MATERIAL_FIX_MAP:
        fixed = MATERIAL_FIX_MAP[material_clean]
        logger.info(f"Material auto-corrected: '{material}' -> '{fixed}'")
        return fixed
    
    # 1a. Case-insensitive match in known fixes
    if material_clean.upper() in MATERIAL_FIX_MAP:
        fixed = MATERIAL_FIX_MAP[material_clean.upper()]
        logger.info(f"Material auto-corrected: '{material}' -> '{fixed}'")
        return fixed
    
    # 2. Already valid? (check both name and number)
    if material_clean in VALID_MATERIALS:
        return material_clean
    
    # 3. Try stripping common P-prefixes and re-checking
    cleaned = material_clean
    for prefix in ["P885-", "P85-", "PF-", "P5", "P8"]:
        if cleaned.upper().startswith(prefix.upper()):
            cleaned = cleaned[len(prefix):]
            break
    
    if cleaned in VALID_MATERIALS:
        logger.info(f"Material auto-corrected: '{material}' -> '{cleaned}'")
        return cleaned
    
    # 4. Check if it's "C45C" style (missing +)
    if re.match(r'^C45[A-Z]?$', cleaned, re.IGNORECASE):
        if cleaned.upper() == "C45C":
            logger.info(f"Material auto-corrected: '{material}' -> 'C45+C'")
            return "C45+C"
    
    # 5. Check for DIN material number pattern: 1.xxxx
    mat_num_match = re.search(r'(1\.\d{4})', material_clean)
    if mat_num_match:
        mat_num = mat_num_match.group(1)
        if mat_num in NUMBER_TO_MATERIAL or mat_num in VALID_MATERIALS:
            logger.info(f"Material recognized by DIN number: '{material}' -> '{mat_num}'")
            return mat_num
    
    # 6. Check for VA / STAINLESS keywords
    if material_clean.upper() in ["VA", "STAINLESS", "V2A", "V4A", "EDELSTAHL", "ROSTFREI"]:
        fixed = MATERIAL_FIX_MAP.get(material_clean.upper(), "1.4301")
        logger.info(f"Material keyword recognized: '{material}' -> '{fixed}'")
        return fixed
    
    # 7. Nothing worked, return original
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
    match = re.search(r'(\d+(?:[.,]\d+)?)\s*[xX]\s*[hH]\d+\s*(\d+(?:[.,]\d+)?)\s*[xX]\s*(\d+(?:[.,]\d+)?)', text)
    if match:
        try:
            dims = [float(d.replace(',', '.')) for d in match.groups()]
            return {"width": dims[0], "height": dims[1], "length": dims[2]}
        except ValueError:
            pass
    
    # 4. Prefix on WIDTH: h68x7x30 (h6 before width digit 8)
    match = re.search(r'[hH]\d+\s*(\d+(?:[.,]\d+)?)\s*[xX]\s*(\d+(?:[.,]\d+)?)\s*[xX]\s*(\d+(?:[.,]\d+)?)', text)
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


def extract_shaft_tolerance(text: str) -> List[Dict[str, str]]:
    """
    Extracts ALL shaft tolerances (h6, h7, h8). Any other h-tolerance (like h11)
    is mapping down to h9 implicitly. Determines which dimension it applies to.
    Handles both suffix (8h6x7x30) and prefix (h68x7x30, 8xh68x30) formats as well
    as double tolerances (8h8x7h8x30).
    
    Returns: [{"spec": "h6", "position": "width"}, ...]
    """
    VALID_TOLERANCES = ["h6", "h7", "h8"]
    found_tolerances = []
    
    def normalize_spec(spec: str) -> str:
        """Map h11, h10, h9 etc. to h9 if it's not strictly h6/h7/h8"""
        if spec in VALID_TOLERANCES:
            return spec
        return "h9"
    
    # Split the dimensions by 'x' or 'X'
    parts = re.split(r'[xX]', text)
    
    if len(parts) >= 1:
        # First chunk is the Width section (e.g. "8h8" or "h88" or "8")
        width_part = parts[0]
        match_w = re.search(r'(h\d+)', width_part, re.IGNORECASE)
        if match_w:
            spec = normalize_spec(match_w.group(1).lower())
            found_tolerances.append({"spec": spec, "position": "width"})
            logger.info(f"Shaft tolerance '{spec}' detected on WIDTH")
            
    if len(parts) >= 2:
        # Second chunk is the Height section (e.g. "7h8" or "h87" or "7")
        height_part = parts[1]
        match_h = re.search(r'(h\d+)', height_part, re.IGNORECASE)
        if match_h:
            spec = normalize_spec(match_h.group(1).lower())
            found_tolerances.append({"spec": spec, "position": "height"})
            logger.info(f"Shaft tolerance '{spec}' detected on HEIGHT")
            
    # Check for standalone tolerance ONLY if we found nothing in the chunks
    if not found_tolerances:
        match_standalone = re.search(r'(?:^|[^\d])(h\d+)(?:[^0-9xX]|$)', text, re.IGNORECASE)
        if match_standalone:
            spec = normalize_spec(match_standalone.group(1).lower())
            logger.info(f"Shaft tolerance '{spec}' detected (standalone → defaults to WIDTH)")
            found_tolerances.append({"spec": spec, "position": "width"})
        else:
            # Default: h9 on width
            found_tolerances.append({"spec": "h9", "position": "width"})
            
    return found_tolerances


def extract_heat_treatment(text: str) -> Optional[str]:
    """
    Extracts heat treatment designations like geh.50-55HRC, verg. Rm 900-1000 N/mm², nitriert, etc.
    Supports unitless ranges (geh.45-48), depth specs (EHT:0,3-0,5), HRA, HV10, and Standalone keywords.
    """
    # Expanded Pattern:
    # 1. Keywords: geh, verg, carbo, nitrieren, etc.
    # 2. Hardness specs: Rm, HRA, HV, HRC, N/mm2, %, +/- tolerances, ranges with -
    # 3. Case depth / EHT: EHT:0,3-0,5 or just 0,3-0,5
    # 4. Standalone keywords: Gehärtet, Wärmeb. etc.
    
    # Updated pattern components:
    # Keywords (LONGER/MORE SPECIFIC FIRST)
    kws = r'(?:Wärmebehandlung|Wärmeb\.?|Gehärtet|Vergütet|salzbadnitrier(?:t|en|ung)?|nitrier(?:t|en|ung)?|carbo?\.?|carb\b|geh\.?|verg\.?)'
    # Measurement types/Prefixes
    prefixes = r'(?:\s*(?:Rm\s*|HRA\s*|EHT\s*:?\s*|min\s*))?'
    # Value ranges/tolerances
    values = r'(?:\s*(?:\d+(?:[.,]\d+)?(?:[-+]\d+(?:[.,]\d+)?)?(?:\+/-?\d+)?))?'
    # Units
    units = r'(?:\s*(?:HRC|HRA|HV\d*|N/mm²|%))?'
    # Secondary specs (EHT suffix) - Allows optional comma
    suffix = r'(?:\s*,?\s*EHT\s*:?\s*\d+(?:[.,]\d+)?(?:[-+]\d+(?:[.,]\d+)?)?)?'
    
    pattern = r'(?i)' + kws + prefixes + values + units + suffix
    
    match = re.search(pattern, text)
    if match:
        extracted = match.group(0).strip()
        # Heuristic: must be longer than 1 char and not just a space
        if len(extracted) > 1:
            return extracted
    
    # Pattern for specific norms: geh. N533.05 or just N533
    norm_match = re.search(r'(?i)(geh\.?|Wärmebehandlung|Wärmeb\.?|Gehärtet)\s*(?:n\.?\s*Norm\s*)?(N\d{3}(?:\.\d+)?)', text)
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
        r'Oberflächenbehandlung': 'Oberflächenbehandlung',
        r'Oberfläche': 'Oberfläche',
        r'Oberfl\.': 'Oberfl.',
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
    }
    
    # Move generic headers to the end of the search list to prioritize specific treatments
    generic_headers = {r'Oberflächenbehandlung', r'Oberfläche', r'Oberfl\.'}
    sorted_patterns = sorted([p for p in mapping.keys() if p not in generic_headers], key=len, reverse=True)
    sorted_patterns += sorted(list(generic_headers), key=len, reverse=True)
    
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
    # 0. Strict Blacklist: IGNORE packaging codes like VP100, VP200, etc.
    if re.search(r'(?i)\bVP\d+\b', text):
        return None

    mapping = {
        r'gek\.\s*DD': 'gek. DD',
        r'gekennz\.': 'gekennz.',
        r'Kennzeich\.': 'Kennzeich.',
        r'gekennzeichnet': 'gekennzeichnet',
        r'KZ': 'KZ',
        r'KX': 'KX',
        r'SS': 'SS',
        r'HC': 'HC',
        r'T': 'T',
        r'Ken\.': 'Ken.',
        r'Kennz\.': 'Kennz.'
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
    issues: List[str] = []
    penalties: List[float] = []

    config = item.get("config", {})

    # Check if raw_text_snippet is None or empty
    if not raw_text_snippet:
        return 0.5  # Default low confidence if no text to check against

    snippet: str = str(raw_text_snippet)

    # 1. Check for NULL / Empty Dimensions (Passfeder MUST have dimensions)
    dims_in_json = config.get("dimensions", {}) or {}
    has_any_dim = any(v is not None and v != 0 for v in dims_in_json.values()) if dims_in_json else False

    if not has_any_dim:
        penalties.append(0.4)
        issues.append("All dimensions are null/empty - Passfeder must have dimensions")

    # 1b. Check for Missing Dimensions if they seem present in text
    dims_in_text = parse_dimensions_from_string(snippet)

    if dims_in_text and not has_any_dim:
        penalties.append(0.3)
        issues.append("Dimensions found in text but missed in JSON")

    # 2. Check for Feature Mismatches (e.g. M-codes)
    text_features = extract_features_from_string(snippet)
    json_features = config.get("features", [])

    for tf in text_features:
        if not any(jf.get("spec") == tf["spec"] for jf in json_features):
            penalties.append(0.2)
            issues.append(f"Feature {tf['spec']} missed")

    # 3. Check for weird Form codes (single letters that might be dimension labels)
    form = config.get("form", "")
    if form and form.upper() not in {"A", "B", "C", "D", "E", "F", "AB", "AS", "BS", "ABS", "CD", "EF", "K"}:
        penalties.append(0.3)
        issues.append(f"Invalid Form extracted: {form}")

    if form and len(form) == 1 and f"{form}=" in snippet.replace(" ", ""):
        penalties.append(0.4)
        issues.append(f"Form '{form}' matches dimension label pattern")

    # Check for Form/Dimension confusion (e.g., config has Form="B" but text has "B=...")
    if config.get("form") == "B" and "B=" in snippet:
        penalties.append(0.4)
        issues.append("Potential Form/Dimension confusion (Form B vs B=Width)")

    # Check for Invalid Materials (Strict Whitelist)
    VALID_MATERIALS_CHECK = ["C45", "C45+C", "C45K", "42CrMo4", "1.4301", "1.4305", "1.4571", "1.4404", "1.4057"]
    mat = config.get("material", "")
    if mat:
        parts = [m.strip() for m in str(mat).split("/")]
        if not all(p in VALID_MATERIALS_CHECK for p in parts):
            penalties.append(0.3)
            issues.append(f"Invalid material detected: {mat}")

    # Check for Invalid M-Codes (Range M1 - M21)
    features = config.get("features", [])
    for feat in features:
        spec_raw: str = str(feat.get("spec", ""))
        spec: str = spec_raw.strip().upper()
        if spec.startswith("M"):
            try:
                spec_tail: str = spec.replace("M", "", 1)  # avoids Pyre2 indexing bug
                num_part = ""
                for char in spec_tail:
                    if char.isdigit() or char == '.':
                        num_part += char
                    else:
                        break
                if num_part:
                    val = float(num_part)
                    if not (1 <= val <= 21):
                        penalties.append(0.3)
                        issues.append(f"M-code out of range (M1-M21): {spec}")
            except Exception:
                pass

    # 4. Check for Empty Form if "Form" keyword is in text
    if "Form" in snippet and not form:
        penalties.append(0.1)
        issues.append("Form keyword present but not extracted")

    total_penalty: float = sum(penalties)
    score: float = max(0.0, 1.0 - total_penalty)

    if issues:
        logger.info(f"Validator Confidence Reduced for {item.get('pos')}: {score:.2f} -> Issues: {issues}")

    return score


def validate_and_fix_items(items: List[Dict[str, Any]], native_text: str, ocr_text: str) -> List[Dict[str, Any]]:
    """
    OPTIMIZED: Validates and overrides AI extracted items using strict Regex on the source text.
    Uses indexing to avoid O(N^2) search complexity.
    """
    source_text = native_text if native_text and len(native_text) > 20 else ocr_text
    if not source_text:
        return items

    source_lines = [line.strip() for line in source_text.split('\n') if line.strip()]
    
    # 1. PRE-INDEXING: Map Pos Numbers and Material IDs to line indices for O(1) lookup
    pos_index = {}
    mat_id_index = {}
    dim_index = {} # width_height -> line_index

    for idx, line in enumerate(source_lines):
        # Index by Pos (e.g. "Pos 1" or "1.")
        pos_match = re.match(r'^(?:Pos\.?|Position)?\s*(\d+)[\.\s]', line, re.IGNORECASE)
        if pos_match:
            pos_index[pos_match.group(1)] = idx
        
        # Index by Material ID (Format: 100-xxx-xxx.xx-xx)
        mat_id_match = re.search(r'(100-\d{3}-\d{3}\.\d{2}-\d{2})', line)
        if mat_id_match:
            mat_id_index[mat_id_match.group(1)] = idx

        # Index by Dimensions (Standard 20x12x50)
        dims = parse_dimensions_from_string(line)
        if dims:
             key = f"{dims.get('width')}_{dims.get('height')}"
             if key not in dim_index: dim_index[key] = []
             dim_index[key].append(idx)

    # 2. Sequential Mapping Fallback Pre-calc
    product_lines = [line for line in source_lines if re.search(r'\d+\s*[xX]\s*\d+', line) or "DIN" in line.upper() or "PF" in line.upper()]
    is_safe_to_sequence = len(product_lines) == len(items) and not pos_index

    # 3. Item Processing Loop
    for i, item in enumerate(items):
        if "metadata" not in item: item["metadata"] = {}
        
        try:
            pos = str(item.get("pos", "")).strip()
            config = item.get("config", {})
            mat_id = config.get("material_id", "")
            
            target_line_idx = -1
            
            # FAST LOOKUPS
            if mat_id in mat_id_index:
                target_line_idx = mat_id_index[mat_id]
            elif pos in pos_index:
                target_line_idx = pos_index[pos]
            elif config.get("dimensions"):
                # Fuzzy match by width/height if only one such line exists in the doc
                d = config["dimensions"]
                dk = f"{d.get('width')}_{d.get('height')}"
                if dk in dim_index and len(dim_index[dk]) == 1:
                    target_line_idx = dim_index[dk][0]
            
            if target_line_idx == -1 and is_safe_to_sequence:
                # O(1) sequential access as last resort
                target_line = product_lines[i]
                target_line_idx = -2 # special flag
            
            # Context construction
            text_to_scan = ""
            if target_line_idx >= 0:
                # Grab a window of context (up to 3 lines above/below)
                start_context = max(0, target_line_idx - 2)
                end_context = min(len(source_lines), target_line_idx + 10)
                text_to_scan = "\n".join(source_lines[start_context:end_context])
            elif target_line_idx == -2:
                text_to_scan = target_line
            else:
                # Fallback to article name if absolutely nothing else
                text_to_scan = item.get("article_name", "")
                item["metadata"]["snippet_is_fallback"] = True

            item["metadata"]["raw_text_snippet"] = text_to_scan

            if not text_to_scan:
                item["metadata"]["rule_confidence_score"] = 0.5
                continue

            # --- Apply Fixes (Dimensions, Features, Material, Form, Treatments) ---
            # (Reuse existing logic but on the smaller targeted text_to_scan)
            
            # Dimensions
            strict_dims = parse_dimensions_from_string(text_to_scan)
            if strict_dims and strict_dims.get("length"):
                config["dimensions"] = strict_dims

            # Features (M-Codes, NZG)
            strict_features = extract_features_from_string(text_to_scan)
            current_features = config.get("features", [])
            for sf in strict_features:
                if not any(cf.get("spec") == sf["spec"] for cf in current_features):
                    current_features.append(sf)
            
            # Shaft Tolerances
            shaft_tols = extract_shaft_tolerance(text_to_scan)
            current_features = [f for f in current_features if not (
                f.get("feature_type") == "tolerance" and f.get("spec", "").lower().startswith("h")
            )]
            for tol in shaft_tols:
                current_features.append({"feature_type": "tolerance", "spec": tol["spec"], "position": tol["position"]})
            config["features"] = current_features

            # Material Recovery (If AI missed it)
            raw_material = config.get("material", "")
            if raw_material:
                config["material"] = fix_material(raw_material)
            else:
                # Recovery loop for materials
                SEARCH_MATERIALS = ["C45+C", "C45K", "C45", "42CrMo4", "1.4301", "1.4305", "1.4571", "1.4404", "1.4057"]
                for mat in SEARCH_MATERIALS:
                    if mat in text_to_scan:
                        config["material"] = mat
                        logger.info(f"Validator: Recovered Material '{mat}' for Pos {pos}")
                        break
                # Common OCR/Hallucination fixes
                if not config.get("material"):
                    tu = text_to_scan.upper()
                    if "C45+C" in tu or "C45C" in tu: config["material"] = "C45+C"
                    elif "C45K" in tu: config["material"] = "C45K"
            
            # Form Sanitization & Recovery
            VALID_FORMS = {"A", "B", "C", "D", "E", "F", "AB", "AS", "BS", "ABS", "CD", "EF", "K"}
            current_form = config.get("form", "").strip().upper() if config.get("form") else ""
            if current_form and current_form not in VALID_FORMS:
                 logger.warning(f"Validator: Invalid Form '{current_form}' - stripping.")
                 config["form"] = None
            
            if not config.get("form"):
                 # Recovery loop for forms (check boundaries)
                 for f_cand in sorted(list(VALID_FORMS), key=len, reverse=True):
                     # Match -Form- or DIN 6885 Form
                     if f"-{f_cand}-" in text_to_scan or text_to_scan.startswith(f"{f_cand}-") or f"DIN 6885 {f_cand}" in text_to_scan.upper():
                         config["form"] = f_cand
                         logger.info(f"Validator: Recovered Form '{f_cand}' for Pos {pos}")
                         break

            # Treatments (Override AI)
            st = extract_surface_treatment(text_to_scan)
            config["surface_treatment"] = st
            
            ht = extract_heat_treatment(text_to_scan)
            config["heat_treatment"] = ht

            # --- DANGER CLEANUP: Purge duplicate "coating" features if they match treatments ---
            # If AI extracted "nitriert" as a feature of type "coating", but it's now in heat_treatment, remove it.
            if config.get("features"):
                final_features = []
                for feat in config["features"]:
                    spec = str(feat.get("spec", "")).strip().lower()
                    # Skip if it's a duplication of HT or ST
                    if ht and spec in str(ht).lower():
                         continue
                    if st and spec in str(st).lower():
                         continue
                    final_features.append(feat)
                config["features"] = final_features

            # Marking
            mk = extract_marking(text_to_scan)
            if mk: config["marking"] = mk
            else: config["marking"] = None if config.get("marking") and not extract_marking(config["marking"]) else config.get("marking")

            item["config"] = config

            # Article Name Reconstruction
            dims = config.get("dimensions", {}) or {}
            d_str = "X".join([str(int(v)) if float(v) == int(float(v)) else str(v) for v in [dims.get("width"), dims.get("height"), dims.get("length")] if v])
            f_str = "-".join([f["spec"] for f in config.get("features", []) if f.get("spec")])
            parts = ["PF", config.get("form"), d_str, config.get("material"), f_str, config.get("heat_treatment"), config.get("surface_treatment"), config.get("marking")]
            item["article_name"] = "-".join([p for p in parts if p])

            item["metadata"]["rule_confidence_score"] = calculate_confidence(item, text_to_scan)

        except Exception as e:
            logger.error(f"Validator failed for Pos {item.get('pos')}: {e}")
            continue
            
    return items
