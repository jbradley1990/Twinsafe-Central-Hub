import logging
import time
from threading import Lock
from typing import Any, Dict, Tuple, Optional

# Try to import opcua, but don't fail if not present
try:
    from opcua import Client, ua
    OPC_AVAILABLE = True
except ImportError:
    OPC_AVAILABLE = False
    Client = None
    ua = None

from .config import PLC_ENDPOINT, NODE_IDS, RIG_IPS

logger = logging.getLogger(__name__)

class OpcUaWrapper:
    def __init__(self, endpoint: str, name: str = "Default"):
        self.endpoint = endpoint
        self.name = name
        self._lock = Lock()
        self.client: Optional[Any] = None
        self.node_cache: Dict[str, Any] = {}
        self.connected = False
        self.last_attempt = 0
        self.attempt_cooldown = 10  # Seconds between reconnection attempts

        if OPC_AVAILABLE:
            try:
                self._connect()
            except Exception as e:
                logger.error(f"[{self.name}] Failed initial connect to {self.endpoint}: {e}")

    def _connect(self) -> None:
        if not OPC_AVAILABLE: return
        logger.info(f"[{self.name}] Connecting to OPC UA at {self.endpoint}")
        try:
            # We use a 5 second timeout for connection as requested
            self.client = Client(self.endpoint, timeout=5)
            self.client.connect()
            self.connected = True
            logger.info(f"[{self.name}] Connected to {self.endpoint}")

            # Cache nodes
            for key, nodeid in NODE_IDS.items():
                try:
                    self.node_cache[key] = self.client.get_node(nodeid)
                except Exception as e:
                    logger.warning(f"[{self.name}] Failed to get node {nodeid} for {key}: {e}")
        except Exception as e:
            self.connected = False
            raise e

    def is_connected(self) -> bool:
        if not OPC_AVAILABLE: return False
        if not self.client or not self.connected: return False
        try:
            # Check connection by reading ServerStatus or just a known node
            # Node i=2259 is ServerState
            state = self.client.get_node("ns=0;i=2259").get_value()
            return state == 0 # 0 is Running
        except:
            self.connected = False
            return False

    def ensure_connected(self) -> bool:
        if not OPC_AVAILABLE: return False
        if self.is_connected(): return True

        # Check cooldown
        now = time.time()
        if now - self.last_attempt < self.attempt_cooldown:
            return False

        self.last_attempt = now
        try:
            self._connect()
            return True
        except:
            self.connected = False
            return False

    def read(self, key: str) -> Any:
        # Mock data if OPC is not available
        if not OPC_AVAILABLE:
            return self._get_mock_data(key)

        if not self.ensure_connected():
            return self._get_mock_data(key)

        if key not in self.node_cache:
            return self._get_mock_data(key)

        with self._lock:
            try:
                return self.node_cache[key].get_value()
            except Exception as e:
                logger.error(f"[{self.name}] OPC read error for {key}: {e}")
                self.connected = False
                return self._get_mock_data(key)

    def _get_mock_data(self, key: str) -> Any:
        # Provide some sensible defaults for UI when disconnected/unavailable
        if key == "channel_readings":
            import random
            return [random.uniform(0, 100) for _ in range(9)]
        if key == "channel_visibility":
            return [True] * 9
        if key == "user": return "—"
        if key == "ots_no": return "—"
        if key == "test_name": return "—"
        if key == "current_user_fullname": return "" # Empty means "Green" status
        return None

    def write(self, key: str, value: Any) -> bool:
        if not self.client or key not in self.node_cache:
            return False
        if not self.ensure_connected():
            return False
        with self._lock:
            try:
                self.node_cache[key].set_value(value)
                return True
            except Exception as e:
                logger.error(f"[{self.name}] OPC write error for {key}: {e}")
                self.connected = False
                return False

# Shared instance for the main PLC (used by Historical Trend)
opc = OpcUaWrapper(PLC_ENDPOINT, name="MainPLC")

# Rig-specific instances
rig_opc: Dict[str, OpcUaWrapper] = {}
for rig_id, ip in RIG_IPS.items():
    endpoint = f"opc.tcp://{ip}:4840"
    rig_opc[rig_id] = OpcUaWrapper(endpoint, name=rig_id)
