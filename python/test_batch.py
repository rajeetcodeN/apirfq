import json
from services.validator import validate_and_fix_items

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
            "features": []
        },
        "article_name": "PF-C-12X8X50-C60",
        "metadata": {}
    },
    {
        "pos": 2,
        "config": {
            "form": "C",
            "material": "C45+C",
            "dimensions": {"width": 8, "height": 7, "length": 45},
            "features": []
        },
        "article_name": "PF-C-8X7X45-C45+C",
        "metadata": {}
    },
    {
        "pos": 3,
        "config": {
            "form": "AS",
            "material": "Edelstahl",
            "dimensions": {"width": 8, "height": 7, "length": 45},
            "features": [{"feature_type": "thread", "spec": "M4"}]
        },
        "article_name": "PF-AS-8X7X45-M4-Edelstahl",
        "metadata": {}
    },
    {
        "pos": 4,
        "config": {
            "form": "E",
            "material": None,
            "dimensions": {"width": 8, "height": 7, "length": 80},
            "features": []
        },
        "article_name": "PF-E-8X7X80",
        "metadata": {}
    },
    {
        "pos": 5,
        "config": {
            "form": "C",
            "material": "C45",
            "dimensions": {"width": 10, "height": 8, "length": 16},
            "features": [{"feature_type": "tolerance", "spec": "h6", "position": "width"}, {"feature_type": "tolerance", "spec": "H8"}]
        },
        "article_name": "PF-C-10X8X16-C45-h6-H8",
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
        "article_name": "PF-E-10X8X50",
        "metadata": {}
    }
]

result = validate_and_fix_items(ITEMS, BATCH_TEXT, "")
print(json.dumps(result, indent=2))
