import sys
import os
import re

# Add the python directory to the path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.validator import extract_heat_treatment

def test_comprehensive_heat_treatment():
    test_cases = [
        # Hardening
        ("-PF A 3x2,6x20 C45 +C geh.50-55HRC", "geh.50-55HRC"),
        ("-PF A 16x10x80 C45+C geh. 40-50HRC Wirb.", "geh. 40-50HRC"),
        ("-PF B 5x5x12,5 C45 +C geh.50-54HRC", "geh.50-54HRC"),
        ("-PF AB 75h6x73,5x340 1.6587 geh.58-60HRC", "geh.58-60HRC"),
        ("PF A 5x5x18 C45+C geh.45-48 VP1500", "geh.45-48"),
        ("-PF A 5x5x22 C45+C geh.44-48 HRC", "geh.44-48 HRC"),
        ("-PF A 3x3x6 1.7139 geh.55+/-2HRC", "geh.55+/-2HRC"),
        ("-PF A 3x3x10 1.7139 geh.HRA81+2", "geh.HRA81+2"),
        ("-PF AB 5x5x11,5 1.7139 geh.56-60 0,3-0,5", "geh. 56-60"), # Base match, EHT may be handled by suffix
        ("-PF AB 5x5x11,5 1.7139 geh. 56-60 HRC, EHT:0,3-0,5", "geh. 56-60 HRC, EHT:0,3-0,5"),
        ("-PF A 4,8h7x5,5x15 C45+C geh. 100%", "geh. 100%"),
        ("-PF 5x4,1x11 1.7139 n.Zng. geh.670HV10", "geh.670HV10"),
        ("Gehärtet", "Gehärtet"),
        ("Geh.", "Geh."),
        
        # Coating (Heat)
        ("-PF A 3x3x8 1.7227 verg.350+50HV VP100", "verg.350+50HV"),
        ("PF A 14x9x80 C45+C M6 verg.90-100 VP100", "verg. 90-100"), # Rm handled by prefix
        ("PF A 14x9x80 C45+C M6 verg. Rm 900-1000 N/mm²", "verg. Rm 900-1000 N/mm²"),
        ("-PF B 8x7x40 C45+C verg.1050-1250", "verg.1050-1250"),
        ("-PF D 50x28x80 1.7227 verg.900-1100", "verg.900-1100"),
        ("-PF B 28x16x72 1.7227 verg.", "verg."),
        ("-PF B 22x14x46 C45 +C verg.min 900", "verg.min 900"),
        ("Vergütet", "Vergütet"),
        
        # Case Hardening / Blue Section
        ("-PF B 18x11x70 C45+C carbo.50-54", "carbo.50-54"),
        ("-PF A 3x3x16 1.7139 carbo.55HRC", "carbo.55HRC"),
        ("- PF B 8x7x25 C45+C carb 53-57 *Neutei", "carb 53-57"),
        ("-PF A 12x8x40 1.4923 salzbadnitrieren", "salzbadnitrieren"),
        ("-PF B 18x18x215 C45+C n.Zng. nitriert", "nitriert"),
        ("Wärmebehandlung", "Wärmebehandlung"),
        ("Wärmeb.", "Wärmeb."),
    ]
    
    print(f"{'Input':<50} | {'Expected':<30} | {'Extracted':<30} | Status")
    print("-" * 120)
    
    all_passed = True
    for text, expected in test_cases:
        extracted = extract_heat_treatment(text)
        # Normalize spaces for comparison
        status = "PASS" if extracted and re.sub(r'\s+', '', extracted).lower() == re.sub(r'\s+', '', expected).lower() else "FAIL"
        if status == "FAIL":
            all_passed = False
            print(f"FAIL: Input: {text[:50]:<50} | Expected: {expected:<30} | Got: {str(extracted):<30}")
        
    if all_passed:
        print("\nAll comprehensive heat treatment tests passed!")
    else:
        print("\nSome tests failed. Check the table above.")
        sys.exit(1)

if __name__ == "__main__":
    test_comprehensive_heat_treatment()
