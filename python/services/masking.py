import re
import logging
import phonenumbers
from typing import Dict, List, Any, Tuple

logger = logging.getLogger(__name__)

# === HEADER EXTRACTION LOGIC (UNCHANGED) ===

class DocumentHeader:
    def __init__(self, supplier_name, customer_name, doc_type, date, customer_num, rfq_num):
        self.supplier_name = supplier_name
        self.customer_name = customer_name
        self.document_type = doc_type
        self.document_date = date
        self.customer_number = customer_num
        self.rfq_number = rfq_num

    def to_dict(self):
        return self.__dict__

def extract_document_header(text: str) -> DocumentHeader:
    """
    Extracts structured header data from raw text using Regex.
    Replicates services/pipeline/masking.ts:extractDocumentHeader
    """
    # Normalize whitespace
    normalized_text = re.sub(r'[ \t]+', ' ', text)
    
    # 1. Supplier Name (Hardcoded as requested)
    supplier_name = "Nosta GmbH"
    
    # 2. RFQ Number
    rfq_number = ""
    rfq_patterns = [
        r"(?:Nr\.|Nummer|Anfrage)\s*(\d{5,})",
        r"<NAnfrage\s+(\d+)\s*>",
        r"ANFRAGE\s+Nr\.?\s*(\d+)"
    ]
    for pattern in rfq_patterns:
        match = re.search(pattern, normalized_text, re.IGNORECASE)
        if match:
            rfq_number = match.group(1)
            break
            
    # 3. Date
    document_date = ""
    date_patterns = [
        r"Datum\s*[:.]?\s*(\d{2}[.\/]\d{2}[.\/]\d{4})",
        r"Date\s*[:.]?\s*(\d{4}-\d{2}-\d{2})",
        # ISO Date (YYYY-MM-DD) appearing anywhere
        r"(\d{4}-\d{2}-\d{2})"
    ]
    for pattern in date_patterns:
        match = re.search(pattern, normalized_text, re.IGNORECASE)
        if match:
            document_date = match.group(1)
            break
            
    # 4. Customer Number
    customer_number = ""
    cust_num_match = re.search(r"Lieferanten-?Nr\.?\s*[:.]?\s*(\d+)", normalized_text, re.IGNORECASE)
    if cust_num_match:
        customer_number = cust_num_match.group(1)
        
    # 5. Customer Name
    customer_name = ""
    customer_patterns = [
        r"\b(?:F\.\s*)?REYHER\b",
        r"([A-Z0-9äöüÄÖÜß][A-Za-z0-9äöüÄÖÜß.\-\s]+)\s+(GmbH\s*&\s*Co\.?\s*(?:KG|OHG))",
        r"([A-Z0-9äöüÄÖÜß][A-Za-z0-9äöüÄÖÜß.\-\s]+)\s+(GmbH|AG|Inc|LLC|Ltd)"
    ]
    
    for pattern in customer_patterns:
        matches = re.finditer(pattern, normalized_text, re.IGNORECASE)
        for match in matches:
            company_name = match.group(0).strip()
            if "nosta" in company_name.lower():
                continue
            if len(company_name) < 3:
                continue
                
            # Clean up artifacts like "Page 1 ---"
            clean_name = re.sub(r"^Page\s+\d+\s*[-]*\s*", "", company_name, flags=re.IGNORECASE)
            clean_name = re.sub(r"^Seite\s+\d+\s*[-]*\s*", "", clean_name, flags=re.IGNORECASE)
            customer_name = clean_name.strip()
            break
        if customer_name:
            break

    # 6. Doc Type
    doc_type = "RFQ"
    if re.search(r"BESTELLUNG|ORDER|PO\b", normalized_text, re.IGNORECASE):
        doc_type = "Purchase Order"
    elif re.search(r"ANFRAGE|RFQ|REQUEST", normalized_text, re.IGNORECASE):
        doc_type = "RFQ"
        
    return DocumentHeader(supplier_name, customer_name, doc_type, document_date, customer_number, rfq_number)


# === ENHANCED MASKING LOGIC (PORTED FROM TYPESCRIPT) ===

