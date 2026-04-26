import sys
import os

# Add the python directory to the path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.validator import validate_and_fix_items

def test_treatment_classification():
    items = [
        {
            "pos": "1",
            "article_name": "Test 1",
            "config": {"material": "C45+C"}
        },
        {
            "pos": "2",
            "article_name": "Test 2",
            "config": {"material": "C45+C"}
        },
        {
            "pos": "3",
            "article_name": "Test 3",
            "config": {"material": "C45+C"}
        },
        {
            "pos": "4",
            "article_name": "Test 4",
            "config": {"material": "C45+C"}
        }
    ]
    
    source_text = """
    Pos 1: PF B 18x11x70 C45+C carbo.50-54
    Pos 2: PF A 12x8x40 1.4923 salzbadnitriert
    Pos 3: PF B 18x18x215 C45+C nitriert
    Pos 4: PF B 20x12x30 C45+C verg.900-1100
    """
    
    fixed_items = validate_and_fix_items(items, source_text, source_text)
    
    for item in fixed_items:
        pos = item['pos']
        ht = item['config'].get('heat_treatment')
        st = item['config'].get('surface_treatment')
        print(f"Pos {pos}:")
        print(f"  Heat Treatment: {ht}")
        print(f"  Surface Treatment: {st}")
        
        if pos == "1":
            assert "carbo" in str(ht).lower()
            assert st is None
        elif pos == "2":
            assert "salzbadnitriert" in str(ht).lower()
            assert st is None
        elif pos == "3":
            assert "nitriert" in str(ht).lower()
            assert st is None
        elif pos == "4":
            assert "verg" in str(ht).lower()
            assert st is None

    print("\nAll tests passed!")

if __name__ == "__main__":
    test_treatment_classification()
