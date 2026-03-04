from services.validator import extract_marking, extract_surface_treatment

texts = [
    'PF A 16X10X80 C45+C geh.40-50HRC Wirb.',
    'PF A 2x2x6 1.4571 passiviert QS APZ3.1',
    'PF A 4x4x10 1.4571 geh. poliert VP100',
    'PF A 4x4x10 1.4571 geh. poliert VP200',
    'PF A 4x4x10 1.4571 geh. poliert VP500',
    'PF A 4x4x10 1.4571 geh. poliert VP1500'
]

for t in texts:
    h = extract_surface_treatment(t)
    m = extract_marking(t)
    print(f'Text: {t:45}\n -> ST: {str(h):10} | MK: {str(m)}')
