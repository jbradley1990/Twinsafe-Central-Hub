from fastapi import APIRouter, UploadFile, File, HTTPException, Response
from fastapi.responses import FileResponse
from pathlib import Path
import tempfile, subprocess, sys, time, os, io
from typing import List

from ..config import PDF_DIR

router = APIRouter()

def read_when_unlocked(path: Path, timeout: float = 6.0, poll: float = 0.1) -> bytes:
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

@router.get("/api/pdf-list")
async def pdf_list():
    try:
        if not PDF_DIR.is_dir():
            return []
        files = [f.name for f in PDF_DIR.iterdir() if f.is_file() and f.suffix.lower() == ".pdf"]
        files.sort()
        return files
    except Exception:
        return []

@router.post("/api/generate-pdf")
async def run_pdf_generation(data_csv: UploadFile = File(...), details_json: UploadFile = File(...)):
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            data_path = tmp / "data.csv"
            details_path = tmp / "details.json"
            out_dir = tmp / f"out_{int(time.time()*1000)}"
            out_dir.mkdir(parents=True, exist_ok=True)

            with open(data_path, "wb") as f:
                f.write(await data_csv.read())
            with open(details_path, "wb") as f:
                f.write(await details_json.read())

            cmd = [sys.executable, "chart_generation/main.py", str(data_path), str(details_path), str(out_dir)]
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)

            if proc.returncode != 0:
                raise HTTPException(status_code=500, detail=f"Generator failed: {proc.stderr}")

            time.sleep(0.05)
            created = list(out_dir.glob("*.pdf"))
            if not created:
                raise HTTPException(status_code=500, detail="No PDF produced by generator.")

            pdf_path = max(created, key=lambda p: p.stat().st_mtime)
            pdf_bytes = read_when_unlocked(pdf_path)

            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={"Content-Disposition": f"attachment; filename={pdf_path.name}"}
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
