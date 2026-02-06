import os
import pandas as pd
from pathlib import Path
from config import INPUT_DIR, OUTPUT_DIR, COLUMNS, TEMP_DIR
from text_extractor import extract_text
from parser import parse_record
from validator import validate_row

def process_batch():
    input_path = Path(INPUT_DIR)
    output_path = Path(OUTPUT_DIR)
    input_path.mkdir(parents=True, exist_ok=True)
    output_path.mkdir(parents=True, exist_ok=True)
    Path(TEMP_DIR).mkdir(parents=True, exist_ok=True)

    all_pdfs = list(input_path.glob("*.pdf"))
    print(f"=== STARTED PROCESSING {len(all_pdfs)} FILES ===")
    
    all_data = []
    
    for i, pdf_file in enumerate(all_pdfs, 1):
        try:
            print(f"[{i}/{len(all_pdfs)}] Processing: {pdf_file.name}")
            text, _ = extract_text(pdf_file, Path(TEMP_DIR))
            
            if text:
                records = parse_record(pdf_file.name, text)
                for record in records:
                    status, msg = validate_row(record)
                    record['Status_Validare'] = status
                    record['Mesaj_Eroare'] = msg
                    all_data.append(record)
            else:
                print(f"   [WARN] No text found in {pdf_file.name}")
                
        except Exception as e:
            print(f"   [ERROR] Failed: {e}")

    if all_data:
        df = pd.DataFrame(all_data, columns=COLUMNS)
        # Sort "VERIFICA" to top
        df = df.sort_values(by=['Status_Validare', 'Numar_CF'], ascending=[False, True])
        
        outfile = output_path / "Registru_Cadastral_Export.xlsx"
        df.to_excel(outfile, index=False)
        print(f"\n=== SUCCESS! Saved to {outfile} ===")
    else:
        print("\n[!] No data extracted.")

# Wrapper for web app compatibility
def process_pdfs_from_dir(input_dir, output_dir):
    """Process PDFs from specified directories (for web interface)."""
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    Path(TEMP_DIR).mkdir(parents=True, exist_ok=True)
    
    all_pdfs = list(input_path.glob("*.pdf"))
    all_data = []
    
    for pdf_file in all_pdfs:
        try:
            text, _ = extract_text(pdf_file, Path(TEMP_DIR))
            if text:
                records = parse_record(pdf_file.name, text)
                for record in records:
                    status, msg = validate_row(record)
                    record['Status_Validare'] = status
                    record['Mesaj_Eroare'] = msg
                    all_data.append(record)
        except Exception:
            pass
    
    if all_data:
        df = pd.DataFrame(all_data, columns=COLUMNS)
        df = df.sort_values(by=['Status_Validare', 'Numar_CF'], ascending=[False, True])
        df.to_excel(output_path / "cadastral_data.xlsx", index=False)
    
    return len(all_pdfs), len(all_data) 

if __name__ == "__main__":
    process_batch()
