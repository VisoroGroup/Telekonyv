"""
Flask web interface for Romanian Cadastral PDF Data Extractor.
Supports large batches (5000+ files) with background processing and progress tracking.
"""
from flask import Flask, render_template_string, request, send_file, redirect, url_for, jsonify, Response
from pathlib import Path
import shutil

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
        .upload-area { border: 2px dashed #bdc3c7; padding: 40px; text-align: center; border-radius: 8px; margin-bottom: 20px; transition: 0.3s; }
        .upload-area:hover { border-color: #3498db; background: #f0f8ff; }
        input[type=file] { display: none; }
        .file-label { background: #3498db; color: white; padding: 12px 25px; border-radius: 5px; cursor: pointer; display: inline-block; font-weight: bold; }
        .file-label:hover { background: #2980b9; }
        .submit-btn { background: #27ae60; color: white; padding: 15px 40px; border: none; border-radius: 5px; cursor: pointer; font-size: 18px; margin-top: 20px; width: 100%; transition: 0.3s; }
        .submit-btn:hover { background: #219150; }
        .stats { color: #7f8c8d; text-align: center; margin-top: 10px; }
        .success-box { background: #d4edda; color: #155724; padding: 20px; border-radius: 8px; margin-top: 20px; text-align: center; border: 1px solid #c3e6cb; }
        .warning-box { background: #fff3cd; color: #856404; padding: 20px; border-radius: 8px; margin-top: 20px; text-align: center; border: 1px solid #ffeeba; }
        .action-btn { display: inline-block; padding: 10px 20px; margin: 5px; text-decoration: none; border-radius: 5px; font-weight: bold; }
        .download-btn { background: #007bff; color: white; }
        .clear-btn { background: #dc3545; color: white; }
        .progress-btn { background: #17a2b8; color: white; }
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
            var input = document.getElementById('file-input');
            if (input.files.length > 0) {
                document.getElementById('loading').style.display = 'block';
                document.getElementById('loading-subtext').textContent = input.files.length + " fájl feltöltése...";
            }
        }
    </script>
</head>
<body>
    <div id="loading">
        <div class="spinner"></div>
        <div id="loading-text">Fájlok feltöltése...</div>
        <div id="loading-subtext">Ez eltarthat néhány percig nagy mennyiségnél.</div>
    </div>

    <h1>🏠 Telekkönyv Feldolgozó</h1>
    
    <div class="container">
        <form method="post" enctype="multipart/form-data" onsubmit="showLoading()">
            <div class="upload-area">
                <label for="file-input" class="file-label">📁 PDF fájlok kiválasztása</label>
                <input id="file-input" type="file" name="files" multiple accept=".pdf" onchange="updateFileName(this)">
                <p id="file-name" style="margin-top: 15px; font-size: 16px;">Nincs kiválasztva</p>
                <p style="font-size: 14px; color: #999;">Akár 5000+ fájl egyszerre!</p>
            </div>
            <input type="submit" class="submit-btn" value="📤 FELTÖLTÉS ÉS FELDOLGOZÁS">
        </form>
        
        <p class="stats">Feltöltött PDF-ek: <strong>{{ pdf_count }}</strong></p>

        {% if message %}
        <div class="success-box">
            <h2>{{ message }}</h2>
            <a href="/progress" class="action-btn progress-btn">📊 Feldolgozás állapota</a>
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

def count_pdfs():
    if not UPLOAD_DIR.exists(): return 0
    return len(list(UPLOAD_DIR.rglob("*.pdf")))

@app.route("/", methods=["GET", "POST"])
def index():
    message = None
    
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
        is_processing=is_processing,
        excel_exists=excel_exists
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
