import re
from typing import Optional

def extract_surface_treatment(text: str) -> Optional[str]:
    mapping = {
        r'poliert': 'poliert',
        r'verzinkt': 'verzinkt',
        r'verz\.': 'verz.',
        r'VZ': 'VZ',
        r'brün\.': 'brün.',
        r'brüniert': 'Brüniert',
        r'Geomet321A': 'Geomet321A',
        r'geo\.': 'geo.',
        r'DBL': 'DBL',
        r'passiviert': 'passiviert',
        r'passiv\.': 'passiv.',
        r'vernickelt\s*DNC\s*520(?:-5[µu])?': 'vernickelt DNC 520-5µ',
        r'vernickelt': 'vernickelt',
        r'zink[\s\-]?nickel': 'Zink-Nickel',
        r'zink[\s\-]?nickl': 'Zink-Nickel',
        r'zinkphosphatiert': 'zinkphosphatiert',
        r'phosph\.': 'phosph',
        r'phosph': 'phosph',
        r'phos\.': 'phos.',
        r'PREN\s*>\s*40': 'PREN >40',
        r'\+?QT\s*800': 'QT 800',
        r'carbo(?:\.\s*\d+(?:-\d+)?)?(?:HRC)?': 'carbo',
        r'carb': 'carb',
        r'salzbad(?:nitrier(?:t|en|ung)?)?': 'salzbadnitriert',
        r'nitrier(?:t|en|ung)?': 'nitriert',
    }
    
    sorted_patterns = sorted(mapping.keys(), key=len, reverse=True)
    
    for pat in sorted_patterns:
        # Added parentheses '(' ')' and brackets '[' ']' and extra punctuation
        regex = r'(?:^|[\s,\-\+\.\(\[])(' + pat + r')(?:\s|$|,|\"|\*|\-|\)|\]|\.)'
        match = re.search(regex, text, re.IGNORECASE)
        if match:
            return mapping[pat]
            
    return None

def extract_marking(text: str) -> Optional[str]:
    mapping = {
        r'gek\.\s*DD': 'gek. DD',
        r'gekennz\.': 'gekennz.',
        r'Kennzeich\.': 'Kennzeich.',
        r'gekennzeichnet': 'gekennzeichnet',
        r'KZ': 'KZ'
    }
    sorted_patterns = sorted(mapping.keys(), key=len, reverse=True)
    for pat in sorted_patterns:
        regex = r'(?:^|[\s,\-\+\.\(\[])(' + pat + r')(?:\s|$|,|\"|\*|\-|\)|\]|\.)'
        match = re.search(regex, text, re.IGNORECASE)
        if match:
            return mapping[pat]
    return None

texts = [
    'PF-B-18X18X215-(nitriert)',
    'PF-A-C45+C-salzbadnitrieren,',
    'PF-14X9X50-M5-nitrierung.',
    'PF-B-10X8X8-Zink-Nickl.',
    'PF-A-gekennzeichnet.'
]

for t in texts:
    s = extract_surface_treatment(t)
    m = extract_marking(t)
    if s:
        print(f'Text: {t:45} -> ST: {str(s)}')
    if m:
        print(f'Text: {t:45} -> MK: {str(m)}')
