"""
Flask web interface for Romanian Cadastral PDF Data Extractor.
Supports large batches (5000+ files) with background processing and progress tracking.
"""
from flask import Flask, render_template_string, request, send_file, redirect, url_for, jsonify, Response
from pathlib import Path
import shutil
import zipfile

from batch_processor import get_processor, start_background_processing, stop_background_processing

app = Flask(__name__)

app.config['MAX_CONTENT_LENGTH'] = 4096 * 1024 * 1024  # 4GB
app.config['MAX_FORM_MEMORY_SIZE'] = 4096 * 1024 * 1024

UPLOAD_DIR = Path("input_pdfs")
OUTPUT_DIR = Path("output_excel")

# ============================================================================
# HTML TEMPLATES
# ============================================================================

HTML_INDEX = """
<!doctype html>
<html>
<head>
    <title>Cadastral Extractor Pro</title>
    <meta charset="utf-8">
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 900px; margin: 40px auto; padding: 20px; background-color: #f9f9f9; }
        h1 { color: #2c3e50; text-align: center; }
        .container { background: white; padding: 40px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); }
        .section { border: 2px solid #e0e0e0; padding: 25px; border-radius: 8px; margin-bottom: 20px; }
        .section h3 { margin-top: 0; color: #2c3e50; }
        .upload-area { border: 2px dashed #bdc3c7; padding: 30px; text-align: center; border-radius: 8px; transition: 0.3s; }
        .upload-area:hover { border-color: #3498db; background: #f0f8ff; }
        input[type=file] { display: none; }
        input[type=text] { width: 100%; padding: 12px; font-size: 16px; border: 2px solid #ddd; border-radius: 5px; box-sizing: border-box; }
        input[type=text]:focus { border-color: #3498db; outline: none; }
        .file-label { background: #3498db; color: white; padding: 12px 25px; border-radius: 5px; cursor: pointer; display: inline-block; font-weight: bold; }
        .file-label:hover { background: #2980b9; }
        .submit-btn { background: #27ae60; color: white; padding: 15px 40px; border: none; border-radius: 5px; cursor: pointer; font-size: 18px; margin-top: 15px; width: 100%; transition: 0.3s; }
        .submit-btn:hover { background: #219150; }
        .submit-btn.folder { background: #9b59b6; }
        .submit-btn.folder:hover { background: #8e44ad; }
        .stats { color: #7f8c8d; text-align: center; margin-top: 10px; }
        .success-box { background: #d4edda; color: #155724; padding: 20px; border-radius: 8px; margin-top: 20px; text-align: center; border: 1px solid #c3e6cb; }
        .warning-box { background: #fff3cd; color: #856404; padding: 20px; border-radius: 8px; margin-top: 20px; text-align: center; border: 1px solid #ffeeba; }
        .error-box { background: #f8d7da; color: #721c24; padding: 20px; border-radius: 8px; margin-top: 20px; text-align: center; border: 1px solid #f5c6cb; }
        .action-btn { display: inline-block; padding: 10px 20px; margin: 5px; text-decoration: none; border-radius: 5px; font-weight: bold; }
        .download-btn { background: #007bff; color: white; }
        .clear-btn { background: #dc3545; color: white; }
        .progress-btn { background: #17a2b8; color: white; }
        .or-divider { text-align: center; margin: 20px 0; color: #999; font-weight: bold; }
        #loading { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(255,255,255,0.95); z-index: 1000; text-align: center; padding-top: 15%; }
        .spinner { border: 8px solid #f3f3f3; border-top: 8px solid #3498db; border-radius: 50%; width: 60px; height: 60px; animation: spin 1s linear infinite; margin: 0 auto 20px auto; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        #loading-text { font-size: 24px; color: #333; font-weight: bold; }
        #loading-subtext { font-size: 16px; color: #666; margin-top: 10px; }
    </style>
    <script>
        function updateFileName(input) {
            var fileName = input.files.length > 0 ? input.files.length + " fájl kiválasztva" : "Nincs kiválasztva";
            document.getElementById('file-name').textContent = fileName;
        }
        function showLoading() {
            document.getElementById('loading').style.display = 'block';
        }
    </script>
</head>
<body>
    <div id="loading">
        <div class="spinner"></div>
        <div id="loading-text">Feldolgozás indul...</div>
        <div id="loading-subtext">Kérlek várj...</div>
    </div>

    <h1>🏠 Telekkönyv Feldolgozó</h1>
    
    <div class="container">
        <!-- OPTION 1: Folder Path -->
        <div class="section">
            <h3>📂 1. Mappa megadása (ajánlott)</h3>
            <form method="post" action="/process-folder" onsubmit="showLoading()">
                <input type="text" name="folder_path" placeholder="/path/to/pdfs mappa" value="{{ last_folder or '' }}">
                <input type="submit" class="submit-btn folder" value="📂 MAPPA FELDOLGOZÁSA">
            </form>
            <p style="font-size: 12px; color: #999; margin-top: 10px;">Pl: /Users/visoro/PDFs vagy C:\\Documents\\PDFs</p>
        </div>
        
        <div class="or-divider">— VAGY —</div>
        
        <!-- OPTION 2: ZIP Upload (recommended for Railway) -->
        <div class="section" style="border-color: #27ae60;">
            <h3>📦 2. ZIP fájl feltöltése (ajánlott Railway-hez)</h3>
            <form method="post" action="/upload-zip" enctype="multipart/form-data" onsubmit="showLoading()">
                <div class="upload-area" style="border-color: #27ae60;">
                    <label for="zip-input" class="file-label" style="background: #27ae60;">📦 ZIP fájl kiválasztása</label>
                    <input id="zip-input" type="file" name="zipfile" accept=".zip">
                    <p id="zip-name" style="margin-top: 15px; font-size: 16px;">Max 1000+ PDF egyszerre!</p>
                </div>
                <input type="submit" class="submit-btn" value="📦 ZIP FELTÖLTÉS ÉS FELDOLGOZÁS">
            </form>
            <p style="font-size: 12px; color: #27ae60; margin-top: 10px;">💡 Tipp: Csomagold a PDF-eket ZIP-be és töltsd fel egyszerre!</p>
        </div>

        <div class="or-divider">— VAGY —</div>

        <!-- OPTION 3: Upload individual files -->
        <div class="section">
            <h3>📤 3. Egyedi fájlok feltöltése</h3>
            <form method="post" enctype="multipart/form-data" onsubmit="showLoading()">
                <div class="upload-area">
                    <label for="file-input" class="file-label">📁 PDF fájlok kiválasztása</label>
                    <input id="file-input" type="file" name="files" multiple accept=".pdf" onchange="updateFileName(this)">
                    <p id="file-name" style="margin-top: 15px; font-size: 16px;">Nincs kiválasztva</p>
                </div>
                <input type="submit" class="submit-btn" value="📤 FELTÖLTÉS ÉS FELDOLGOZÁS">
            </form>
        </div>

        {% if message %}
        <div class="success-box">
            <h2>{{ message }}</h2>
            <a href="/progress" class="action-btn progress-btn">📊 Feldolgozás állapota</a>
        </div>
        {% endif %}

        {% if error %}
        <div class="error-box">
            <h3>❌ {{ error }}</h3>
        </div>
        {% endif %}

        {% if is_processing %}
        <div class="warning-box">
            <h3>⏳ Feldolgozás folyamatban...</h3>
            <a href="/progress" class="action-btn progress-btn">📊 Folyamat megtekintése</a>
        </div>
        {% endif %}

        {% if excel_exists %}
        <div class="success-box" style="background: #e2e6ea; color: #333; border-color: #dae0e5;">
            <h3>Korábbi eredmény elérhető</h3>
            <a href="/download" class="action-btn download-btn">📥 Excel letöltése</a>
            <a href="/download-errors" class="action-btn" style="background: #ffc107; color: #333;">⚠️ Hiba riport</a>
            <a href="/clear" class="action-btn clear-btn">🗑️ Törlés</a>
        </div>
        {% endif %}

        <hr style="margin: 30px 0; border: none; border-top: 1px solid #ddd;">
        <div style="text-align: center;">
            <a href="/progress" class="action-btn" style="background: #6c757d; color: white;">📊 Feldolgozás állapota</a>
        </div>
    </div>
</body>
</html>
"""

