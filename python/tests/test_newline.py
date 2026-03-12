import json
import os
import requests
from dotenv import load_dotenv

load_dotenv()
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
MISTRAL_API_BASE = "https://api.mistral.ai/v1"

SYSTEM_PROMPT = """You are a document parsing assistant designed to extract structured data from purchase orders and RFQs for automated uploading and validation in a procurement system.

Extract the following fields from the text:
requested_items: List of all requested materials/articles in the document. For each item, extract:
    - pos: Position number.
    - config: A nested object containing technical specifications (dimensions, form, material, features).
      - dimensions: Object with `width`, `height`, `length` (numeric values). Handle tolerances correctly.
    - quantity: Number of parts requested.

Return ONLY valid JSON with no markdown formatting."""

USER_PROMPT_TEMPLATE = """Extract ALL line items and document information from this RFQ/Purchase Order document:

{TEXT}

Return ONLY valid JSON with no markdown formatting."""

def test_mistral(text, label):
    print(f"\n--- Testing: {label} ---")
    headers = {
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "mistral-small-latest",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT_TEMPLATE.replace("{TEXT}", text)}
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"}
    }
    response = requests.post(f"{MISTRAL_API_BASE}/chat/completions", headers=headers, json=payload)
    parsed = json.loads(response.json()['choices'][0]['message']['content'])
    for idx, item in enumerate(parsed.get('requested_items', [])):
        dims = item.get('config', {}).get('dimensions', {})
        print(f"Item {idx+1} Dimensions: {dims}")

text_without_newline = "PFC 8h7x6x12 Edelstahl 500 stk\nPFC 8h7x7x12 Edelstahl 500 stk"
text_with_newline = "\n\nPFC 8h7x6x12 Edelstahl 500 stk\nPFC 8h7x7x12 Edelstahl 500 stk"

if MISTRAL_API_KEY:
    test_mistral(text_without_newline, "Without Leading Newline")
    test_mistral(text_with_newline, "With Leading Newline")
else:
    print("No API key")
