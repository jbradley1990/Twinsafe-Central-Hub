import logging
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

from .config import PLC_ENDPOINT, NODE_IDS

logger = logging.getLogger(__name__)

class OpcUaWrapper:
    def __init__(self, endpoint: str):
        self.endpoint = endpoint
        self._lock = Lock()
        self.client: Optional[Any] = None
        self.node_cache: Dict[str, Any] = {}

        if OPC_AVAILABLE:
            try:
                self._connect()
            except Exception as e:
                logger.error(f"Failed to connect to OPC server: {e}")

    def _connect(self) -> None:
        if not OPC_AVAILABLE: return
        logger.info(f"Connecting to OPC UA at {self.endpoint}")
        self.client = Client(self.endpoint)
        self.client.connect()

        # Cache nodes
        for key, nodeid in NODE_IDS.items():
            try:
                self.node_cache[key] = self.client.get_node(nodeid)
            except Exception as e:
                logger.warning(f"Failed to get node {nodeid} for {key}: {e}")

    def read(self, key: str) -> Any:
        if not self.client or key not in self.node_cache:
            # Mock data if OPC is not available or node missing
            if key == "channel_readings":
                import random
                return [random.uniform(0, 100) for _ in range(9)]
            if key == "channel_visibility":
                return [True] * 9
            return None

        with self._lock:
            try:
                return self.node_cache[key].get_value()
            except Exception as e:
                logger.error(f"OPC read error for {key}: {e}")
                return None

    def write(self, key: str, value: Any) -> bool:
        if not self.client or key not in self.node_cache:
            return False
        with self._lock:
            try:
                self.node_cache[key].set_value(value)
                return True
            except Exception as e:
                logger.error(f"OPC write error for {key}: {e}")
                return False

# Shared instance
opc = OpcUaWrapper(PLC_ENDPOINT)