HTML_PROGRESS = """
<!doctype html>
<html>
<head>
    <title>Feldolgozás állapota</title>
    <meta charset="utf-8">
    <meta http-equiv="refresh" content="3">
    <style>
        body { font-family: 'Segoe UI', sans-serif; max-width: 700px; margin: 40px auto; padding: 20px; background-color: #f9f9f9; }
        h1 { color: #2c3e50; text-align: center; }
        .container { background: white; padding: 40px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); }
        .progress-bar-bg { background: #e0e0e0; border-radius: 10px; height: 30px; overflow: hidden; margin: 20px 0; }
        .progress-bar { background: linear-gradient(90deg, #27ae60, #2ecc71); height: 100%; transition: width 0.5s; display: flex; align-items: center; justify-content: center; color: white; font-weight: bold; }
        .stats { text-align: center; font-size: 18px; margin: 20px 0; }
        .status { text-align: center; padding: 15px; border-radius: 8px; margin: 20px 0; }
        .status.running { background: #fff3cd; color: #856404; }
        .status.completed { background: #d4edda; color: #155724; }
        .status.error { background: #f8d7da; color: #721c24; }
        .action-btn { display: inline-block; padding: 12px 25px; margin: 10px; text-decoration: none; border-radius: 5px; font-weight: bold; }
        .download-btn { background: #007bff; color: white; }
        .error-btn { background: #ffc107; color: #333; }
        .back-btn { background: #6c757d; color: white; }
        .stop-btn { background: #dc3545; color: white; }
    </style>
</head>
<body>
    <h1>📊 Feldolgozás állapota</h1>
    
    <div class="container">
        <div class="stats">
            <strong>{{ progress.current }}</strong> / <strong>{{ progress.total }}</strong> PDF feldolgozva
        </div>
        
        <div class="progress-bar-bg">
            <div class="progress-bar" style="width: {{ progress.percent }}%;">
                {{ progress.percent }}%
            </div>
        </div>
        
        <div class="status {{ 'completed' if progress.status == 'completed' else 'running' if progress.status == 'running' else 'error' if 'error' in progress.status else '' }}">
            {% if progress.status == 'running' %}
                ⏳ Feldolgozás folyamatban...
            {% elif progress.status == 'completed' %}
                ✅ Feldolgozás kész!
            {% elif progress.status == 'stopped' %}
                ⏹️ Feldolgozás leállítva
            {% elif progress.status == 'idle' %}
                💤 Nincs aktív feldolgozás
            {% elif progress.status == 'no_files' %}
                📁 Nincsenek PDF fájlok
            {% else %}
                ⚠️ {{ progress.status }}
            {% endif %}
        </div>
        
        <div style="text-align: center; margin-top: 30px;">
            {% if progress.status == 'completed' or progress.status == 'stopped' %}
                <a href="/download" class="action-btn download-btn">📥 Excel letöltése</a>
                <a href="/download-errors" class="action-btn error-btn">⚠️ Hiba riport ({{ error_count }})</a>
            {% endif %}
            
            {% if progress.status == 'running' %}
                <a href="/stop" class="action-btn stop-btn">⏹️ Leállítás</a>
            {% endif %}
            
            <a href="/" class="action-btn back-btn">🏠 Főoldal</a>
        </div>
    </div>
</body>
</html>
"""

