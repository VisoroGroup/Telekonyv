import os

INPUT_DIR = "input_pdfs"
OUTPUT_DIR = "output_excel"
TEMP_DIR = "temp_images"
FAILED_LOG = "failed_pdfs.txt"

# Complete column set for Romanian Carte Funciară extraction
COLUMNS = [
    # Validation
    "Status_Validare",
    "Mesaj_Eroare",
    
    # File info
    "Nume_Fisier",
    
    # Part A - Property identification
    "Numar_CF",
    "UAT",
    "Localitate",
    "Numar_Cadastral",
    "Numar_Topografic",
    "Adresa_Imobil",
    "Suprafata_Masurata_MP",
    "Suprafata_Din_Act_MP",
    "Observatii_Teren",
    
    # Constructions (Part A continued)
    "Nr_Constructie",
    "Destinatie_Constructie",
    "Suprafata_Construita_MP",
    "Suprafata_Desfasurata_MP",
    "An_Constructie",
    "Nr_Niveluri",
    "Observatii_Constructie",
    
    # Part B - Owners
    "Proprietari",
    "Cota_Proprietate",
    "Mod_Dobandire",
    "Act_Proprietate",
    
    # Part C - Encumbrances
    "Sarcini",
    
    # Metadata
    "Data_Emitere_Extras",
    "Numar_Cerere"
]

MIN_TEXT_CHARS = 150
MIN_ALPHA_RATIO = 0.05
