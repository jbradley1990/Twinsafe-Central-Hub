from fastapi import APIRouter
from ..opc import rig_data_cache

router = APIRouter()

@router.get("/api/rigs-status")
async def rigs_status():
    # Return cached data immediately
    return rig_data_cache
