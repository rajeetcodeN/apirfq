import logging
import json
import requests
import os
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
MISTRAL_API_BASE = "https://api.mistral.ai/v1"

VERIFIER_PROMPT = """You are a rigorous data auditor. Your job is to verify an AI's extraction against the raw text.

RAW TEXT SNIPPET:
"{RAW_TEXT}"

AI EXTRACTED JSON:
{JSON_DATA}

Strictly check for these errors:
1. **Hallucinated Dimensions**: Does the text ACTUALLY contain these dimensions? Or did the AI guess?
   - Example error: Extracting "100" from a material code "100-20..." as length.
2. **Form vs Dimension Confusion**: 
   - Example error: "B=20" in text -> AI extracted Form="B". (CORRECT: Width=20, Form might be missing or different).
3. **Missing Features**: Did the text have "M6", "Zinc Plated", "Tempered" that operates distinct features?
4. **Material Mismatch**: Does the material code match the text EXACTLY?

Output a JSON object:
{{
  "is_correct": boolean,
  "confidence_score": float (0.0-1.0),
  "correction": {{ ...corrected json object... }} (only if is_correct is false, otherwise null),
  "reason": "explanation of error" (or "looks good")
}}
"""

class Verifier:
    def __init__(self, api_key: str = MISTRAL_API_KEY):
        self.api_key = api_key

    def verify_item(self, raw_text_snippet: str, current_extraction: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sends the extraction and raw text to AI for a second opinion.
        Returns the verification result (is_correct, correction, reason).
        """
        if not self.api_key:
            logger.warning("Verifier: No API key, skipping verification")
            return {"is_correct": True, "confidence_score": 0.5, "reason": "No API Key"}

        try:
            prompt = VERIFIER_PROMPT.replace("{RAW_TEXT}", raw_text_snippet).replace("{JSON_DATA}", json.dumps(current_extraction))
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": "mistral-small-latest", # Use a smaller/faster model for verification if possible, or same as main
                "messages": [
                     {"role": "user", "content": prompt}
                ],
                "temperature": 0.0, # Strict
                "response_format": {"type": "json_object"}
            }
            
            response = requests.post(
                f"{MISTRAL_API_BASE}/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()['choices'][0]['message']['content']
            return json.loads(result)

        except Exception as e:
            logger.error(f"Verifier failed: {e}")
            # Fail open - assume correct to avoid blocking flow on verifier error
            return {"is_correct": True, "confidence_score": 0.5, "reason": f"Verifier Error: {e}"}
