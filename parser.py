import re
from typing import List, Dict, Tuple

def clean_text(text: str) -> str:
    """Standardize text for easier regex matching."""
    if not text: return ""
    text = text.replace('\r', '')
    text = text.replace('ţ', 't').replace('ş', 's').replace('ă', 'a').replace('î', 'i').replace('â', 'a')
    text = text.replace('Ţ', 'T').replace('Ş', 'S').replace('Ă', 'A').replace('Î', 'I').replace('Â', 'A')
    text = re.sub(r'[ \t]+', ' ', text)
    return text

def extract_cf_number(text: str) -> str:
    match = re.search(r"CARTE\s+FUNCIAR[AĂ]\s+NR\.?\s+(\d+)", text, re.IGNORECASE)
    return match.group(1) if match else "Nedetectat"

def extract_uat_locality(text: str) -> Tuple[str, str]:
    """Extracts UAT and Locality from header."""
    uat = ""
    localitate = ""
    
    uat_match = re.search(r"(?:UAT|Comuna|Oras|Municipiu)[:\s]+([A-Z][a-zA-Z\s\-]+)", text)
    if uat_match:
        uat = uat_match.group(1).strip()
    
    loc_match = re.search(r"Loc\.\s*([A-Z][a-zA-Z\s\-]+)", text)
    if loc_match:
        localitate = loc_match.group(1).strip()
    
    return uat, localitate

def extract_cadastral_number(text: str) -> str:
    # Matches A1 followed by number, IGNORING quotes/commas
    a1_match = re.search(r"\bA1[^\d\n]*([0-9\-/]+)", text)
    if a1_match:
        return a1_match.group(1)
    
    cad_match = re.search(r"Nr\.?\s*(?:cadastral|topografic).*?(\d+[0-9\-/]*)", text, re.IGNORECASE)
    if cad_match:
        if "vechi" not in cad_match.group(0).lower():
            return cad_match.group(1)
    return "Nedetectat"

