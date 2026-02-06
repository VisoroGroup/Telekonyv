"""
Optimized text extraction for large batches (1000+ PDFs).
Improvements: better OCR detection, parallel processing support, memory management.
"""
import re
from pathlib import Path
from typing import Tuple
from pypdf import PdfReader
from pdf2image import convert_from_path
import pytesseract
from PIL import Image
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def extract_text_pypdf(pdf_path: Path) -> str:
    """Extract text from PDF using pypdf (text layer)."""
    try:
        reader = PdfReader(str(pdf_path))
        parts = []
        
        # Limit to first 10 pages for performance
        max_pages = min(10, len(reader.pages))
        
        for i in range(max_pages):
            try:
                page_text = reader.pages[i].extract_text()
                if page_text:
                    parts.append(page_text)
            except Exception as e:
                logging.warning(f"Page {i} extraction failed for {pdf_path.name}: {e}")
                continue
        
        return "\n".join(parts).strip()
    
    except Exception as e:
        logging.error(f"pypdf failed for {pdf_path.name}: {e}")
        return ""


def extract_text_ocr(pdf_path: Path, temp_dir: Path) -> str:
    """
    Convert PDF to images and OCR with Tesseract.
    Optimized for Romanian cadastral documents.
    """
    try:
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        # Convert only first 5 pages (cadastral docs are typically 3 pages)
        images = convert_from_path(
            str(pdf_path), 
            first_page=1, 
            last_page=5,
            dpi=300,  # Higher DPI for better OCR accuracy
            grayscale=True  # Faster processing
        )
        
        parts = []
        
        for i, image in enumerate(images):
            try:
                # Tesseract with Romanian language
                text = pytesseract.image_to_string(
                    image,
                    lang="ron",  # Romanian language pack
                    config='--psm 6 --oem 3'  # PSM 6 = uniform text block, OEM 3 = default
                )
                
                if text.strip():
                    parts.append(text)
            
            except Exception as e:
                logging.warning(f"OCR failed on {pdf_path.name} page {i}: {e}")
                continue
        
        result = "\n".join(parts).strip()
        
        # Cleanup: Romanian character normalization
        result = normalize_romanian_text(result)
        
        return result
    
    except Exception as e:
        logging.error(f"OCR conversion failed for {pdf_path.name}: {e}")
        return ""


def normalize_romanian_text(text: str) -> str:
    """Fix common OCR errors in Romanian text."""
    if not text:
        return ""
    
    # Common OCR misreads - normalize cedilla forms to comma-below forms
    replacements = {
        'ţ': 'ț',  # t-cedilla to t-comma-below
        'ş': 'ș',  # s-cedilla to s-comma-below
        'Ţ': 'Ț',  # T-cedilla to T-comma-below
        'Ş': 'Ș',  # S-cedilla to S-comma-below
        '|': 'I',  # Common OCR mistake: pipe to I
    }
    
    for old, new in replacements.items():
        text = text.replace(old, new)
    
    return text


def needs_ocr(text: str, min_chars: int = 150, min_alpha_ratio: float = 0.05) -> bool:
    """
    Determine if PDF needs OCR fallback.
    Enhanced logic for cadastral documents.
    """
    if not text or len(text) < min_chars:
        return True
    
    # Check for key cadastral terms (if missing, likely bad extraction)
    key_terms = ["CARTE", "FUNCIAR", "Proprietar", "Partea", "cadastral"]
    has_key_term = any(term.lower() in text.lower() for term in key_terms)
    
    if not has_key_term:
        return True
    
    # Check alphabetic ratio
    alpha_count = sum(1 for c in text if c.isalpha())
    ratio = alpha_count / max(len(text), 1)
    
    return ratio < min_alpha_ratio


def extract_text(pdf_path: Path, temp_dir: Path) -> Tuple[str, bool]:
    """
    Extract text from PDF with intelligent fallback.
    Returns: (text, used_ocr)
    """
    logging.info(f"Processing: {pdf_path.name}")
    
    # Step 1: Try direct text extraction
    text = extract_text_pypdf(pdf_path)
    
    # Step 2: Check if OCR is needed
    if not needs_ocr(text):
        logging.info(f"✓ {pdf_path.name} - Text layer OK")
        return text, False
    
    # Step 3: Fallback to OCR
    logging.info(f"↻ {pdf_path.name} - Using OCR (weak text layer)")
    text = extract_text_ocr(pdf_path, temp_dir)
    
    if text.strip():
        logging.info(f"✓ {pdf_path.name} - OCR successful")
        return text, True
    
    logging.warning(f"✗ {pdf_path.name} - Both methods failed")
    return text, True


def batch_extract_text(pdf_paths: list, temp_dir: Path, max_workers: int = 4):
    """
    Extract text from multiple PDFs in parallel (optional).
    Use for very large batches (500+).
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    results = {}
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_pdf = {
            executor.submit(extract_text, pdf, temp_dir): pdf 
            for pdf in pdf_paths
        }
        
        for future in as_completed(future_to_pdf):
            pdf_path = future_to_pdf[future]
            try:
                text, used_ocr = future.result()
                results[pdf_path] = (text, used_ocr)
            except Exception as e:
                logging.error(f"Failed to process {pdf_path.name}: {e}")
                results[pdf_path] = ("", True)
    
    return results
