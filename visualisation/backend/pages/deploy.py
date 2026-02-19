import os
import asyncio
import shutil
import tempfile
import zipfile
import json
import uuid
from typing import List, Optional, Dict
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, UploadFile, File, Form, HTTPException, Query
import logging

from ..config import RIG_IPS

router = APIRouter()
logger = logging.getLogger(__name__)

# Deployment password from environment variable
DEPLOY_PASSWORD = os.getenv("DEPLOY_PASSWORD", "password123")

# In-memory storage for active deployment sessions (temp_dir mapping)
active_sessions: Dict[str, str] = {}

# Store connected websocket clients for logs
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.error(f"Failed to send websocket message: {e}")

manager = ConnectionManager()

@router.websocket("/api/deploy/ws")
async def websocket_endpoint(websocket: WebSocket, password: str = Query(...)):
    if password != DEPLOY_PASSWORD:
        await websocket.close(code=4001) # Unauthorized
        return

    await manager.connect(websocket)
    try:
        while True:
            # Keep the connection open and handle incoming messages if any
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)

async def log_to_ws(message: str):
    logger.info(message)
    await manager.broadcast(message)

@router.post("/api/deploy/upload")
async def upload_files(
    password: str = Form(...),
    app_file: UploadFile = File(...),
    crc_file: UploadFile = File(...),
    prj_file: UploadFile = File(...),
    visu_zip: Optional[UploadFile] = File(None)
):
    if password != DEPLOY_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Create a temporary directory to store uploaded files
    temp_dir = tempfile.mkdtemp(prefix="deploy_")
    session_id = str(uuid.uuid4())
    active_sessions[session_id] = temp_dir

    try:
        # Save files
        for file in [app_file, crc_file, prj_file]:
            # Sanitize filename to prevent path traversal
            filename = os.path.basename(file.filename)
            file_path = os.path.join(temp_dir, filename)
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

        if visu_zip:
            filename = os.path.basename(visu_zip.filename)
            zip_path = os.path.join(temp_dir, filename)
            with open(zip_path, "wb") as buffer:
                shutil.copyfileobj(visu_zip.file, buffer)

            # Extract zip
            visu_dir = os.path.join(temp_dir, "visu")
            os.makedirs(visu_dir, exist_ok=True)
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(visu_dir)

        return {"session_id": session_id}
    except Exception as e:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        if session_id in active_sessions:
            del active_sessions[session_id]
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/deploy/run")
async def run_deploy(
    session_id: str = Form(...),
    selected_rigs: str = Form(...), # JSON string list
    username: str = Form(...),
    password: str = Form(...)
):
    if username != "mechatronics" or password != DEPLOY_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    temp_dir = active_sessions.get(session_id)
    if not temp_dir or not os.path.exists(temp_dir):
        raise HTTPException(status_code=400, detail="Invalid or expired session")

    try:
        rig_ids = json.loads(selected_rigs)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid rig selection format")

    # Start deployment in background
    # Remove from active_sessions so it can't be reused
    del active_sessions[session_id]
    asyncio.create_task(execute_deployment(temp_dir, rig_ids))

    return {"status": "started"}

async def execute_deployment(temp_dir: str, rig_ids: List[str]):
    try:
        await log_to_ws(">>> Starting deployment process...")

        key_path = os.path.expanduser("~/.ssh/tl_prototype_key")
        if not os.path.exists(key_path):
            await log_to_ws(f"ERROR: SSH key not found at {key_path}")
            return

        # Find files in temp_dir
        app_files = [f for f in os.listdir(temp_dir) if f.endswith(".app")]
        crc_files = [f for f in os.listdir(temp_dir) if f.endswith(".crc")]
        prj_files = [f for f in os.listdir(temp_dir) if f.lower() == "archive.prj"]
        if not prj_files:
            prj_files = [f for f in os.listdir(temp_dir) if f.endswith(".prj")]

        visu_dir = os.path.join(temp_dir, "visu")

        if not app_files or not crc_files or not prj_files:
            await log_to_ws("ERROR: Missing required files (.app, .crc, or Archive.prj)")
            return

        app_file = os.path.join(temp_dir, app_files[0])
        crc_file = os.path.join(temp_dir, crc_files[0])
        prj_file = os.path.join(temp_dir, prj_files[0])

        for rig_id in rig_ids:
            ip = RIG_IPS.get(rig_id)
            if not ip:
                await log_to_ws(f"ERROR: Unknown rig ID {rig_id}")
                continue

            await log_to_ws(f"==> Deploying to {rig_id} ({ip})")

            # 1. Copy Archive.prj
            await log_to_ws(f"   -> Copying Archive.prj")
            success = await run_command([
                "scp", "-i", key_path, "-o", "StrictHostKeyChecking=no", "-C", "-q",
                prj_file, f"root@{ip}:/var/opt/codesys/PlcLogic/Archive.prj"
            ])
            if not success:
                await log_to_ws(f"FAILED to copy Archive.prj to {rig_id}")
                continue

            # 2. Copy .app and .crc
            updates_path = "/var/opt/codesys/PlcLogic/DLS/Updates/"
            await log_to_ws(f"   -> Copying {app_files[0]} and {crc_files[0]}")
            await run_command([
                "ssh", "-i", key_path, "-o", "StrictHostKeyChecking=no",
                f"root@{ip}", f"mkdir -p {updates_path}"
            ])

            success = await run_command([
                "scp", "-i", key_path, "-o", "StrictHostKeyChecking=no", "-C", "-q",
                app_file, crc_file, f"root@{ip}:{updates_path}"
            ])
            if not success:
                await log_to_ws(f"FAILED to copy app/crc files to {rig_id}")
                continue

            # 3. Copy visu if exists
            if os.path.exists(visu_dir):
                visu_remote_path = "/var/opt/codesys/PlcLogic/DLS/Updates/visu"
                await log_to_ws("   -> Ensuring remote visu directory exists")
                await run_command([
                    "ssh", "-i", key_path, "-o", "StrictHostKeyChecking=no",
                    f"root@{ip}", f"mkdir -p {visu_remote_path}"
                ])

                await log_to_ws("   -> Copying visu contents")
                success = await run_command([
                    "scp", "-i", key_path, "-o", "StrictHostKeyChecking=no", "-r", "-C", "-q",
                    f"{visu_dir}/.", f"root@{ip}:{visu_remote_path}/"
                ])
                if not success:
                    await log_to_ws(f"FAILED to copy visu contents to {rig_id}")

            await log_to_ws(f"Deployment complete for {rig_id}")

        await log_to_ws(">>> All deployments finished.")
    except Exception as e:
        await log_to_ws(f"CRITICAL ERROR during deployment: {str(e)}")
    finally:
        # Cleanup temp dir
        try:
            if os.path.exists(temp_dir) and "deploy_" in temp_dir:
                shutil.rmtree(temp_dir)
            await log_to_ws("   -> Cleaned up temporary files.")
        except Exception as e:
            logger.error(f"Failed to cleanup temp dir: {e}")

async def run_command(cmd: List[str]) -> bool:
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            if stderr:
                await log_to_ws(f"      ERROR: {stderr.decode().strip()}")
            return False
        return True
    except Exception as e:
        await log_to_ws(f"      EXECUTION ERROR: {str(e)}")
        return False