# ============================================================================
# ROUTES
# ============================================================================

# Store last used folder path
_last_folder = ""

def count_pdfs():
    if not UPLOAD_DIR.exists(): return 0
    return len(list(UPLOAD_DIR.rglob("*.pdf")))

@app.route("/", methods=["GET", "POST"])
def index():
    global _last_folder
    message = None
    error = None
    
    if request.method == "POST":
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        
        uploaded_files = request.files.getlist("files")
        valid_files = [f for f in uploaded_files if f.filename and f.filename.lower().endswith(".pdf")]
        
        if valid_files:
            # Save all files first
            for f in valid_files:
                dest = UPLOAD_DIR / f.filename
                f.save(dest)
            
            # Start background processing
            success, msg = start_background_processing(UPLOAD_DIR, OUTPUT_DIR, resume=False)
            message = f"{len(valid_files)} fájl feltöltve. {msg}"
    
    # Check if processor is running
    processor = get_processor(UPLOAD_DIR, OUTPUT_DIR)
    is_processing = processor.is_running
    
    excel_exists = (OUTPUT_DIR / "cadastral_data.xlsx").exists()
    
    return render_template_string(
        HTML_INDEX, 
        pdf_count=count_pdfs(),
        message=message,
        error=error,
        is_processing=is_processing,
        excel_exists=excel_exists,
        last_folder=_last_folder
    )

