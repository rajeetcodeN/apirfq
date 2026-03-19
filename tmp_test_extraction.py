import sys
import os

# Add python directory to path
sys.path.append(os.path.join(os.getcwd(), 'python'))

from services.validator import extract_surface_treatment, extract_heat_treatment, extract_marking

def test_surface():
    print("Testing Surface Treatment:")
    tests = [
        "Oberflächenbehandlung poliert",
        "Oberfläche verzinkt",
        "Oberfl. brüniert"
    ]
    for t in tests:
        res = extract_surface_treatment(t)
        print(f"  {repr(t)} -> {repr(res)}")

def test_heat():
    print("\nTesting Heat Treatment:")
    tests = [
        "Wärmebehandlung 50-55HRC",
        "Wärmeb. 900-1100",
        "Gehärtet 60HRC",
        "Geh. N533"
    ]
    for t in tests:
        res = extract_heat_treatment(t)
        print(f"  {repr(t)} -> {repr(res)}")

def test_marking():
    print("\nTesting Marking:")
    tests = [
        "KX identifier",
        "SS marking",
        "HC code",
        "T spec",
        "Ken. 123",
        "Kennz. ABC"
    ]
    for t in tests:
        res = extract_marking(t)
        print(f"  {repr(t)} -> {repr(res)}")

if __name__ == "__main__":
    import sys
    with open("test_results.txt", "w", encoding="utf-8") as f:
        sys.stdout = f
        test_surface()
        test_heat()
        test_marking()
    sys.stdout = sys.__stdout__
    print("Results written to test_results.txt")
