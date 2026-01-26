from flask import Flask, request, send_file, send_from_directory, current_app, jsonify, redirect
try:
    from flask_cors import CORS
except Exception:  # pragma: no cover - dependency might be missing
    CORS = lambda *args, **kwargs: None
from pathlib import Path
import tempfile, subprocess, traceback, sys, io, os, time

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # optional

BASE_DIR = Path(__file__).resolve().parent
GUIDE_DIR = BASE_DIR / "guide"
PDF_DIR = BASE_DIR / "static" / "pdfs"

#WEBVISU_URL = "http://127.0.0.1:8080/webvisu.htm"  # ← adjust to your HMI
WEBVISU_URL = "http://10.1.6.7:9000"  # ← adjust to your HMI

@app.before_request
def bounce_portal_host():
    # If someone tries the portal hostname on this kiosk, bounce to local WebVisu
    host = request.host.split(":")[0].lower()
    if host == "rnd-portal.valves.co.uk":
        return redirect(WEBVISU_URL, code=302)

# ---- serve the front-end ----
@app.get("/")
def root():
    # HTML should not be aggressively cached in dev; let it revalidate
    resp = send_from_directory(str(GUIDE_DIR), "guide.html", conditional=True)
    # Short cache or revalidate:
    resp.headers["Cache-Control"] = "no-cache"
    return resp

@app.get("/guide/<path:path>")
def guide_files(path):
    return send_from_directory(str(GUIDE_DIR), path)

@app.get("/api/pdf-list")
def pdf_list():
    try:
        if not PDF_DIR.is_dir():
            # No folder / no PDFs yet
            return jsonify([])

        files = [
            f.name
            for f in PDF_DIR.iterdir()
            if f.is_file() and f.suffix.lower() == ".pdf"
        ]
        files.sort()  # optional: stable order
        return jsonify(files)
    except Exception as e:
        current_app.logger.exception("Error listing PDFs")
        return jsonify([]), 500

# ---- tiny health check ----
@app.get("/api/ping")
def ping():
    return {"ok": True}

@app.after_request
def add_cors_headers(resp):
    resp.headers.setdefault("Access-Control-Allow-Origin", "*")
    return resp

# # ---- caching headers for guide assets ----
# @app.after_request
# def add_cache_headers(resp):
#     p = request.path.lower()

#     # Long-lived, immutable caching for static guide assets
#     if p.startswith("/guide/"):
#         # File-type specific rules
#         if p.endswith((".mp4", ".webm")):
#             resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
#             resp.headers["Accept-Ranges"] = "bytes"  # Range requests are expected for video
#         elif p.endswith((".js", ".css", ".png", ".jpg", ".jpeg", ".webp", ".svg", ".woff2", ".woff", ".ttf")):
#             resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
#         elif p.endswith((".html",)):
#             # Avoid sticking old HTML
#             resp.headers["Cache-Control"] = "no-cache"
#     # Basic CORS header for API responses in case flask_cors is unavailable
#     if p.startswith("/api/"):
#         resp.headers.setdefault("Access-Control-Allow-Origin", "*")

#     return resp

# ---------- NEW: helper to read when Windows releases the lock ----------
def read_when_unlocked(path: Path, timeout: float = 6.0, poll: float = 0.1) -> bytes:
    """
    Wait until `path` is readable and its size is stable across two polls, then return bytes.
    Raises RuntimeError if it never becomes readable within `timeout`.
    """
    deadline = time.time() + timeout
    last_size = -1
    while time.time() < deadline:
        try:
            size = os.path.getsize(path)
            if size != last_size:
                last_size = size
                time.sleep(poll)
                continue
            with open(path, 'rb') as f:
                return f.read()
        except (PermissionError, OSError):
            time.sleep(poll)
    raise RuntimeError(f"File still locked after {timeout:.1f}s: {path}")

@app.post("/api/generate-pdf")
def run_pdf_generation():
    try:
        data = request.files.get("data_csv")
        details = request.files.get("details_json")
        if not data or not details:
            return jsonify(error="Both data_csv and details_json are required"), 400

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            data_path = tmp / "data.csv"
            details_path = tmp / "details.json"

            # Use a dedicated, unique output folder per request
            out_dir = tmp / f"out_{int(time.time()*1000)}"
            out_dir.mkdir(parents=True, exist_ok=True)

            data.save(data_path)
            details.save(details_path)

            before = {p.name for p in out_dir.glob("*.pdf")}

            # Use the current interpreter (portable on Windows/macOS/Linux)
            cmd = [sys.executable, "R-D-AutoChart-Generation/DLS Chart Generation/main.py", str(data_path), str(details_path), str(out_dir)]
            current_app.logger.info("Running: %s", " ".join(cmd))

            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)

            # Helpful logging on failure
            if proc.returncode != 0:
                current_app.logger.error(
                    "Generator failed\nSTDOUT:\n%s\nSTDERR:\n%s",
                    proc.stdout, proc.stderr
                )
                return (f"Generator failed ({proc.returncode}).\n{proc.stderr}", 500)

            # Small nudge to avoid race with AV/indexer or buffered I/O finalisation
            time.sleep(0.05)

            created = [p for p in out_dir.glob("*.pdf") if p.name not in before]
            if not created:
                created = list(out_dir.glob("*.pdf"))  # fallback: newest

            if not created:
                return ("No PDF produced by generator.", 500)

            pdf_path = max(created, key=lambda p: p.stat().st_mtime)

            # --------- CHANGED: read to memory after the OS releases the lock ----------
            try:
                pdf_bytes = read_when_unlocked(pdf_path, timeout=6.0, poll=0.1)
            except RuntimeError as e:
                current_app.logger.error(str(e))
                # 503 is appropriate for transient problems, invites client retry
                return ("PDF was produced but is temporarily locked; please retry.", 503)

            return send_file(
                io.BytesIO(pdf_bytes),            # in-memory stream avoids file locking
                as_attachment=True,
                download_name=pdf_path.name,      # keep your generator's dynamic name
                mimetype="application/pdf",
                max_age=0
            )

    except Exception as e:
        current_app.logger.exception("Unhandled exception in /api/generate-pdf")
        return (f"Internal error: {e}\n{traceback.format_exc()}", 500)

@app.route('/<path:filename>')
def serve_static_files(filename):
    return send_from_directory(str(BASE_DIR), filename)

if __name__ == '__main__':
    app.run(
        host='0.0.0.0',
        port=9000,
        debug=True,
        use_reloader=True,
    )