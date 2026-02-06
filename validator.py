from typing import Dict, Tuple

def validate_row(record: Dict) -> Tuple[str, str]:
    issues = []
    
    # 1. CF Number
    if not record.get('Numar_CF') or record['Numar_CF'] == "Nedetectat":
        issues.append("Lipsa Numar CF")
        
    # 2. Owner
    owner = record.get('Proprietari', '')
    if not owner or owner == "Nedetectat":
        issues.append("Lipsa Proprietar")
    elif len(owner) < 3:
        issues.append("Nume Proprietar Suspect")

    # 3. Land Surface
    surf_land = record.get('Suprafata_Masurata_MP', '')
    if not surf_land or surf_land == "0":
        # Check Document Surface as backup
        if not record.get('Suprafata_Din_Act_MP'):
            issues.append("Lipsa Suprafata Teren")

    # 4. Building Logic
    has_building = record.get('Nr_Constructie') and record['Nr_Constructie'] != ""
    if has_building:
        surf_build = record.get('Suprafata_Construita_MP', '')
        if not surf_build or surf_build == "0":
            issues.append("Lipsa Suprafata Constructie")
            
        dest = record.get('Destinatie_Constructie', '')
        if not dest:
            issues.append("Lipsa Destinatie")
    
    if not issues:
        return "OK", ""
    else:
        return "VERIFICA", ", ".join(issues)
