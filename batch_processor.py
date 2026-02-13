"""
Robust Batch PDF Processor with checkpoint support.
Handles 5000+ PDFs reliably with progress tracking and error reporting.
"""
import json
import threading
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import pandas as pd

from text_extractor import extract_text
from parser import parse_record
from validator import validate_row
from config import COLUMNS, TEMP_DIR

# Constants
BATCH_SIZE = 100  # Process 100 PDFs at a time
CHECKPOINT_FILE = "checkpoint.json"
ERRORS_FILE = "errors.json"
PROGRESS_FILE = "progress.json"


class BatchProcessor:
    """
    Processes PDFs in batches with checkpoint support.
    Can resume from where it left off if interrupted.
    """
    
    def __init__(self, input_dir: Path, output_dir: Path):
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir = Path(TEMP_DIR)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
        self.checkpoint_path = self.output_dir / CHECKPOINT_FILE
        self.errors_path = self.output_dir / ERRORS_FILE
        self.progress_path = self.output_dir / PROGRESS_FILE
        self.excel_path = self.output_dir / "cadastral_data.xlsx"
        
        self.is_running = False
        self.should_stop = False
        
    def get_all_pdfs(self) -> List[Path]:
        """Get all PDF files from input directory (skip macOS resource forks)."""
        return sorted([
            p for p in self.input_dir.glob("*.pdf")
            if not p.name.startswith('._')
        ])
    
    def load_checkpoint(self) -> Dict:
        """Load checkpoint from file."""
        if self.checkpoint_path.exists():
            try:
                with open(self.checkpoint_path, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {"processed_files": [], "last_batch": 0}
    
    def save_checkpoint(self, processed_files: List[str], batch_num: int):
        """Save checkpoint to file."""
        checkpoint = {
            "processed_files": processed_files,
            "last_batch": batch_num,
            "timestamp": datetime.now().isoformat()
        }
        with open(self.checkpoint_path, 'w') as f:
            json.dump(checkpoint, f, indent=2)
    
    def load_errors(self) -> List[Dict]:
        """Load errors from file."""
        if self.errors_path.exists():
            try:
                with open(self.errors_path, 'r') as f:
                    return json.load(f)
            except:
                pass
        return []
    
    def save_errors(self, errors: List[Dict]):
        """Save errors to file."""
        with open(self.errors_path, 'w') as f:
            json.dump(errors, f, indent=2, ensure_ascii=False)
    
    def update_progress(self, current: int, total: int, status: str = "running"):
        """Update progress file."""
        progress = {
            "current": current,
            "total": total,
            "percent": round((current / total) * 100, 1) if total > 0 else 0,
            "status": status,
            "timestamp": datetime.now().isoformat()
        }
        with open(self.progress_path, 'w') as f:
            json.dump(progress, f, indent=2)
    
    def get_progress(self) -> Dict:
        """Get current progress."""
        if self.progress_path.exists():
            try:
                with open(self.progress_path, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {"current": 0, "total": 0, "percent": 0, "status": "idle"}
    
    def process_single_pdf(self, pdf_path: Path) -> Tuple[List[Dict], Optional[Dict]]:
        """
        Process a single PDF file.
        Returns: (records, error_info)
        """
        records = []
        error_info = None
        
        try:
            # Skip macOS resource fork files
            if pdf_path.name.startswith('._'):
                return [], None  # Silently skip, don't count as error
            
            # Check file size
            if pdf_path.stat().st_size == 0:
                return [], {"file": pdf_path.name, "type": "EMPTY_PDF", "details": "0 byte fájl"}
            
            # Extract text
            text, used_ocr = extract_text(pdf_path, self.temp_dir)
            
            if not text or len(text.strip()) < 50:
                return [], {"file": pdf_path.name, "type": "OCR_FAILED", "details": "Nem olvasható szöveg"}
            
            # Parse record
            parsed = parse_record(pdf_path.name, text)
            
            if not parsed:
                return [], {"file": pdf_path.name, "type": "PARSE_ERROR", "details": "Nem sikerült kinyerni adatokat"}
            
            # Validate and add records
            for record in parsed:
                status, msg = validate_row(record)
                record['Status_Validare'] = status
                record['Mesaj_Eroare'] = msg
                records.append(record)
            
            # Check if owner was found
            if records and records[0].get('Proprietari') == 'Nedetectat':
                error_info = {"file": pdf_path.name, "type": "NO_OWNER", "details": "Proprietar nem található"}
            
        except Exception as e:
            error_info = {"file": pdf_path.name, "type": "EXCEPTION", "details": str(e)[:200]}
        
        return records, error_info
    
    def process_batch(self, pdf_paths: List[Path]) -> Tuple[List[Dict], List[Dict]]:
        """
        Process a batch of PDFs.
        Returns: (all_records, errors)
        """
        all_records = []
        errors = []
        
        for pdf_path in pdf_paths:
            if self.should_stop:
                break
                
            records, error = self.process_single_pdf(pdf_path)
            all_records.extend(records)
            
            if error:
                errors.append(error)
        
        return all_records, errors
    
    def save_excel(self, all_data: List[Dict]):
        """Save all data to Excel file."""
        if all_data:
            df = pd.DataFrame(all_data, columns=COLUMNS)
            df = df.sort_values(by=['Status_Validare', 'Numar_CF'], ascending=[False, True])
            df.to_excel(self.excel_path, index=False)
    
    def run(self, resume: bool = True):
        """
        Run the batch processor.
        Set resume=True to continue from checkpoint.
        """
        self.is_running = True
        self.should_stop = False
        
        try:
            all_pdfs = self.get_all_pdfs()
            total_pdfs = len(all_pdfs)
            
            if total_pdfs == 0:
                self.update_progress(0, 0, "no_files")
                return
            
            # Load checkpoint if resuming
            checkpoint = self.load_checkpoint() if resume else {"processed_files": [], "last_batch": 0}
            processed_set = set(checkpoint.get("processed_files", []))
            
            # Load existing errors
            all_errors = self.load_errors() if resume else []
            
            # Load existing data if resuming
            all_data = []
            if resume and self.excel_path.exists():
                try:
                    existing_df = pd.read_excel(self.excel_path)
                    all_data = existing_df.to_dict('records')
                except:
                    pass
            
            # Filter out already processed PDFs
            remaining_pdfs = [p for p in all_pdfs if p.name not in processed_set]
            
            self.update_progress(len(processed_set), total_pdfs, "running")
            
            # Process in batches
            batch_num = checkpoint.get("last_batch", 0)
            
            for i in range(0, len(remaining_pdfs), BATCH_SIZE):
                if self.should_stop:
                    break
                
                batch = remaining_pdfs[i:i + BATCH_SIZE]
                batch_num += 1
                
                # Process batch
                batch_records, batch_errors = self.process_batch(batch)
                
                # Add to totals
                all_data.extend(batch_records)
                all_errors.extend(batch_errors)
                
                # Mark as processed
                for pdf in batch:
                    processed_set.add(pdf.name)
                
                # Save checkpoint and Excel after each batch
                self.save_checkpoint(list(processed_set), batch_num)
                self.save_excel(all_data)
                self.save_errors(all_errors)
                
                # Update progress
                self.update_progress(len(processed_set), total_pdfs, "running")
            
            # Final status
            status = "completed" if not self.should_stop else "stopped"
            self.update_progress(len(processed_set), total_pdfs, status)
            
        except Exception as e:
            self.update_progress(0, 0, f"error: {str(e)[:100]}")
        
        finally:
            self.is_running = False
    
    def stop(self):
        """Stop the processor gracefully."""
        self.should_stop = True
    
    def reset(self):
        """Reset checkpoint and errors to start fresh."""
        if self.checkpoint_path.exists():
            self.checkpoint_path.unlink()
        if self.errors_path.exists():
            self.errors_path.unlink()
        if self.progress_path.exists():
            self.progress_path.unlink()
    
    def get_error_report_csv(self) -> str:
        """Generate error report as CSV string."""
        errors = self.load_errors()
        if not errors:
            return "Nincs hiba!\n"
        
        lines = ["Fájlnév;Hiba típus;Részletek"]
        for err in errors:
            lines.append(f"{err['file']};{err['type']};{err['details']}")
        
        return "\n".join(lines)


# Global processor instance for the web app
_processor: Optional[BatchProcessor] = None
_processor_thread: Optional[threading.Thread] = None


def get_processor(input_dir: Path, output_dir: Path) -> BatchProcessor:
    """Get or create processor instance. Creates new if input dir changed."""
    global _processor
    input_path = Path(input_dir)
    
    # Create new processor if none exists or input dir changed
    if _processor is None or _processor.input_dir != input_path:
        _processor = BatchProcessor(input_path, output_dir)
    
    return _processor


def start_background_processing(input_dir: Path, output_dir: Path, resume: bool = True):
    """Start processing in background thread."""
    global _processor, _processor_thread
    
    # Always create new processor for the specified input dir
    _processor = BatchProcessor(Path(input_dir), Path(output_dir))
    
    if _processor.is_running:
        return False, "Feldolgozás már folyamatban"
    
    # Reset if not resuming
    if not resume:
        _processor.reset()
    
    _processor_thread = threading.Thread(target=_processor.run, args=(resume,), daemon=True)
    _processor_thread.start()
    
    # Count PDFs for message
    pdf_count = len(_processor.get_all_pdfs())
    return True, f"Feldolgozás elindítva ({pdf_count} PDF)"


def stop_background_processing():
    """Stop background processing."""
    global _processor
    if _processor:
        _processor.stop()
        return True, "Feldolgozás leállítva"
    return False, "Nincs futó feldolgozás"

