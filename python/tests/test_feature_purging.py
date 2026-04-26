import sys
import os

# Add the python directory to the path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.validator import validate_and_fix_items

def test_feature_purging():
    # Simulate AI output where "nitriert" is incorrectly extracted as a coating feature
    # and also placed in surface_treatment (previous behavior)
    items = [
        {
            "pos": "1",
            "article_name": "PF-B-18X18X215-C45+C-nitriert",
            "config": {
                "material": "C45+C",
                "form": "B",
                "dimensions": {"width": 18, "height": 18, "length": 215},
                "features": [
                    {"feature_type": "coating", "spec": "nitriert"},
                    {"feature_type": "tolerance", "spec": "h9", "position": "width"}
                ],
                "heat_treatment": None,
                "surface_treatment": "nitriert"
            }
        },
        {
            "pos": "2",
            "article_name": "T2",
            "config": {
                "material": "C45+C",
                "features": [
                    {"feature_type": "coating", "spec": "carbo.50-54"}
                ],
                "heat_treatment": "carbo.50-54",
                "surface_treatment": "carbo.50-54"
            }
        }
    ]
    
    source_text = """
    Pos 1: -PF B 18x18x215 C45+C nitriert
    Pos 2: -PF B 18x11x70 C45+C carbo.50-54
    """
    
    fixed_items = validate_and_fix_items(items, source_text, source_text)
    
    # Check Pos 1
    item1 = fixed_items[0]
    print(f"Pos 1:")
    print(f"  Heat Treatment: {item1['config'].get('heat_treatment')}")
    print(f"  Surface Treatment: {item1['config'].get('surface_treatment')}")
    print(f"  Features: {item1['config'].get('features')}")
    
    assert item1['config']['heat_treatment'] == "nitriert"
    assert item1['config']['surface_treatment'] is None
    # "nitriert" should be GONE from features
    assert not any(f['spec'] == 'nitriert' for f in item1['config']['features'])
    # "h9" should STAY
    assert any(f['spec'] == 'h9' for f in item1['config']['features'])

    # Check Pos 2
    item2 = fixed_items[1]
    print(f"\nPos 2:")
    print(f"  Heat Treatment: {item2['config'].get('heat_treatment')}")
    print(f"  Surface Treatment: {item2['config'].get('surface_treatment')}")
    print(f"  Features: {item2['config'].get('features')}")
    
    assert item2['config']['heat_treatment'] == "carbo.50-54"
    assert item2['config']['surface_treatment'] is None
    # "carbo.50-54" should be GONE from features
    assert not any(f['spec'] == 'carbo.50-54' for f in item2['config']['features'])

    print("\nFeature purging tests passed!")

if __name__ == "__main__":
    test_feature_purging()