def extract_owner_details(text: str) -> Tuple[str, str, str, str]:
    """
    Extracts Owner Name, Quota, Mode of Acquisition, and Act.
    Handles: person names, company names (S.A., S.R.L.), municipalities, state entities, etc.
    """
    # Fixed regex: read B section until C. Partea III (not stopping at "Anexa" in middle of text)
    part_ii_match = re.search(r"B\.\s*Partea\s+II.*?(?=C\.\s*Partea\s+III)", text, re.IGNORECASE | re.DOTALL)
    if not part_ii_match:
        return "Fara proprietar identificat", "", "", ""
    
    part_ii = part_ii_match.group(0)
    
    if "proprietar neidentificat" in part_ii.lower():
        return "Proprietar neidentificat", "1/1", "Lege", ""

    # 1. Extract Owner Names - COMPREHENSIVE LOGIC
    owners = []
    
    # Pattern 1: Match numbered owners "1) OWNER NAME" anywhere in B section
    # Include quotes for church names like PAROHIA "SFANTUL..."
    numbered_pattern = r'1\)\s*([A-ZĂÂÎȘȚŢŞa-zăâîșțţş][A-ZĂÂÎȘȚŢŞa-zăâîșțţş\s\.\,\-\"\'\(\)]+?)(?=\n(?:Act|OBSERV|B\d|A\d|Radiat|Document)|$)'
    numbered_matches = re.findall(numbered_pattern, part_ii)
    
    for match in numbered_matches:
        clean_name = match.strip()
        # Clean up trailing commas, "domeniu privat", etc.
        clean_name = re.sub(r',\s*domeniu\s+privat\s*$', '', clean_name, flags=re.IGNORECASE)
        clean_name = re.sub(r',\s*$', '', clean_name)
        clean_name = clean_name.strip()
        
        # Skip if it's just reference text
        if len(clean_name) > 2 and "INTABULARE" not in clean_name.upper() and "DREPT DE" not in clean_name.upper():
            if clean_name not in owners:
                owners.append(clean_name)
    
    # Pattern 2: Special entities - STATE, AGENCIES, etc.
    if not owners:
        state_patterns = [
            r'(STATUL\s+ROMAN)',
            r'(AGENTIA\s+DOMENIILOR\s+STATULUI)',
            r'(ADMINISTRATIA\s+NATIONALA[^,\n]*)',
            r'(REGIA\s+NATIONALA[^,\n]*)',
            r'(SOCIETATEA\s+NATIONALA[^,\n]*)',
            r'(CONSILIUL\s+LOCAL[^,\n]*)',
            r'(PRIMARIA[^,\n]*)',
        ]
        for pattern in state_patterns:
            match = re.search(pattern, part_ii, re.IGNORECASE)
            if match:
                owners.append(match.group(1).strip())
                break
    
    # Pattern 3: Companies (S.A., S.R.L.)
    if not owners:
        company_match = re.search(r'(?:S\.C\.\s*)?([A-ZĂÂÎȘȚa-zăâîșț\s\.\-]+(?:S\.A\.|S\.R\.L\.|SA|SRL))', part_ii)
        if company_match:
            owners.append(company_match.group(1).strip())
    
    # Pattern 4: Municipalities
    if not owners:
        muni_match = re.search(r'((?:MUNICIPIUL|JUDEȚUL|COMUNA|ORAȘUL|Municipiul|Județul|Comuna|Orașul)\s+[A-ZĂÂÎȘȚa-zăâîșț]+)', part_ii)
        if muni_match:
            owners.append(muni_match.group(1).strip())
    
    # Pattern 5: Search in full text for MUNICIPIUL with uppercase city name
    if not owners:
        muni_full = re.search(r'((?:MUNICIPIUL|JUDEȚUL|COMUNA|ORAȘUL)\s+[A-ZĂÂÎȘȚ]+)', text)
        if muni_full:
            owners.append(muni_full.group(1).strip())
    
    # Pattern 6: Person names - UPPERCASE format "LASTNAME FIRSTNAME"
    if not owners:
        # Look for typical Romanian person names after 1)
        person_pattern = r'1\)\s*([A-ZĂÂÎȘȚ][A-ZĂÂÎȘȚ\-]+\s+[A-ZĂÂÎȘȚ][A-ZĂÂÎȘȚa-zăâîșț\-]+)'
        person_match = re.search(person_pattern, part_ii)
        if person_match:
            owners.append(person_match.group(1).strip())
    
    owner_str = " & ".join(owners[:2]) if owners else "Nedetectat"

    # 2. Extract Cota
    cota = ""
    cota_match = re.search(r"cota\s+(?:actuala\s+)?(\d+/\d+)", part_ii, re.IGNORECASE)
    if cota_match:
        cota = cota_match.group(1)

    # 3. Extract Acquisition Mode
    mod = ""
    if "vanzare" in part_ii.lower() or "cumparare" in part_ii.lower(): mod = "Cumparare"
    elif "donatie" in part_ii.lower(): mod = "Donatie"
    elif "mostenire" in part_ii.lower() or "succesiune" in part_ii.lower(): mod = "Mostenire"
    elif "reconstituire" in part_ii.lower(): mod = "Reconstituire"
    elif "lege" in part_ii.lower(): mod = "Lege"
    elif "intretinere" in part_ii.lower(): mod = "Intretinere"

    # 4. Act
    act = ""
    act_match = re.search(r"(Act\s+(?:Notarial|Administrativ|Judecatoresc)[^\n]+)", part_ii, re.IGNORECASE)
    if act_match:
        act = act_match.group(1).strip()[:50] 

    return owner_str, cota, mod, act

def extract_sarcini(text: str) -> str:
    """Extracts Encumbrances (Part III)."""
    part_iii_match = re.search(r"C\.\s*Partea\s+III.*?(?=Anexa|Certificat|\Z)", text, re.IGNORECASE | re.DOTALL)
    if not part_iii_match:
        return ""
    
    part_iii = part_iii_match.group(0)
    if "NU SUNT" in part_iii:
        return "NU SUNT"
    
    sarcini = []
    if "IPOTECA" in part_iii.upper():
        bank = re.search(r"(?:Banca|BCR|BRD|CEC|Raiffeisen|ING)[^\n]*", part_iii, re.IGNORECASE)
        if bank:
            sarcini.append(f"Ipoteca: {bank.group(0).strip()}")
        else:
            sarcini.append("Ipoteca")
            
    if "UZUFRUCT" in part_iii.upper():
        sarcini.append("Uzufruct")
        
    return "; ".join(sarcini)

