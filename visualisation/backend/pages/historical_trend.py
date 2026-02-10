from fastapi import APIRouter
from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel

from ..opc import opc
from ..config import CHANNEL_NAMES

router = APIRouter()

class ChannelReading(BaseModel):
    name: str
    value: Optional[float]
    visible: bool

class LiveResponse(BaseModel):
    timestamp: datetime
    channels: List[ChannelReading]

@router.get("/api/live", response_model=LiveResponse)
async def get_live_json():
    now = datetime.now(tz=timezone.utc)

    channel_values = opc.read("channel_readings")
    channel_visibility = opc.read("channel_visibility")

    channels = []
    for i in range(9):
        val = channel_values[i] if channel_values and i < len(channel_values) else 0.0
        vis = channel_visibility[i] if channel_visibility and i < len(channel_visibility) else True
        name = CHANNEL_NAMES.get(i+1, f"Channel {i+1}")
        channels.append(ChannelReading(name=name, value=val, visible=vis))

    return LiveResponse(timestamp=now, channels=channels)
