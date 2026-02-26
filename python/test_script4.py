from services.validator import extract_heat_treatment, extract_surface_treatment, extract_marking

texts = [
    'PF A 2x2x6 1.4571 passiviert QS APZ3.1',
    'PF A 4x4x10 1.4571 geh. poliert VP200',
    'Passfeder A 5x5x20 phosph. *NEUTEIL*',
    'Passfeder F 32x18x125 C45+C phos. "NEU"',
    'PF B 50x28x350 1.4057 +QT800 *  NEUTEIL*'
]

for t in texts:
    h = extract_heat_treatment(t)
    s = extract_surface_treatment(t)
    m = extract_marking(t)
    print(f'Text: {t:45}\n -> HT: {str(h):10} | ST: {str(s):10} | MK: {str(m)}')
