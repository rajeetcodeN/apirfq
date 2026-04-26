import pytest
import asyncio
from unittest.mock import patch
import re
from services.ai import extract_data_from_text_async

def mock_extract(text, native_text=None, user_feedback=None, is_chunk=False):
    """Mocks the AI response. Returns some items based on the input text."""
    pos_matches = re.findall(r'Pos\s*(\d+)', text)
    
    items = []
    for p in pos_matches:
        items.append({
            "pos": int(p),
            "article_name": f"PF-A-Mock-{p}",
            "config": {"dimensions": {"width": 8}}
        })
    
    return {
        "requested_items": items,
        "metadata": {"source": "mock"}
    }

@pytest.mark.asyncio
async def test_parallel_batch_extraction_logic():
    """
    Verifies that extract_data_from_text_async correctly chunks 
    a 30-item text into 3 parallel batches and merges them.
    """
    # Simulate a 30-item RFQ text (should trigger 3 chunks of 10)
    items_text = ""
    for i in range(1, 31):
        items_text += f"Pos {i}  PF A 8h8x7x{20+i} C45+C\n"
    
    full_text = f"Supplier: Nosta GmbH\nRFQ: 12345\n\n{items_text}"
    
    # Patch the real function with our mock
    with patch('services.ai.extract_data_from_text', side_effect=mock_extract) as mock_api:
        result = await extract_data_from_text_async(full_text)
        
        items = result.get("requested_items", [])
        metadata = result.get("metadata", {})
        
        # 1. Verify chunk count
        assert metadata.get("batch_count") == 3
        assert mock_api.call_count == 3
        
        # 2. Verify total items
        assert len(items) == 30
        
        # 3. Verify position re-sequencing
        for idx, item in enumerate(items):
            assert item.get("pos") == idx + 1
            
        # 4. Verify mode
        assert metadata.get("processing_mode") == "parallel_burst"

@pytest.mark.asyncio
async def test_single_chunk_fallback():
    """Verifies that small files (<= 10 items) do NOT trigger chunking."""
    small_text = "Pos 1  PF A 8X7X40 C45+C"
    
    with patch('services.ai.extract_data_from_text', side_effect=mock_extract) as mock_api:
        result = await extract_data_from_text_async(small_text)
        
        # metadata.get("batch_count") won't exist because it falls back to single call
        assert "batch_count" not in result.get("metadata", {})
        assert mock_api.call_count == 1
        assert len(result.get("requested_items", [])) == 1
