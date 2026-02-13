import re
from typing import List, Dict, Tuple

def clean_text(text: str) -> str:
    """Standardize text for easier regex matching."""
    if not text: return ""
    text = text.replace('\r', '')
    # Replace ALL Romanian diacritic variants (both cedilla AND comma-below forms)
    text = text.replace('ţ', 't').replace('ș', 's').replace('ş', 's').replace('ă', 'a').replace('î', 'i').replace('â', 'a').replace('ț', 't')
    text = text.replace('Ţ', 'T').replace('Ș', 'S').replace('Ş', 'S').replace('Ă', 'A').replace('Î', 'I').replace('Â', 'A').replace('Ț', 'T')
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
    Strategy: Find the LAST valid Intabulare block (cota != 0/1) and extract owners from there.
    """
    # Fixed regex: read B section until C. Partea III (not stopping at "Anexa" in middle of text)
    part_ii_match = re.search(r"B\.\s*Partea\s+II.*?(?=C\.\s*Partea\s+III)", text, re.IGNORECASE | re.DOTALL)
    if not part_ii_match:
        return "Fara proprietar identificat", "", "", "", ""
    
    part_ii = part_ii_match.group(0)
    
    if "proprietar neidentificat" in part_ii.lower():
        return "Proprietar neidentificat", "1/1", "Lege", "", ""

    # === STRATEGY: Find last valid Intabulare block with owners ===
    # Split Part II into B-blocks (B1, B2, B3, ...) and find those with Intabulare + numbered owners
    # The LAST one with cota_actuala != 0/1 (or missing Radiat) is the current owner
    
    owners = []
    best_owners = []
    best_cota = ""
    
    # Find all Intabulare blocks with their content
    # Pattern: B\d+ ... Intabulare ... owners ... until next B\d+ or end
    intabulare_blocks = list(re.finditer(
        r'B(\d+)\s+(?:Intabulare|intabulare)',
        part_ii
    ))
    
    for idx, ib_match in enumerate(intabulare_blocks):
        b_num = ib_match.group(1)
        start = ib_match.start()
        
        # Find end of this block (next B-block or end of Part II)
        if idx + 1 < len(intabulare_blocks):
            end = intabulare_blocks[idx + 1].start()
        else:
            # Find next major section marker
            next_section = re.search(r'\n(?:B\d+\s)', part_ii[ib_match.end():])
            if next_section:
                end = ib_match.end() + next_section.start()
            else:
                end = len(part_ii)
        
        block = part_ii[start:end]
        
        # Skip blocks that are "se noteaza" (notes, not ownership)
        if re.search(r'B\d+\s+se\s+noteaza', block, re.IGNORECASE):
            continue
        
        # Skip SERVITUTE blocks
        if 'SERVITUTE' in block.upper():
            continue
        
        # Check if this block has been radiata (cancelled)
        if re.search(r'Radiat[a|ă]?\s+prin', block, re.IGNORECASE):
            continue
        
        # Check cota - skip blocks with cota actuala 0/1 (transferred ownership)
        cota_match = re.search(r'cota\s+actuala\s+(\d+/\d+)', block, re.IGNORECASE)
        if cota_match and cota_match.group(1) == '0/1':
            continue
        
        # Extract numbered owners from this block: 1) NAME, 2) NAME, etc.
        block_owners = []
        owner_matches = re.finditer(
            r'(\d+)\)\s*([A-Za-z][A-Za-z\s\.\,\-\"\'\(\)]+?)(?=\n\d+\)|\n\d{4,6}\s*/|\n(?:Act|OBSERV|B\d|A\d|Radiat|Document|se\s+noteaz)|\Z)',
            block
        )
        
        for om in owner_matches:
            clean_name = om.group(2).strip()
            # Clean up trailing info
            clean_name = re.sub(r',\s*(?:casatorit|necasatorit|ca\s+bun|bun\s+comun|bun\s+propriu|domeniu\s+privat).*$', '', clean_name, flags=re.IGNORECASE)
            clean_name = re.sub(r',\s*$', '', clean_name).strip()
            
            if len(clean_name) > 2 and "INTABULARE" not in clean_name.upper() and "DREPT DE" not in clean_name.upper():
                if clean_name not in block_owners:
                    block_owners.append(clean_name)
        
        if block_owners:
            best_owners = block_owners
            if cota_match:
                best_cota = cota_match.group(1)
            else:
                # Try to find cota anywhere in block
                any_cota = re.search(r'cota\s+(?:actuala\s+)?(\d+/\d+)', block, re.IGNORECASE)
                if any_cota:
                    best_cota = any_cota.group(1)
    
    owners = best_owners
    
    # === FALLBACK PATTERNS (if no Intabulare blocks found owners) ===
    
    # Fallback 1: Simple numbered pattern anywhere in Part II
    if not owners:
        numbered_matches = re.finditer(
            r'(\d+)\)\s*([A-Za-z][A-Za-z\s\.\,\-\"\'\(\)]+?)(?=\n\d+\)|\n\d{4,6}\s*/|\n(?:Act|OBSERV|B\d|A\d|Radiat|Document)|\Z)',
            part_ii
        )
        for om in numbered_matches:
            clean_name = om.group(2).strip()
            clean_name = re.sub(r',\s*(?:casatorit|necasatorit|ca\s+bun|bun\s+comun|bun\s+propriu|domeniu\s+privat).*$', '', clean_name, flags=re.IGNORECASE)
            clean_name = re.sub(r',\s*$', '', clean_name).strip()
            if len(clean_name) > 2 and "INTABULARE" not in clean_name.upper() and "DREPT DE" not in clean_name.upper():
                if clean_name not in owners:
                    owners.append(clean_name)
    
    # Fallback 2: Special entities - STATE, AGENCIES, etc.
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
    
    # Fallback 3: Companies (S.A., S.R.L.) — require word boundary on SA/SRL to avoid false matches
    if not owners:
        company_match = re.search(r'(?:S\.C\.\s*)?([A-ZĂÂÎȘȚa-zăâîșț\s\.\-]+(?:S\.A\.|S\.R\.L\.|\bSA\b|\bSRL\b))', part_ii)
        if company_match:
            name = company_match.group(1).strip()
            if len(name) > 3:  # Must be more than just "SA"
                owners.append(name)
    
    # Fallback 4: Municipalities
    if not owners:
        muni_match = re.search(r'((?:MUNICIPIUL|JUDETUL|COMUNA|ORASUL|Municipiul|Judetul|Comuna|Orasul)\s+[A-Za-z]+)', part_ii)
        if muni_match:
            owners.append(muni_match.group(1).strip())
    
    # Fallback 5: Search in full text for MUNICIPIUL with uppercase city name
    if not owners:
        muni_full = re.search(r'((?:MUNICIPIUL|JUDETUL|COMUNA|ORASUL)\s+[A-Z]+)', text)
        if muni_full:
            owners.append(muni_full.group(1).strip())
    
    # Fallback 6: Person names - UPPERCASE format "LASTNAME FIRSTNAME"
    if not owners:
        person_pattern = r'1\)\s*([A-Z][A-Z\-]+\s+[A-Z][A-Za-z\-]+)'
        person_match = re.search(person_pattern, part_ii)
        if person_match:
            owners.append(person_match.group(1).strip())
    
    owner_str = " & ".join(owners[:3]) if owners else "Nedetectat"

    # 2. Extract Cota (use best_cota from block analysis, or find in whole section)
    cota = best_cota
    if not cota:
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

    # 5. Extract FULL owner history with dates
    owner_history = extract_owner_history(part_ii)

    return owner_str, cota, mod, act, owner_history


def extract_owner_history(part_ii: str) -> str:
    """
    Extract all owners with their registration dates in chronological order.
    Returns a string like: "2009-04-15: BUHAI ANATOLI, BUHAI MARUSEA | 2012-12-18: MOCANU VALENTIN"
    """
    history_entries = []
    
    # Find all B blocks with dates: "12345 / DD/MM/YYYY" followed by owner info
    # Pattern: number / date + block until next number/date or end
    blocks = re.split(r'(\d{4,6}\s*/\s*\d{2}/\d{2}/\d{4})', part_ii)
    
    for i in range(1, len(blocks), 2):
        if i+1 >= len(blocks):
            continue
            
        date_str = blocks[i]  # e.g., "11944 / 15/04/2009"
        block_content = blocks[i+1]
        
        # Extract date
        date_match = re.search(r'(\d{2})/(\d{2})/(\d{4})', date_str)
        if not date_match:
            continue
        day, month, year = date_match.groups()
        formatted_date = f"{year}-{month}-{day}"
        
        # Only include blocks with Intabulare (actual ownership registration)
        if 'intabulare' not in block_content.lower():
            continue
        
        # Extract owners from this block
        block_owners = []
        
        # Find numbered owners: 1), 2), 3), etc.
        owner_matches = re.findall(
            r'(\d+)\)\s*([A-Za-z][A-Za-z\s\.\,\-\"\'\(\)]+?)(?=\n(?:\d+\)|Act|OBSERV|B\d|A\d|Document|se\s+noteaza)|\n\d{4,6}\s*/|\Z)',
            block_content
        )
        
        for num, owner_name in owner_matches:
            clean_name = owner_name.strip()
            # Clean up trailing commas and common words
            clean_name = re.sub(r',\s*domeniu\s+privat.*$', '', clean_name, flags=re.IGNORECASE)
            clean_name = re.sub(r',\s*in\s+indiviziune.*$', '', clean_name, flags=re.IGNORECASE)
            clean_name = re.sub(r',\s*casatorit.*$', '', clean_name, flags=re.IGNORECASE)
            clean_name = re.sub(r',\s*$', '', clean_name).strip()
            
            if clean_name and len(clean_name) > 2 and "INTABULARE" not in clean_name.upper():
                if clean_name not in block_owners:
                    block_owners.append(clean_name)
        
        if block_owners:
            owners_str = ", ".join(block_owners[:5])  # Max 5 owners per entry
            history_entries.append(f"{formatted_date}: {owners_str}")
    
    # Return chronologically sorted (oldest first)
    if history_entries:
        # Sort by date
        history_entries.sort(key=lambda x: x[:10])
        return " | ".join(history_entries)
    
    return ""

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

    # If no measured surface found, try table format
    if not measured:
        # Pattern 1: A1 with number on same line
        table_match = re.search(r"A1[^\d\n]+[0-9\-/]+[^\d\n]+(\d{1,3}(?:\.\d{3})*)", text)
        if table_match: measured = table_match.group(1).replace('.', '')
    
    # Pattern 2: Multi-line format where surface is on next line after cadastral number
    # Example: "A1 CAD: 6886-\n5094/1 965\n" -> surface is 965
    if not measured:
        multi_line = re.search(r"A1\s+(?:CAD:?\s*)?[\d\-/]+[\s\-]*\n[\d/]+\s+(\d{2,6})\s*\n", text)
        if multi_line:
            measured = multi_line.group(1)
    
    # Pattern 3: Just look for standalone number after A1 line
    if not measured:
        a1_section = re.search(r"A1\s.*?(?=B\.\s*Partea)", text, re.DOTALL)
        if a1_section:
            nums = re.findall(r'\s(\d{2,6})\s', a1_section.group(0))
            for n in nums:
                if 10 <= int(n) <= 500000:  # Reasonable surface range
                    measured = n
                    break

    return measured, doc_surf, obs

def extract_constructions(text: str, cad_base: str) -> List[Dict]:
    """Extract construction data from the document."""
    buildings = []
    
    # FIRST: Check for A1.x format in "A. Partea I" section (embedded constructions)
    # This format often has MORE buildings than "Date referitoare" section
    # Format: A1.1 31573-C1 ... \n ... \n Nr. niveluri:1; S. construita la sol:20 mp; ... \n REMIZA P.S.I.
    part_a = re.search(r'A\.\s*Partea\s+I.*?(?=B\.\s*Partea\s+II)', text, re.IGNORECASE | re.DOTALL)
    if part_a:
        part_a_text = part_a.group(0)
        
        # Find all A1.x blocks - each block spans multiple lines until the next A1.x
        # Handle variants: A1.1 XXX-C1, *A1.1 CAD: XXX-C1, A1.1 CAD: XXX-C1
        a1x_starts = list(re.finditer(r'\*?A1\.(\d+)\s+(?:CAD:\s*)?(\d+-C\d+)', part_a_text))
        
        if a1x_starts:
            for i, match in enumerate(a1x_starts):
                a1_idx = match.group(1)
                full_id = match.group(2)
                cid = full_id.split('-')[1] if '-' in full_id else f"C{a1_idx}"
                
                # Get the block until the next A1.x or end of section
                start_pos = match.start()
                if i + 1 < len(a1x_starts):
                    end_pos = a1x_starts[i + 1].start()
                else:
                    end_pos = len(part_a_text)
                
                block = part_a_text[start_pos:end_pos]
                
                # Extract surface from block - "S. construita la sol:XX mp" (may have decimals)
                surface = ""
                surf_match = re.search(r'S\.\s*construita\s+la\s+sol:\s*(\d+(?:[.,]\d+)?)\s*mp', block, re.IGNORECASE)
                if surf_match:
                    # Round to integer
                    surface = str(int(round(float(surf_match.group(1).replace(',', '.')))))
                
                # Pattern 2: "suprafata construita de XXX mp" or "in suprafata de XXX mp"
                if not surface:
                    inline_match = re.search(r'(?:suprafata|suprafață)\s+(?:construita\s+)?de\s+(\d+(?:[.,]\d+)?)\s*m\.?p', block, re.IGNORECASE)
                    if inline_match:
                        surface = str(int(round(float(inline_match.group(1).replace(',', '.')))))
                
                # Pattern 3: "s.c. de XXX m.p."
                if not surface:
                    sc_match = re.search(r's\.c\.?\s+de\s+(\d+(?:[.,]\d+)?)\s*m\.?p', block, re.IGNORECASE)
                    if sc_match:
                        surface = str(int(round(float(sc_match.group(1).replace(',', '.')))))
                
                # Extract S. construita desfasurata
                surf_desf = ""
                desf_match = re.search(r'desfasurata:?\s*(\d+(?:\.\d+)?)\s*mp', block, re.IGNORECASE)
                if desf_match:
                    surf_desf = str(int(round(float(desf_match.group(1)))))
                # Also check for "Sup.desfasurata=XXX mp" format
                if not surf_desf:
                    desf_match2 = re.search(r'Sup\.?\s*desfasurata\s*=\s*(\d+)', block, re.IGNORECASE)
                    if desf_match2:
                        surf_desf = desf_match2.group(1)
                
                # Extract nr niveluri
                nr_niv = ""
                niv_match = re.search(r'Nr\.\s*niveluri:\s*(\d+)', block, re.IGNORECASE)
                if niv_match:
                    nr_niv = niv_match.group(1)
                
                # Extract year - multiple patterns
                year = ""
                # Pattern 1: "an XXXX" at end (e.g., "P+1+M, an 2008")
                year_match = re.search(r',?\s*an\s+(19\d{2}|20\d{2})', block, re.IGNORECASE)
                if year_match:
                    year = year_match.group(1)
                # Pattern 2: "Anul construirii XXXX"
                if not year:
                    year_match2 = re.search(r'Anul\s+construirii\s+(19\d{2}|20\d{2})', block, re.IGNORECASE)
                    if year_match2:
                        year = year_match2.group(1)
                # Pattern 3: Standalone year (less reliable, use as fallback)
                if not year:
                    year_match3 = re.search(r'\b(19[5-9]\d|20[0-2]\d)\b', block)
                    if year_match3:
                        year = year_match3.group(1)
                
                # Material extraction
                material = ""
                block_lower = block.lower()
                if "beton" in block_lower: material = "Beton"
                elif "caramida" in block_lower or "cărămidă" in block_lower: material = "Caramida"
                elif "lemn" in block_lower: material = "Lemn"
                elif "paianta" in block_lower or "paiantă" in block_lower: material = "Paianta"
                elif "metal" in block_lower: material = "Metal"
                
                # Floor info (obs)
                obs = ""
                floor_match = re.search(r'\b((?:S\+)?P(?:\+\d+)?(?:\+M)?)\b', block, re.IGNORECASE)
                if floor_match:
                    obs = floor_match.group(1).upper()
                
                # Destination - from the entire block (more specific patterns first)
                dest = "Cladire"
                if "spatii comerciale" in block_lower or "spatiu comercial" in block_lower: dest = "Spatii Comerciale"
                elif "pensiune" in block_lower: dest = "Pensiune"
                elif "cheu" in block_lower or "bazin" in block_lower: dest = "Cheu"
                elif "vestiar" in block_lower: dest = "Vestiar"
                elif "sediu" in block_lower: dest = "Sediu"
                elif "casa de locuit" in block_lower or "casa" in block_lower: dest = "Locuinta"
                elif "locuinta" in block_lower or "locuințe" in block_lower or "locuinte" in block_lower: dest = "Locuinta"
                elif "constructii de locuinte" in block_lower: dest = "Locuinta"
                elif "constructii anexa" in block_lower: dest = "Anexa"
                elif "anexa" in block_lower or "anexe" in block_lower: dest = "Anexa"
                elif "garaj" in block_lower: dest = "Garaj"
                elif "grajd" in block_lower: dest = "Grajd"
                elif "magazie" in block_lower: dest = "Magazie"
                elif "remiza" in block_lower or "remiza p.s.i" in block_lower: dest = "Remiza"
                elif "post trafo" in block_lower: dest = "Post Trafo"
                elif "birou" in block_lower or "birouri" in block_lower: dest = "Birouri"
                elif "cabina" in block_lower: dest = "Cabina"
                elif "punct termic" in block_lower: dest = "Punct Termic"
                elif "constructii industriale" in block_lower or "industrial" in block_lower: dest = "Industrial"
                elif "laborator" in block_lower or "cofetarie" in block_lower: dest = "Industrial"
                elif "atelier" in block_lower: dest = "Atelier"
                elif "depozit" in block_lower: dest = "Depozit"
                elif "hala" in block_lower: dest = "Hala"
                elif "imprejmuire" in block_lower or "gard" in block_lower: dest = "Imprejmuire"
                elif "sopron" in block_lower: dest = "Sopron"
                elif "beci" in block_lower or "pivnita" in block_lower: dest = "Beci"
                elif "wc" in block_lower or "toaleta" in block_lower: dest = "WC"
                elif "terasa" in block_lower: dest = "Terasa"
                elif "centrala" in block_lower: dest = "Centrala"
                elif "statie" in block_lower: dest = "Statie"
                elif "piscina" in block_lower: dest = "Piscina"
                
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
            
            # Try to fill missing surfaces from B. Partea II notes
            # Pattern: "constructia C1 in suprafata construita de 15 m.p."
            # or "constructia C2 in s.c. de 15 m.p."
            part_b = re.search(r'B\.\s*Partea\s+II.*?(?=C\.\s*Partea\s+III)', text, re.DOTALL | re.IGNORECASE)
            if part_b:
                b_text = part_b.group(0)
                for b in buildings:
                    if not b['surface']:
                        cid_num = b['nr'].replace('C', '')
                        # Pattern: "constructia C1 in suprafata construita de XX m.p."
                        bp_match = re.search(
                            rf'constructi[ai]\s+C{cid_num}\s+(?:in\s+)?(?:suprafata\s+(?:construita\s+)?de|s\.c\.?\s+de)\s+(\d+(?:[.,]\d+)?)\s*m\.?p',
                            b_text, re.IGNORECASE
                        )
                        if bp_match:
                            b['surface'] = str(int(round(float(bp_match.group(1).replace(',', '.')))))
            
            return buildings
    
    # SECOND (fallback): Find the "Date referitoare la constructii" section
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

        # Desfasurata surface - multiple patterns
        surf_desf = ""
        desf_match = re.search(r"desfasurata:?\s*(\d+(?:\.\d+)?)\s*mp", data_chunk, re.IGNORECASE)
        if desf_match:
            surf_desf = str(int(round(float(desf_match.group(1)))))
        # Also check for "Sup.desfasurata=XXX mp" format
        if not surf_desf:
            desf_match2 = re.search(r"Sup\.?\s*desfasurata\s*=\s*(\d+)", data_chunk, re.IGNORECASE)
            if desf_match2:
                surf_desf = desf_match2.group(1)

        # Destination - more specific patterns first
        dest = "Cladire"
        chunk_lower = data_chunk.lower()
        if "spatii comerciale" in chunk_lower or "spatiu comercial" in chunk_lower: dest = "Spatii Comerciale"
        elif "pensiune" in chunk_lower: dest = "Pensiune"
        elif "cheu" in chunk_lower or "bazin" in chunk_lower: dest = "Cheu"
        elif "vestiar" in chunk_lower: dest = "Vestiar"
        elif "sediu" in chunk_lower: dest = "Sediu"
        elif "locuinta" in chunk_lower or "locuințe" in chunk_lower or "locuinte" in chunk_lower: dest = "Locuinta"
        elif "anexa" in chunk_lower: dest = "Anexa"
        elif "garaj" in chunk_lower: dest = "Garaj"
        elif "magazie" in chunk_lower: dest = "Magazie"
        elif "remiza" in chunk_lower: dest = "Remiza"
        elif "post trafo" in chunk_lower: dest = "Post Trafo"
        elif "birou" in chunk_lower: dest = "Birouri"
        elif "cabina" in chunk_lower: dest = "Cabina"
        elif "punct termic" in chunk_lower: dest = "Punct Termic"
        elif "industrial" in chunk_lower: dest = "Industrial"
        elif "atelier" in chunk_lower: dest = "Atelier"
        elif "depozit" in chunk_lower: dest = "Depozit"
        elif "hala" in chunk_lower: dest = "Hala"
        elif "imprejmuire" in chunk_lower or "gard" in chunk_lower: dest = "Imprejmuire"
        elif "sopron" in chunk_lower: dest = "Sopron"
        elif "beci" in chunk_lower or "pivnita" in chunk_lower: dest = "Beci"
        elif "wc" in chunk_lower or "toaleta" in chunk_lower: dest = "WC"
        elif "terasa" in chunk_lower: dest = "Terasa"
        elif "centrala" in chunk_lower: dest = "Centrala"
        elif "statie" in chunk_lower: dest = "Statie"
        elif "piscina" in chunk_lower: dest = "Piscina"
        elif "piata" in chunk_lower: dest = "Piata"

        # Year - multiple patterns
        year = ""
        # Pattern 1: "an XXXX" at end
        year_match = re.search(r',?\s*an\s+(19\d{2}|20\d{2})', data_chunk, re.IGNORECASE)
        if year_match:
            year = year_match.group(1)
        # Pattern 2: "Anul construirii XXXX"
        if not year:
            year_match2 = re.search(r'Anul\s+construirii\s+(19\d{2}|20\d{2})', data_chunk, re.IGNORECASE)
            if year_match2:
                year = year_match2.group(1)
        # Pattern 3: Standalone year (less reliable)
        if not year:
            year_match3 = re.search(r'\b(19[5-9]\d|20[0-2]\d)\b', data_chunk)
            if year_match3:
                year = year_match3.group(1)

        # Material
        material = ""
        if "beton" in chunk_lower: material = "Beton"
        elif "caramida" in chunk_lower or "cărămidă" in chunk_lower: material = "Caramida"
        elif "lemn" in chunk_lower: material = "Lemn"
        elif "paianta" in chunk_lower or "paiantă" in chunk_lower: material = "Paianta"
        elif "metal" in chunk_lower: material = "Metal"

        # Floor info
        obs = ""
        floor_match = re.search(r"\b((?:S\+)?P(?:\+\d+)?(?:\+M)?)\b", data_chunk, re.IGNORECASE)
        if floor_match:
            obs = floor_match.group(1).upper()
        
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
    owner, cota, mod, act, owner_history = extract_owner_details(clean_txt)
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
                "Tulajdonos_Tortenelem": owner_history,
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
            "Tulajdonos_Tortenelem": owner_history,
            "Sarcini": sarcini,
            "Data_Emitere_Extras": data_em,
            "Numar_Cerere": cerere
        })
        
    return records