def extract_parcel_data(text: str) -> Tuple[str, str, str]:
    """Extracts Measured Surface, Document Surface, and Terrain Obs."""
    measured = ""
    doc_surf = ""
    obs = ""

    # Obs
    if re.search(r"Teren\s+neimprejmuit", text, re.IGNORECASE): obs = "Teren neimprejmuit"
    elif re.search(r"Teren\s+imprejmuit", text, re.IGNORECASE): obs = "Teren imprejmuit"
    
    if not obs:
        match = re.search(r"A1[^\w\n]+[0-9\-/]+[^\w\n]+[\d\.]+[^\w\n]+(.*?)(?=\s+Adresa|\s+Jud\.|\s+B\.|\s+Partea|\Z)", text, re.DOTALL)
        if match:
            raw_obs = match.group(1).strip().replace(';', '').replace('"', '')
            if len(raw_obs) < 50: obs = raw_obs

    # Surfaces
    masurata = re.search(r"Masurata:?\s*(\d+[\.\s]?\d*)", text, re.IGNORECASE)
    if masurata: measured = masurata.group(1).replace('.', '').replace(' ', '')

    din_acte = re.search(r"Din\s+acte:?\s*(\d+[\.\s]?\d*)", text, re.IGNORECASE)
    if din_acte: doc_surf = din_acte.group(1).replace('.', '').replace(' ', '')

    if not measured:
        table_match = re.search(r"A1[^\d\n]+[0-9\-/]+[^\d\n]+(\d{1,3}(?:\.\d{3})*)", text)
        if table_match: measured = table_match.group(1).replace('.', '')

    return measured, doc_surf, obs

def extract_constructions(text: str, cad_base: str) -> List[Dict]:
    """Extract construction data from the document."""
    buildings = []
    
    # Find the construction section
    section_match = re.search(
        r"Date\s+referitoare\s+la\s+construc[tț]ii(.*?)(?=Lungime\s+Segmente|Extrase\s+pentru|Document\s+care|\Z)", 
        text, 
        re.DOTALL | re.IGNORECASE
    )
    
    if not section_match:
        return []

    block = section_match.group(1)
    
    # Find all construction IDs in the block
    construction_pattern = r'(\d+-C\d+)'
    matches = list(re.finditer(construction_pattern, block))
    
    if not matches:
        return []
    
    for idx, match in enumerate(matches):
        full_id = match.group(1)  # e.g., "30705-C1"
        start_pos = match.end()
        
        # Get the chunk until the next construction or end
        if idx + 1 < len(matches):
            end_pos = matches[idx + 1].start()
        else:
            end_pos = len(block)
        
        data_chunk = block[start_pos:end_pos]
        
        # Also include text BEFORE the ID (same line) for surface
        line_start = block.rfind('\n', 0, match.start())
        pre_text = block[line_start:match.start()] if line_start != -1 else ""
        
        cid = full_id.split('-')[1]  # C1
        
        # Surface extraction - try multiple patterns
        surface = ""
        
        # Pattern 1: "S. construita la sol:XXX mp" or "S. construita:XXX"
        surf_match = re.search(r"S\.\s*construita[^:]*:?\s*(\d+)", data_chunk, re.IGNORECASE)
        if surf_match:
            surface = surf_match.group(1)
        
        # Pattern 2: "Supraf. (mp)" column - number on its own line after destination
        if not surface:
            # Look for standalone number (surface) after construction type
            nums = re.findall(r'\n(\d{2,5})\n', data_chunk)
            for n in nums:
                if 10 <= int(n) <= 50000 and not (1900 < int(n) < 2030):
                    surface = n
                    break
        
        # Pattern 3: Number right after text like "constructii industriale"
        if not surface:
            surf_inline = re.search(r'(?:constructii|anexa|locuinta|garaj)\s*\n?\s*(\d{2,5})', data_chunk, re.IGNORECASE)
            if surf_inline and not (1900 < int(surf_inline.group(1)) < 2030):
                surface = surf_inline.group(1)
        
        # Pattern 4: Check the line before the ID
        if not surface and pre_text:
            nums = re.findall(r'(\d{2,5})', pre_text)
            for n in nums:
                if 10 <= int(n) <= 50000 and not (1900 < int(n) < 2030):
                    surface = n
                    break

        # Desfasurata surface
        surf_desf = ""
        desf_match = re.search(r"desfasurata:?\s*(\d+)", data_chunk, re.IGNORECASE)
        if desf_match:
            surf_desf = desf_match.group(1)

        # Destination
        dest = "Cladire"
        if "locuinta" in data_chunk.lower(): dest = "Locuinta"
        elif "anexa" in data_chunk.lower(): dest = "Anexa"
        elif "garaj" in data_chunk.lower(): dest = "Garaj"
        elif "magazie" in data_chunk.lower(): dest = "Magazie"
        elif "industrial" in data_chunk.lower(): dest = "Industrial"
        elif "piata" in data_chunk.lower(): dest = "Piata"

        # Year
        year_match = re.search(r"\b(19\d{2}|20\d{2})\b", data_chunk)
        year = year_match.group(1) if year_match else ""

        # Material
        material = ""
        if "beton" in data_chunk.lower(): material = "Beton"
        elif "caramida" in data_chunk.lower(): material = "Caramida"
        elif "lemn" in data_chunk.lower(): material = "Lemn"
        elif "paianta" in data_chunk.lower(): material = "Paianta"

        # Floor info
        obs = ""
        floor_match = re.search(r"\b((?:S\+)?P(?:\+\d+)?(?:\+M)?)\b", data_chunk, re.IGNORECASE)
        if floor_match:
            obs = floor_match.group(1)
        
        # Nr niveluri  
        nr_niv = ""
        niv_match = re.search(r"Nr\.\s*niveluri:?\s*(\d+)", data_chunk, re.IGNORECASE)
        if niv_match:
            nr_niv = niv_match.group(1)

        buildings.append({
            "nr": cid,
            "destinatie": dest,
            "surface": surface,
            "surface_desf": surf_desf,
            "year": year,
            "material": material,
            "obs": obs,
            "nr_niv": nr_niv
        })

    return buildings