@app.route("/process-folder", methods=["POST"])
def process_folder():
    global _last_folder
    
    folder_path = request.form.get("folder_path", "").strip()
    _last_folder = folder_path
    
    if not folder_path:
        return render_template_string(
            HTML_INDEX,
            pdf_count=count_pdfs(),
            error="Kérlek add meg a mappa útvonalát!",
            is_processing=False,
            excel_exists=(OUTPUT_DIR / "cadastral_data.xlsx").exists(),
            last_folder=_last_folder
        )
    
    folder = Path(folder_path)
    
    if not folder.exists():
        return render_template_string(
            HTML_INDEX,
            pdf_count=count_pdfs(),
            error=f"A mappa nem létezik: {folder_path}",
            is_processing=False,
            excel_exists=(OUTPUT_DIR / "cadastral_data.xlsx").exists(),
            last_folder=_last_folder
        )
    
    if not folder.is_dir():
        return render_template_string(
            HTML_INDEX,
            pdf_count=count_pdfs(),
            error=f"Ez nem egy mappa: {folder_path}",
            is_processing=False,
            excel_exists=(OUTPUT_DIR / "cadastral_data.xlsx").exists(),
            last_folder=_last_folder
        )
    
    # Count PDFs in folder
    pdfs = list(folder.glob("*.pdf"))
    if not pdfs:
        return render_template_string(
            HTML_INDEX,
            pdf_count=count_pdfs(),
            error=f"Nincs PDF fájl a mappában: {folder_path}",
            is_processing=False,
            excel_exists=(OUTPUT_DIR / "cadastral_data.xlsx").exists(),
            last_folder=_last_folder
        )
    
    # Start processing directly from the folder
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    success, msg = start_background_processing(folder, OUTPUT_DIR, resume=False)
    
    return redirect(url_for("progress"))

