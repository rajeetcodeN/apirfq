import pytest
from services.validator import validate_and_fix_items, fix_material

BATCH_TEXT = """Passfedern DIN 6885 Form C 12x8x50 C60
PF C 8x7x45 C45+C
Paßfeder 6885 AS 8x7x45 M4 Edelstahl
Parallel key DIN6885 E 8 x 7 x 80
PF C B-10h6 H8 T 16 C45
PAsfffedr E 10x8h7x50"""

ITEMS = [
    {
        "pos": 1,
        "config": {
            "form": "C",
            "material": "C60",
            "dimensions": {"width": 12, "height": 8, "length": 50},
            "features": [{"feature_type": "tolerance", "spec": "h9", "position": "height"}]
        },
        "article_name": "PF-C-12X8X50-C60-h9",
        "metadata": {}
    },
    {
        "pos": 5,
        "config": {
            "form": "C",
            "material": "C45",
            "dimensions": {"width": 10, "height": 8, "length": 16},
            "features": [{"feature_type": "tolerance", "spec": "h6", "position": "width"}]
        },
        "article_name": "PF-C-10X8X16-C45-h6",
        "metadata": {}
    },
    {
        "pos": 6,
        "config": {
            "form": "E",
            "material": None,
            "dimensions": {"width": 10, "height": 8, "length": 50},
            "features": []
        },
        "article_name": "PF-E-10X8X50-h7",
        "metadata": {}
    },
]

def test_tolerance_does_not_bleed():
    result = validate_and_fix_items(ITEMS, BATCH_TEXT, "")
    pos1 = next(r for r in result if r["pos"] == 1)
    pos5 = next(r for r in result if r["pos"] == 5)
    
    # 1. Pos 1 should NOT have h7 (bled from Pos 6) - it should keep h9 (or default normalized)
    tols1 = {f["spec"] for f in pos1["config"]["features"] if f["feature_type"] == "tolerance"}
    assert "h7" not in tols1, f"Pos 1 should NOT have h7 from Pos 6 bleed: {tols1}"
    
    # 2. Pos 5 should keep its h6 (from its own raw line 'B-10h6')
    tols5 = {f["spec"] for f in pos5["config"]["features"] if f["feature_type"] == "tolerance"}
    assert "h6" in tols5, f"Pos 5 should keep h6: {tols5}"

def test_material_c60_autocorrect():
    assert fix_material("C60") == "C60E"

def test_material_edelstahl_autocorrect():
    assert fix_material("Edelstahl") == "1.4301"
