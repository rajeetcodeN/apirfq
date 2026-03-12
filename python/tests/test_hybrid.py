
import asyncio
import os
import sys
import json
from dotenv import load_dotenv

# Add current directory to path so imports work
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Load env from .env.local (parent dir)
load_dotenv(dotenv_path="../.env.local")

from services.ingestion import route_ingestion
from services.ai import extract_data_from_text

async def test_extraction():
    pdf_path = "../würth.pdf"
    print(f"Testing extraction for: {pdf_path}")
    
    if not os.path.exists(pdf_path):
        print(f"Error: File {pdf_path} not found.")
        return

    with open(pdf_path, "rb") as f:
        file_bytes = f.read()
        
    # 1. Ingestion
    print("Running ingestion...")
    try:
        result = await route_ingestion(file_bytes, "application/pdf", "würth.pdf")
        source = result["source"]
        print(f"Ingestion Source: {source}")
        
        if source == "hybrid_pdf":
            raw_text = result["ocr_text"]
            native_text = result["native_text"]
            print(f"OCR Text Length: {len(raw_text)}")
            print(f"Native Text Length: {len(native_text)}")
        else:
            raw_text = result["raw_data"]
            native_text = None
            print(f"Raw Text Length: {len(raw_text)}")
            
    except Exception as e:
        print(f"Ingestion failed: {e}")
        return

    # 2. AI Extraction
    print("Running AI Extraction...")
    try:
        # Mock masking for now (just pass raw text) as masking is not the focus of this test
        masked_text = raw_text 
        
        ai_data = extract_data_from_text(masked_text, native_text=native_text)
        
        print("\n--- Extracted Data ---")
        items = ai_data.get("requested_items", [])
        for item in items:
            print(f"Pos: {item.get('pos')}")
            print(f"Article Name: {item.get('article_name')}")
            config = item.get("config", {})
            print(f"Dimensions: {config.get('dimensions')}")
            print(f"Features: {config.get('features')}")
            print("-" * 30)
            
    except Exception as e:
        print(f"AI Extraction failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_extraction())
