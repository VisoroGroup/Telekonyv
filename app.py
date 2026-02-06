"""
Flask web interface for Romanian Cadastral PDF Data Extractor.
Optimized for large batches (1000+ files) with loading indicators.
"""
from flask import Flask, render_template_string, request, send_file, redirect, url_for
from pathlib import Path
import shutil
import time

from main import process_pdfs_from_dir

app = Flask(__name__)

app.config['MAX_CONTENT_LENGTH'] = 2048 * 1024 * 1024 
app.config['MAX_FORM_MEMORY_SIZE'] = 2048 * 1024 * 1024

UPLOAD_DIR = Path("input_pdfs")
OUTPUT_DIR = Path("output_excel")

HTML = """
<!doctype html>
<html>
<head>
    <title>Cadastral Extractor Pro</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 800px; margin: 40px auto; padding: 20px; background-color: #f9f9f9; }
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
        
        .action-btn { display: inline-block; padding: 10px 20px; margin: 5px; text-decoration: none; border-radius: 5px; font-weight: bold; }
        .download-btn { background: #007bff; color: white; }
        .clear-btn { background: #dc3545; color: white; }

        #loading { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(255,255,255,0.95); z-index: 1000; text-align: center; padding-top: 15%; }
        .spinner { border: 8px solid #f3f3f3; border-top: 8px solid #3498db; border-radius: 50%; width: 60px; height: 60px; animation: spin 1s linear infinite; margin: 0 auto 20px auto; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        #loading-text { font-size: 24px; color: #333; font-weight: bold; }
        #loading-subtext { font-size: 16px; color: #666; margin-top: 10px; }
    </style>
    
    <script>
        function updateFileName(input) {
            var fileName = input.files.length > 0 ? input.files.length + " files selected" : "No files selected";
            document.getElementById('file-name').textContent = fileName;
        }

        function showLoading() {
            var input = document.getElementById('file-input');
            if (input.files.length > 0) {
                document.getElementById('loading').style.display = 'block';
                document.getElementById('loading-subtext').textContent = "Processing " + input.files.length + " files. Please do not close this tab.";
            }
        }
    </script>
</head>
<body>

    <div id="loading">
        <div class="spinner"></div>
        <div id="loading-text">Processing your PDFs...</div>
        <div id="loading-subtext">This may take a few minutes for large batches.</div>
    </div>

    <h1>Cadastral Data Extractor</h1>
    
    <div class="container">
        
        <form method="post" enctype="multipart/form-data" onsubmit="showLoading()">
            <div class="upload-area">
                <label for="file-input" class="file-label">Choose PDF Files</label>
                <input id="file-input" type="file" name="files" multiple accept=".pdf" onchange="updateFileName(this)">
                <p id="file-name" style="margin-top: 15px; font-size: 16px;">No files selected</p>
                <p style="font-size: 14px; color: #999;">Select up to 1000 files at once</p>
            </div>
            <input type="submit" class="submit-btn" value="START PROCESSING">
        </form>
        
        <p class="stats">Files currently on server: {{ pdf_count }}</p>

        {% if message %}
        <div class="success-box">
            <h2>{{ message }}</h2>
            <p>Processed: <strong>{{ pdfs_processed }}</strong> files</p>
            <p>Rows Extracted: <strong>{{ records_count }}</strong></p>
            <br>
            <a href="/download" class="action-btn download-btn">Download Excel Report</a>
            <a href="/clear" class="action-btn clear-btn">Clear & Start Over</a>
        </div>
        {% elif excel_exists %}
        <div class="success-box" style="background: #e2e6ea; color: #333; border-color: #dae0e5;">
            <h3>Previous Report Available</h3>
            <a href="/download" class="action-btn download-btn">Download Excel</a>
            <a href="/clear" class="action-btn clear-btn">Clear Files</a>
        </div>
        {% endif %}

        <hr style="margin: 30px 0; border: none; border-top: 1px solid #ddd;">
        <div style="text-align: center;">
            <p style="color: #666; margin-bottom: 10px;">Developer Tools</p>
            <a href="/download-code-txt" class="action-btn" style="background: #6c757d; color: white;">Download Source Code (TXT)</a>
        </div>

    </div>

</body>
</html>
"""

def count_pdfs():
    if not UPLOAD_DIR.exists(): return 0
    return len(list(UPLOAD_DIR.rglob("*.pdf")))

@app.route("/", methods=["GET", "POST"])
def index():
    message = None
    pdfs_processed = 0
    records_count = 0
    
    if request.method == "POST":
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        
        uploaded_files = request.files.getlist("files")
        valid_files = [f for f in uploaded_files if f.filename and f.filename.lower().endswith(".pdf")]
        
        if valid_files:
            for f in valid_files:
                dest = UPLOAD_DIR / f.filename
                f.save(dest)
            
            pdfs_processed, records_count = process_pdfs_from_dir(UPLOAD_DIR, OUTPUT_DIR)
            message = "Extraction Complete!"
    
    excel_exists = (OUTPUT_DIR / "cadastral_data.xlsx").exists()
    
    return render_template_string(
        HTML, 
        pdf_count=count_pdfs(),
        message=message, 
        pdfs_processed=pdfs_processed,
        records_count=records_count,
        excel_exists=excel_exists
    )

@app.route("/download")
def download():
    excel_path = OUTPUT_DIR / "cadastral_data.xlsx"
    if excel_path.exists():
        return send_file(excel_path, as_attachment=True, download_name="Registru_Cadastral_Final.xlsx")
    return redirect(url_for("index"))

@app.route("/clear")
def clear():
    if UPLOAD_DIR.exists(): shutil.rmtree(UPLOAD_DIR)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    
    excel_path = OUTPUT_DIR / "cadastral_data.xlsx"
    if excel_path.exists(): excel_path.unlink()
    
    return redirect(url_for("index"))

def generate_code_file():
    """Regenerates all_code.txt with latest code from all files."""
    code_files = [
        ("config.py", "config.py"),
        ("main.py", "main.py"),
        ("parser.py", "parser.py"),
        ("validator.py", "validator.py"),
        ("text_extractor.py", "text_extractor.py"),
        ("app.py", "app.py"),
        ("requirements.txt", "requirements.txt"),
    ]
    
    output = []
    for label, filepath in code_files:
        output.append("=" * 80)
        output.append(f"FILE: {label}")
        output.append("=" * 80)
        try:
            with open(filepath, 'r') as f:
                output.append(f.read())
        except:
            output.append(f"# Could not read {filepath}")
        output.append("")
    
    with open("all_code.txt", "w") as f:
        f.write("\n".join(output))

@app.route("/download-code-txt")
def download_code_txt():
    generate_code_file()
    txt_path = Path("all_code.txt")
    if txt_path.exists():
        return send_file(txt_path, as_attachment=True, download_name="all_code.txt")
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
