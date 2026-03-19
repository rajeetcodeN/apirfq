import sys
import os

# Add python directory to path
sys.path.append(os.path.join(os.getcwd(), 'python'))

from services.validator import fix_material

def test_material_suffixes():
    print("Testing Material Suffix Stripping:")
    tests = [
        "1.4057+QT800+2H",
        "1.4301+C700",
        "1.4462+2H",
        "1.7139+A+C",
        "C45+C",           # This should NOT be stripped
        "c45+c",           # This should NOT be stripped
        "1.0503"           # This should become C45+C
    ]
    for t in tests:
        res = fix_material(t)
        print(f"  {repr(t)} -> {repr(res)}")

if __name__ == "__main__":
    import sys
    with open("test_results_mat.txt", "w", encoding="utf-8") as f:
        sys.stdout = f
        test_material_suffixes()
    sys.stdout = sys.__stdout__
    print("Results written to test_results_mat.txt")
