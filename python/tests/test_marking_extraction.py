import sys
import os

# Add the python directory to the path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.validator import validate_and_fix_items

def test_marking_extraction():
    items = [
        {"pos": "1", "article_name": "T1", "config": {"material": "C45+C"}},
        {"pos": "2", "article_name": "T2", "config": {"material": "C45+C"}},
        {"pos": "3", "article_name": "T3", "config": {"material": "C45+C"}},
        {"pos": "4", "article_name": "T4", "config": {"material": "C45+C"}},
        {"pos": "5", "article_name": "T5", "config": {"material": "C45+C"}},
        {"pos": "6", "article_name": "T6", "config": {"material": "C45+C"}},
    ]
    
    source_text = """
    Pos 1: -PF A 8x5x63 1.4057 KX
    Pos 2: -PF A 20x12x160 1.4571 SS
    Pos 3: -PF A 14x6x25 1.4501 HC
    Pos 4: -PF A 22x14x90 1.4462 T
    Pos 5: -PF D 14-0,014x9h11x50-0,03 C45+C KZ
    Pos 6: -PF B 12x8x45 1.4571 Kennz.
    """
    
    fixed_items = validate_and_fix_items(items, source_text, source_text)
    
    expected = {
        "1": "KX",
        "2": "SS",
        "3": "HC",
        "4": "T",
        "5": "KZ",
        "6": "Kennz."
    }
    
    for item in fixed_items:
        pos = item['pos']
        mk = item['config'].get('marking')
        print(f"Pos {pos}: Marking='{mk}'")
        assert mk == expected[pos], f"Expected {expected[pos]}, got {mk}"

    print("\nAll marking tests passed!")

if __name__ == "__main__":
    test_marking_extraction()
