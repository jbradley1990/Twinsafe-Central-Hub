from pathlib import Path
from typing import Dict

BASE_DIR = Path(__file__).resolve().parent.parent.parent
FRONTEND_DIR = BASE_DIR / "visualisation" / "frontend"
PDF_DIR = BASE_DIR / "static" / "pdfs"

# OPC configuration (placeholder for now)
PLC_ENDPOINT = "opc.tcp://10.1.6.7:4840"

NODE_IDS: Dict[str, str] = {
    "channel_readings": "ns=4;s=|var|CODESYS Control for Linux ARM64 SL.DLS.GVL.alrChannelReading",
    "channel_visibility": "ns=4;s=|var|CODESYS Control for Linux ARM64 SL.DLS.GVL.axVisibilty",
}

CHANNEL_NAMES = {
    1: "Channel 1",
    2: "Channel 2",
    3: "Channel 3",
    4: "Channel 4",
    5: "Channel 5",
    6: "Channel 6",
    7: "Channel 7",
    8: "Channel 8",
    9: "Ambient Temperature",
}
