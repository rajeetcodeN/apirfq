
import re
import logging
from typing import Dict, List, Any, Tuple
from presidio_analyzer import AnalyzerEngine, RecognizerResult, PatternRecognizer, Pattern
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

logger = logging.getLogger(__name__)

# === HEADER EXTRACTION LOGIC ===

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
    
    # 1. Supplier Name (Hardcoded)
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
        r"Date\s*[:.]?\s*(\d{4}-\d{2}-\d{2})"
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


# === MASKING LOGIC ===

class PIIMasker:
    def __init__(self):
        # Configure Presidio to use Spacy (German)
        # Note: Requires `python -m spacy download de_core_news_lg`
        nlp_config = {
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "de", "model_name": "de_core_news_sm"},
                       {"lang_code": "en", "model_name": "en_core_web_lg"}] 
        }
        provider = NlpEngineProvider(nlp_configuration=nlp_config)
        
        try:
            self.nlp_engine = provider.create_engine()
            self.analyzer = AnalyzerEngine(nlp_engine=self.nlp_engine, supported_languages=["de", "en"])
            self.nlp_available = True
        except OSError:
            logger.warning("Spacy models not found. Falling back to Regex-only mode. Run `python -m spacy download de_core_news_sm`")
            self.analyzer = AnalyzerEngine() # Default config
            self.nlp_available = False

        self.anonymizer = AnonymizerEngine()
        self._add_custom_recognizers()

    def _add_custom_recognizers(self):
        """Adds specific Regex patterns from the original TypeScript code."""
        
        # 1. German Address Pattern (Street Number, Zip City)
        # Regex: ([A-Za-zäöüÄÖÜß]+(?:straße|strasse|str\.|gasse|weg|platz|allee)\s*\d{1,4}[a-zA-Z]?)\s*,?\s*(\d{4,5})\s+([A-Za-zäöüÄÖÜß]+)
        address_pattern = Pattern(
            name="german_address_pattern",
            regex=r"([A-Za-zäöüÄÖÜß]+(?:straße|strasse|str\.|gasse|weg|platz|allee)\s*\d{1,4}[a-zA-Z]?)\s*,?\s*(\d{4,5})\s+([A-Za-zäöüÄÖÜß]+)",
            score=0.85
        )
        address_recognizer = PatternRecognizer(
            supported_entity="GERMAN_ADDRESS",
            patterns=[address_pattern],
            supported_language="de"
        )
        self.analyzer.registry.add_recognizer(address_recognizer)

        # 2. Specific Company Blocklist (Nosta, Reyher)
        company_pattern = Pattern(
            name="company_blocklist",
            regex=r"(?i)\b(Nosta\s*GmbH|NOSTA|Reyher|F\.\s*Reyher)\b",
            score=1.0
        )
        company_recognizer = PatternRecognizer(
            supported_entity="BLOCKED_COMPANY",
            patterns=[company_pattern],
            supported_language="de"
        )
        self.analyzer.registry.add_recognizer(company_recognizer)
        
        # 3. German Phone Formats
        # 09074/42117 or +49 ...
        phone_pattern = Pattern(
            name="german_phone_custom",
            regex=r"((?:Telefax|Telefon|Tel|Fax|Phone)[\s.:]*)([\d\s\/\-\+]+[\d]{4,})|\b(\d{3,5}[\/-]\d{4,})\b",
            score=0.7
        )
        phone_recognizer = PatternRecognizer(
            supported_entity="PHONE_CUSTOM",
            patterns=[phone_pattern],
            supported_language="de"
        )
        self.analyzer.registry.add_recognizer(phone_recognizer)


    def mask(self, text: str, header_values: List[str] = None) -> Tuple[str, Dict[str, str]]:
        """
        Masks PII in the text.
        Returns: (masked_text, token_map)
        """
        
        # 1. Pre-masking (Header Values - Hardening)
        # If we know the Customer Name is "FooBar GmbH", we mask it expressly.
        text_to_analyze = text
        token_map = {}
        
        # We use a primitive replace for these exact known strings to ensure 100% safety
        if header_values:
            for i, val in enumerate(header_values):
                if val and len(val) > 2:
                    # Create a token (consistent with existing system)
                    token = f"{{{{HEADER_VAL_{i}}}}}" 
                    if val not in text_to_analyze:
                        continue
                        
                    # Save mapping
                    token_map[token] = val
                    # Replace
                    text_to_analyze = text_to_analyze.replace(val, token)

        # 2. Presidio Analysis
        results = self.analyzer.analyze(
            text=text_to_analyze,
            language='de',
            entities=[
                "PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "IBAN", 
                "GERMAN_ADDRESS", "BLOCKED_COMPANY", "PHONE_CUSTOM",
                "LOCATION", "ORGANIZATION" # Generic Spacy entities
            ]
        )

        # 3. Anonymization
        # We want to replace with {{ENTITY_TYPE}} to match the existing format styles roughly
        anonymized_result = self.anonymizer.anonymize(
            text=text_to_analyze,
            analyzer_results=results,
            operators={
                "DEFAULT": OperatorConfig("replace", {"new_value": "{{PII_REDACTED}}"}),
                "PERSON": OperatorConfig("replace", {"new_value": "{{PERSON}}"}),
                "ORGANIZATION": OperatorConfig("replace", {"new_value": "{{COMPANY}}"}),
                "BLOCKED_COMPANY": OperatorConfig("replace", {"new_value": "{{COMPANY}}"}),
                "EMAIL_ADDRESS": OperatorConfig("replace", {"new_value": "{{EMAIL}}"}),
                "IBAN": OperatorConfig("replace", {"new_value": "{{IBAN}}"}),
                "GERMAN_ADDRESS": OperatorConfig("replace", {"new_value": "{{ADDRESS}}"}),
                "PHONE_CUSTOM": OperatorConfig("replace", {"new_value": "{{PHONE}}"})
            }
        )
        
        return anonymized_result.text, token_map

# Singleton instance
_masker = None

def get_masker():
    global _masker
    if not _masker:
        _masker = PIIMasker()
    return _masker

def process_document(text: str) -> Dict[str, Any]:
    # 1. Extract Header
    header = extract_document_header(text)
    
    # 2. Mask
    masker = get_masker()
    
    # Force mask extracted header fields
    header_vals = [header.customer_name, header.rfq_number, header.customer_number]
    masked_text, token_map = masker.mask(text, header_vals)
    
    return {
        "header": header.to_dict(),
        "masked_text": masked_text,
        "token_map": token_map
    }