class RegexMasker:
    """
    Enhanced Masker porting the 'DataMasker' logic from TypeScript.
    Uses 'phonenumbers' (libphonenumber port) and regex fallbacks.
    Maintains counters for entities (EMAIL_1, COMPANY_1).
    """
    def __init__(self):
        self.token_map = {}
        self.counters = {
            "EMAIL": 0,
            "COMPANY": 0,
            "PERSON": 0,
            "ADDRESS": 0,
            "IBAN": 0
        }

    def _get_next_token(self, entity_type: str) -> str:
        self.counters[entity_type] += 1
        # Match TS format: {{EMAIL_1}}, {{COMPANY_1}}
        # But some generic ones might just be {{PHONE}} in the TS code?
        # The TS code uses {{PHONE}} generic, but EMAIL_N. We'll stick to TS style.
        if entity_type == "PHONE":
             return "{{PHONE}}"
        return f"{{{{{entity_type}_{self.counters[entity_type]}}}}}"

    def mask(self, text: str, header_values: List[str] = None) -> Tuple[str, Dict[str, str]]:
        # Normalize whitespace (TS: text.replace(/[ \t]+/g, ' '))
        masked_text = re.sub(r'[ \t]+', ' ', text)
        self.token_map = {}
        self.counters = {k:0 for k in self.counters}

        # 1. Header Hardening (Pre-mask known values)
        if header_values:
            for i, val in enumerate(header_values):
                if val and len(val) > 2:
                    token = f"{{{{HEADER_VAL_{i}}}}}"
                    if val in masked_text:
                        self.token_map[token] = val
                        masked_text = masked_text.replace(val, token)

        # 2. Mask Phone/Fax (Regex First - for German formats)
        # Porting TS patterns
        phone_patterns = [
            # Labeled
            r"((?:Telefax|Telefon|Tel|Fax|Phone|Mobil)[\s.:]*)([\d\s\/\-\+]+[\d]{4,})",
            # Standalone German local
            r"\b(\d{3,5}[\/-]\d{4,})\b",
            # International
            r"(\+\d{1,3}[\s\/-]?\d{2,4}[\s\/-]?\d{3,}[\s\/-]?\d{0,})"
        ]

        # Note: In Python regex, we must iterate carefully to avoid overlap.
        # Simple approach: applied sequentially.
        for idx, pattern in enumerate(phone_patterns):
            # We use finding iteration
            for match in re.finditer(pattern, masked_text, re.IGNORECASE):
                full_match = match.group(0)
                if "{{" in full_match: continue
                
                token = "{{PHONE}}"
                replacement = token
                
                # Logic from TS: Labeled patterns keep label
                if idx == 0 and match.lastindex and match.lastindex >= 2:
                    label = match.group(1)
                    number = match.group(2).strip()
                    if len(number) > 5:
                        self.token_map[token] = number # Note: map key is {{PHONE}}, overwrites previous. TS does this too.
                        replacement = label + token
                        masked_text = masked_text.replace(full_match, replacement)
                else:
                    if len(full_match) > 5:
                        self.token_map[token] = full_match
                        masked_text = masked_text.replace(full_match, replacement)

        # 3. Mask Known Companies (Blocklist)
        known_companies = ['Nosta GmbH', 'NOSTA', 'Nosta'] # Add Reyher if needed
        for company in known_companies:
            if re.search(re.escape(company), masked_text, re.IGNORECASE):
                 # Check if not already masked? Simplest is just replace.
                 # Python replace is case sensitive, regex sub is better
                 token = self._get_next_token("COMPANY")
                 self.token_map[token] = company
                 masked_text = re.sub(re.escape(company), token, masked_text, flags=re.IGNORECASE)

        # 4. Mask Emails
        email_regex = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
        emails = list(set(re.findall(email_regex, masked_text)))
        for email in emails:
            if "{{" in email: continue
            token = self._get_next_token("EMAIL")
            self.token_map[token] = email
            masked_text = masked_text.replace(email, token)

        # 5. International Phones (libphonenumber)
        try:
            for match in phonenumbers.PhoneNumberMatcher(masked_text, "DE"):
                number_str = masked_text[match.start:match.end]
                if "{{" in number_str: continue
                if len(number_str) < 6: continue
                
                token = "{{PHONE}}"
                self.token_map[token] = number_str
                # Replace exact occurrence
                # Be careful not to replace partials of other tokens
                masked_text = masked_text.replace(number_str, token)
        except Exception:
            pass # Ignore if parsing fails

        # 6. German Addresses (Regex)
        address_regex = r"([A-Za-zäöüÄÖÜß]+(?:straße|strasse|str\.|gasse|weg|platz|allee)\s*\d{1,4}[a-zA-Z]?)\s*,?\s*(\d{4,5})\s+([A-Za-zäöüÄÖÜß]+)"
        # Use finditer
        for match in re.finditer(address_regex, masked_text):
            full_match = match.group(0)
            if "{{" in full_match: continue
            
            token = self._get_next_token("ADDRESS")
            self.token_map[token] = full_match
            masked_text = masked_text.replace(full_match, token)

        # 7. IBAN
        iban_regex = r"\b([A-Z]{2}\d{2}[A-Z0-9]{10,30})\b"
        ibans = list(set(re.findall(iban_regex, masked_text)))
        for iban in ibans:
             if "{{" in iban: continue
             token = self._get_next_token("IBAN")
             self.token_map[token] = iban
             masked_text = masked_text.replace(iban, token)

        return masked_text, self.token_map

# Singleton
_masker = None
def get_masker():
    global _masker
    if not _masker:
        _masker = RegexMasker()
    return _masker

def process_document(text: str) -> Dict[str, Any]:
    header = extract_document_header(text)
    masker = get_masker()
    
    header_vals = [header.customer_name, header.rfq_number, header.customer_number]
    masked_text, token_map = masker.mask(text, header_vals)
    
    return {
        "header": header.to_dict(),
        "masked_text": masked_text,
        "token_map": token_map
    }
