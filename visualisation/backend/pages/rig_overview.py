from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
import json
from urllib.request import Request as URLRequest, urlopen
from urllib.error import URLError, HTTPError

router = APIRouter()

# @router.get("/api/rig-json")
# async def rig_json_proxy(host: str, path: str = "/rig.json"):
#     if not host:
#         raise HTTPException(status_code=400, detail="host is required")

#     if not path.startswith("/"):
#         path = "/" + path

#     if host.startswith("http://") or host.startswith("https://"):
#         base = host
#     else:
#         base = f"http://{host}"

#     url = f"{base}{path}"

#     try:
#         req = URLRequest(url, headers={"Accept": "application/json"})
#         with urlopen(req, timeout=3.5) as resp:
#             raw = resp.read()
#             try:
#                 parsed = json.loads(raw)
#                 return parsed
#             except Exception:
#                 # Return raw if not JSON
#                 return JSONResponse(content={"error": "Invalid JSON from upstream"}, status_code=502)
#     except HTTPError as e:
#         raise HTTPException(status_code=502, detail=f"Upstream error {e.code}")
#     except URLError as e:
#         raise HTTPException(status_code=502, detail=f"Upstream unreachable: {e.reason}")
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))
