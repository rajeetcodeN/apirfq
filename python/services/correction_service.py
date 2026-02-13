import json
import os
import re
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Directory to store corrections
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
CORRECTIONS_FILE = os.path.join(DATA_DIR, "corrections.json")

class CorrectionService:
    def __init__(self):
        self._ensure_data_dir()
        self.corrections = self._load_corrections()

    def _ensure_data_dir(self):
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)
        if not os.path.exists(CORRECTIONS_FILE):
            with open(CORRECTIONS_FILE, 'w', encoding='utf-8') as f:
                json.dump([], f)

    def _load_corrections(self) -> List[Dict[str, Any]]:
        try:
            with open(CORRECTIONS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load corrections: {e}")
            return []

    def _save_corrections(self):
        try:
            with open(CORRECTIONS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.corrections, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save corrections: {e}")

    def fingerprint_text(self, text: str) -> List[str]:
        """
        Generates a list of keywords/tokens that identify the format/supplier.
        Simple heuristic: looks for common supplier names or unique header terms.
        """
        fingerprints = []
        text_lower = text.lower()
        
        # Known suppliers / keywords (can be expanded)
        keywords = ["würth", "nosta", "schrauben", "liefertermin", "bestellnummer", "auftrag"]
        
        for k in keywords:
            if k in text_lower:
                fingerprints.append(k)
                
        return fingerprints

    def save_correction(self, raw_text_snippet: str, correct_json: Dict[str, Any], full_text_context: str = ""):
        """
        Saves a correction.
        raw_text_snippet: The specific line/text that was misread (e.g. "Pos 10 ...")
        correct_json: The correct extraction for that snippet.
        full_text_context: The full document text (used for fingerprinting).
        """
        fingerprints = self.fingerprint_text(full_text_context)
        
        correction = {
            "fingerprints": fingerprints,
            "raw_text": raw_text_snippet.strip(),
            "correction": correct_json,
            "timestamp": "TODO: timestamp" 
        }
        
        # Check for duplicates (avoid saving exact same correction multiple times)
        for existing in self.corrections:
            if existing["raw_text"] == correction["raw_text"] and \
               existing["correction"] == correction["correction"]:
                return

        self.corrections.append(correction)
        self._save_corrections()
        logger.info(f"Saved correction for fingerprints: {fingerprints}")

    def get_few_shot_context(self, text: str) -> str:
        """
        Returns a string containing relevant few-shot examples based on the text's fingerprint.
        """
        fingerprints = self.fingerprint_text(text)
        if not fingerprints:
            return ""

        relevant_corrections = []
        for corr in self.corrections:
            # If any fingerprint matches
            if any(f in corr["fingerprints"] for f in fingerprints):
                relevant_corrections.append(corr)

        if not relevant_corrections:
            return ""

        # Format context for the AI prompt
        context_msg = "\n\n⚡ LEARNED CORRECTIONS (Review these specific examples for this document format):\n"
        
        # Limit to 3 most recent relevant corrections to avoid token overflow
        for i, corr in enumerate(relevant_corrections[-3:]):
            context_msg += f"\nExample {i+1}:\n"
            context_msg += f"RAW TEXT: {corr['raw_text']}\n"
            context_msg += f"CORRECT OUTPUT: {json.dumps(corr['correction'], ensure_ascii=False)}\n"
            
        return context_msg
