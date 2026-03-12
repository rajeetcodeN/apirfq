import re
import sys
import json
from services.validator import extract_marking

def test_marking():
    texts = [
        'PF A 14x9x50 1.4410 gek. DD',
        'PF B 12x8x45 1.4571  gekennz."1.4571"',
        'PF A 8h6x7x45 M4 + Kennzeich. *Neuteil*',
        'PF A 10x8x70 1.4571 gekennzeichnet "SS"',
        'PF D 14-0,014x9h11x50-0,03 C45+C KZ',
        'PF B 50x28x350 1.4057 +QT800 *NEUTEIL*'
    ]

    for t in texts:
        print(f'Text: {t:45} -> MK: {extract_marking(t)}')

test_marking()
