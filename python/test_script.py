from services.validator import extract_heat_treatment, extract_surface_treatment, extract_marking

texts = [
    'PF A 4x4x10 1.4571 geh. poliert VP200',
    'Achshalter 20x5x60 verzinkt',
    'PF A 4x4x12 C45 +C  verz.',
    'PF B 12x8x40 C45 +C VZ',
    'PF A 4x4x18 C45 +C  brün.   VP500',
    ' PF F 14x9x50  C45+C M5 brüniert',
    'PF A 4x4x22 C45+C Geomet321A',
    'PF A 8x7x32 1.4301+C700  geo.',
    'PF A 6x4x25 C45 +C DBL',
    'PF A 2x2x6 1.4571 passiviert QS APZ3.1',
    'PF A 6x6x22 1.4571 passiv.',
    'PF A 4x4x10 1.4571 geh. poliert VP200',
    'PP A 22x14x140 C45+C vernickelt',
    'PF A 22x14x140 C45+C vernickelt DNC520',
    'Passfeder B 10x8x8,Zink Nickl',
    'PF A 10x8x63 C45 +C zinkphosphatiert',
    'Passfeder A 5x5x20 phosph. *NEUTEIL*',
    'Passfeder F 32x18x125 C45+C phos. "NEU"',
    'PF A 8x5x110 1.4501 PREN>40 "NEU"',
    'PF B 50x28x350 1.4057 +QT800 *NEUTEIL*'
]

for t in texts:
    print(f'Text: {t}')
    print(f'  HT: {extract_heat_treatment(t)}')
    print(f'  ST: {extract_surface_treatment(t)}')
    print(f'  MK: {extract_marking(t)}\n')
