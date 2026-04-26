import sys
import os

# Add the python directory to the path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.validator import validate_and_fix_items

def test_surface_treatment_extraction():
    items = [
        {"pos": "1", "article_name": "T1", "config": {"material": "C45+C"}},
        {"pos": "2", "article_name": "T2", "config": {"material": "C45+C"}},
        {"pos": "3", "article_name": "T3", "config": {"material": "C45+C"}},
    ]
    
    source_text = """
    Pos 1: Passfeder 10x8x8, Oberflächenbehandlung: verzinkt
    Pos 2: PF A 6x4x25 C45 +C Oberfläche: poliert
    Pos 3: PF A 10x8x63 C45 +C Oberfl. brün.
    """
    
    fixed_items = validate_and_fix_items(items, source_text, source_text)
    
    expected = {
        "1": "verzinkt",
        "2": "poliert",
        "3": "brün."
    }
    
    for item in fixed_items:
        pos = item['pos']
        st = item['config'].get('surface_treatment')
        print(f"Pos {pos}: Surface Treatment='{st}'")
        assert st == expected[pos], f"Expected {expected[pos]}, got {st}"

    print("\nAll surface treatment tests passed!")

if __name__ == "__main__":
    test_surface_treatment_extraction()