def parse_record(filename: str, text: str) -> List[Dict]:
    """Main Orchestrator."""
    clean_txt = clean_text(text)
    
    cf_num = extract_cf_number(clean_txt)
    cad_num = extract_cadastral_number(clean_txt)
    uat, loc = extract_uat_locality(clean_txt)
    owner, cota, mod, act = extract_owner_details(clean_txt)
    surf_meas, surf_doc, terrain_obs = extract_parcel_data(clean_txt)
    sarcini = extract_sarcini(clean_txt)
    buildings = extract_constructions(clean_txt, cad_num)
    
    cerere = ""
    cerere_match = re.search(r"Cerere\s+nr\.\s*(\d+)", clean_txt, re.IGNORECASE)
    if cerere_match: cerere = cerere_match.group(1)
    
    data_em = ""
    date_match = re.search(r"Ziua\s+(\d{2})\s+Luna\s+(\d{2})\s+Anul\s+(\d{4})", clean_txt)
    if date_match: data_em = f"{date_match.group(1)}/{date_match.group(2)}/{date_match.group(3)}"

    records = []
    
    if buildings:
        for b in buildings:
            records.append({
                "Nume_Fisier": filename,
                "Numar_CF": cf_num,
                "UAT": uat,
                "Localitate": loc,
                "Numar_Cadastral": f"{cad_num}-{b['nr']}",
                "Numar_Topografic": "",
                "Adresa_Imobil": f"{loc}, {uat}",
                "Suprafata_Masurata_MP": surf_meas,
                "Suprafata_Din_Act_MP": surf_doc,
                "Observatii_Teren": terrain_obs,
                "Nr_Constructie": b['nr'],
                "Destinatie_Constructie": b['destinatie'],
                "Suprafata_Construita_MP": b['surface'],
                "Suprafata_Desfasurata_MP": b['surface_desf'],
                "An_Constructie": b['year'],
                "Nr_Niveluri": b['nr_niv'],
                "Observatii_Constructie": b['obs'],
                "Proprietari": owner,
                "Cota_Proprietate": cota,
                "Mod_Dobandire": mod,
                "Act_Proprietate": act,
                "Sarcini": sarcini,
                "Data_Emitere_Extras": data_em,
                "Numar_Cerere": cerere
            })
    else:
        records.append({
            "Nume_Fisier": filename,
            "Numar_CF": cf_num,
            "UAT": uat,
            "Localitate": loc,
            "Numar_Cadastral": cad_num,
            "Numar_Topografic": "",
            "Adresa_Imobil": f"{loc}, {uat}",
            "Suprafata_Masurata_MP": surf_meas,
            "Suprafata_Din_Act_MP": surf_doc,
            "Observatii_Teren": terrain_obs,
            "Nr_Constructie": "",
            "Destinatie_Constructie": "",
            "Suprafata_Construita_MP": "",
            "Suprafata_Desfasurata_MP": "",
            "An_Constructie": "",
            "Nr_Niveluri": "",
            "Observatii_Constructie": "",
            "Proprietari": owner,
            "Cota_Proprietate": cota,
            "Mod_Dobandire": mod,
            "Act_Proprietate": act,
            "Sarcini": sarcini,
            "Data_Emitere_Extras": data_em,
            "Numar_Cerere": cerere
        })
        
    return records
