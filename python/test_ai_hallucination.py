import json
from services.validator import validate_and_fix_items

BATCH_TEXT = """PFC 8h7x6x12 Edelstahl 500 stk
PFC 8h7x7x12 Edelstahl 500 stk"""

# Simulate AI hallucinating the height as 7 for BOTH items
ITEMS = [
    {
        "pos": 1,
        "config": {
            "dimensions": {"width": 8, "height": 7, "length": 12}, # AI hallucinated 7 instead of 6
            "features": []
        },
        "article_name": "PF-8X7X12",
        "metadata": {}
    },
    {
        "pos": 2,
        "config": {
            "dimensions": {"width": 8, "height": 7, "length": 12},
            "features": []
        },
        "article_name": "PF-8X7X12",
        "metadata": {}
    }
]

result = validate_and_fix_items(ITEMS, BATCH_TEXT, "")
print("POS 1 -------------")
print(json.dumps(result[0], indent=2))
print("\nPOS 2 -------------")
print(json.dumps(result[1], indent=2))
