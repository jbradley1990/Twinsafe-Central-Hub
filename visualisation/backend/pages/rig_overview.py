from fastapi import APIRouter
from ..opc import rig_opc

router = APIRouter()

@router.get("/api/rigs-status")
async def rigs_status():
    results = {}
    for rig_id, wrapper in rig_opc.items():
        # Check connection first
        connected = wrapper.is_connected()

        # Read values
        user = wrapper.read("user")
        ots_no = wrapper.read("ots_no")
        test_name = wrapper.read("test_name")
        full_name = wrapper.read("current_user_fullname")

        # Determine color state based on requirements:
        # orange if there is no connection
        # green if ns=4;s=|var|...vumCurrentUser.wstFullName is empty
        # red if ns=4;s=|var|...vumCurrentUser.wstFullName is not empty

        if not connected:
            color_state = "orange"
        elif not full_name or str(full_name).strip() == "":
            color_state = "green"
        else:
            color_state = "red"

        results[rig_id] = {
            "user": user,
            "ots_no": ots_no,
            "test_name": test_name,
            "color_state": color_state,
            "connected": connected
        }

    return results