@app.route("/upload-zip", methods=["POST"])
def upload_zip():
    """Handle ZIP file upload - extract PDFs and process."""
    global _last_folder
    
    zipfile_upload = request.files.get("zipfile")
    
    if not zipfile_upload or not zipfile_upload.filename:
        return render_template_string(
            HTML_INDEX,
            pdf_count=count_pdfs(),
            error="Kérlek válassz ki egy ZIP fájlt!",
            is_processing=False,
            excel_exists=(OUTPUT_DIR / "cadastral_data.xlsx").exists(),
            last_folder=_last_folder
        )
    
    if not zipfile_upload.filename.lower().endswith('.zip'):
        return render_template_string(
            HTML_INDEX,
            pdf_count=count_pdfs(),
            error="Csak ZIP fájl tölthető fel!",
            is_processing=False,
            excel_exists=(OUTPUT_DIR / "cadastral_data.xlsx").exists(),
            last_folder=_last_folder
        )
    
    try:
        # Clear previous uploads
        if UPLOAD_DIR.exists():
            shutil.rmtree(UPLOAD_DIR)
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        
        # Save ZIP temporarily
        zip_path = UPLOAD_DIR / "uploaded.zip"
        zipfile_upload.save(zip_path)
        
        # Extract PDFs from ZIP - use streaming to avoid memory issues
        pdf_count = 0
        with zipfile.ZipFile(zip_path, 'r') as zf:
            for name in zf.namelist():
                # Skip directories, non-PDF files, and macOS resource forks
                if name.endswith('/') or not name.lower().endswith('.pdf'):
                    continue
                if name.startswith('__MACOSX') or name.startswith('._'):
                    continue
                
                # Extract PDF with flat structure (no subdirs)
                basename = Path(name).name
                if basename and not basename.startswith('._'):
                    # Use streaming copy to avoid memory issues
                    dest_path = UPLOAD_DIR / basename
                    with zf.open(name) as src:
                        with open(dest_path, 'wb') as dest:
                            shutil.copyfileobj(src, dest)
                    pdf_count += 1
        
        # Remove the ZIP file
        zip_path.unlink()
        
        if pdf_count == 0:
            return render_template_string(
                HTML_INDEX,
                pdf_count=count_pdfs(),
                error="A ZIP fájl nem tartalmaz PDF fájlokat!",
                is_processing=False,
                excel_exists=(OUTPUT_DIR / "cadastral_data.xlsx").exists(),
                last_folder=_last_folder
            )
        
        # Start processing
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        success, msg = start_background_processing(UPLOAD_DIR, OUTPUT_DIR, resume=False)
        
        return redirect(url_for("progress"))
        
    except zipfile.BadZipFile:
        return render_template_string(
            HTML_INDEX,
            pdf_count=count_pdfs(),
            error="Hibás ZIP fájl! Kérlek próbáld újra.",
            is_processing=False,
            excel_exists=(OUTPUT_DIR / "cadastral_data.xlsx").exists(),
            last_folder=_last_folder
        )
    except Exception as e:
        return render_template_string(
            HTML_INDEX,
            pdf_count=count_pdfs(),
            error=f"Hiba történt: {str(e)[:100]}",
            is_processing=False,
            excel_exists=(OUTPUT_DIR / "cadastral_data.xlsx").exists(),
            last_folder=_last_folder
        )

@app.route("/progress")
def progress():
    processor = get_processor(UPLOAD_DIR, OUTPUT_DIR)
    prog = processor.get_progress()
    errors = processor.load_errors()
    
    return render_template_string(
        HTML_PROGRESS,
        progress=prog,
        error_count=len(errors)
    )

@app.route("/progress-json")
def progress_json():
    """API endpoint for progress."""
    processor = get_processor(UPLOAD_DIR, OUTPUT_DIR)
    return jsonify(processor.get_progress())

@app.route("/start")
def start():
    """Start or resume processing."""
    success, msg = start_background_processing(UPLOAD_DIR, OUTPUT_DIR, resume=True)
    return redirect(url_for("progress"))

@app.route("/stop")
def stop():
    """Stop processing."""
    stop_background_processing()
    return redirect(url_for("progress"))

@app.route("/download")
def download():
    excel_path = OUTPUT_DIR / "cadastral_data.xlsx"
    if excel_path.exists():
        return send_file(excel_path, as_attachment=True, download_name="Registru_Cadastral_Final.xlsx")
    return redirect(url_for("index"))

@app.route("/download-errors")
def download_errors():
    """Download error report as CSV."""
    processor = get_processor(UPLOAD_DIR, OUTPUT_DIR)
    csv_content = processor.get_error_report_csv()
    
    return Response(
        csv_content,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=hibak.csv"}
    )

@app.route("/errors")
def errors():
    """View errors as JSON."""
    processor = get_processor(UPLOAD_DIR, OUTPUT_DIR)
    return jsonify(processor.load_errors())

@app.route("/clear")
def clear():
    # Stop any running process
    stop_background_processing()
    
    # Reset processor state
    processor = get_processor(UPLOAD_DIR, OUTPUT_DIR)
    processor.reset()
    
    # Clear directories
    if UPLOAD_DIR.exists(): 
        shutil.rmtree(UPLOAD_DIR)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
