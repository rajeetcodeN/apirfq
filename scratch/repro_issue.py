import sys
import os

# Add python directory to path
sys.path.append(os.path.join(os.getcwd(), 'python'))

from services.validator import parse_dimensions_from_string, validate_and_fix_items

def test_dimensions():
    print("Testing Dimension Extraction:")
    test_str = "PF B 19,05x19,05x115 C45 25St"
    res = parse_dimensions_from_string(test_str)
    print(f"  {repr(test_str)} -> {res}")
    
    test_str_2 = "PF AS 9,5x8x35 1.4057 600St."
    res_2 = parse_dimensions_from_string(test_str_2)
    print(f"  {repr(test_str_2)} -> {res_2}")

def test_full_validator_logic():
    print("\nTesting Full Validator Logic:")
    ocr_text = """PF AS 9,5x8x35 1.4057 600St.
PF B 19,05x19,05x115 C45 25St
\-PF A 3x3x16 1.7139 carbo.55HRC 60"""

    # Simulate what AI might return if it's confused
    items = [
        {
            "pos": 1,
            "article_name": "PF-AS-9.5X8X35-1.4057",
            "config": {
                "form": "AS",
                "dimensions": {"width": 9.5, "height": 8.0, "length": 35.0},
                "material": "1.4057"
            },
            "quantity": 600
        },
        {
            "pos": 2,
            "article_name": "PF-B-9.5X8X35-C45", # Hallucinated dims
            "config": {
                "form": "B",
                "dimensions": {"width": 9.5, "height": 8.0, "length": 35.0}, # Hallucinated
                "material": "C45"
            },
            "quantity": 25
        },
        {
            "pos": 3,
            "article_name": "PF-A-3X3X16-1.7139-carbo.55HRC",
            "config": {
                "form": "A",
                "dimensions": {"width": 3.0, "height": 3.0, "length": 16.0},
                "material": "1.7139",
                "heat_treatment": "carbo.55HRC"
            },
            "quantity": 60
        }
    ]
    
    fixed_items = validate_and_fix_items(items, ocr_text, ocr_text)
    
    for item in fixed_items:
        print(f"Pos {item['pos']}:")
        print(f"  Article: {item['article_name']}")
        print(f"  Dims: {item['config']['dimensions']}")
        print(f"  Mat: {item['config']['material']}")
        print(f"  Snippet used: {repr(item['metadata'].get('raw_text_snippet', ''))}")

if __name__ == "__main__":
    test_dimensions()
    test_full_validator_logic()
