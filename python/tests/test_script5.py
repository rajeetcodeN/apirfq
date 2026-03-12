import re
from services.validator import extract_surface_treatment, extract_heat_treatment, extract_features_from_string

text = 'PF-B-18X18X215-C45+C-n.Zng.nitriert'

print(f"HT: {extract_heat_treatment(text)}")
print(f"ST: {extract_surface_treatment(text)}")
print(f"Features: {extract_features_from_string(text)}")
