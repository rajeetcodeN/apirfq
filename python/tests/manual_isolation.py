import json
from services.validator import validate_and_fix_items

BATCH_TEXT = """Passfeder DIN 6885 Form A 10x8x40 C45
Parallel key Form B 10x8x50 Edelstahl"""

ITEMS = [
    {
        "pos": 1,
        "config": {
            "dimensions": {"width": 10, "height": 8, "length": 40},
            "features": []
        },
        "article_name": "PF-10X8X40",
        "metadata": {}
    },
    {
        "pos": 2,
        "config": {
            "dimensions": {"width": 10, "height": 8, "length": 50},
            "features": []
        },
        "article_name": "PF-10X8X50",
        "metadata": {}
    }
]

# We run the validator. Pos 1 should pick up Form A and C45.
# Pos 2 should pick up Form B and Edelstahl (1.4301).
# They should NOT bleed into each other, even though they share W/H dimensions.
result = validate_and_fix_items(ITEMS, BATCH_TEXT, "")
print("POS 1 -------------")
print(json.dumps(result[0], indent=2))
print("\nPOS 2 -------------")
print(json.dumps(result[1], indent=2))
