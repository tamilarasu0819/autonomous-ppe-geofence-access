"""
Incident Storage and Metrics Aggregation Layer
Autonomous PPE Verification and Perimeter Access Control
"""

import os
import time
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("IncidentStorage")

class IncidentStorage:
    """
    Manages in-memory and file storage for incident records and snapshots.
    """
    def __init__(self, snapshot_dir: str = "snapshots"):
        self.snapshot_dir = snapshot_dir
        os.makedirs(self.snapshot_dir, exist_ok=True)
        self.incidents: List[Dict[str, Any]] = []
        self.total_checks: int = 0
        self.last_incident_time: Optional[float] = None

    def add_incident(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Inserts an incident record into memory with auto-increment ID."""
        self.total_checks += 1
        record["id"] = len(self.incidents) + 1
        record["received_at"] = time.time()
        self.last_incident_time = record["received_at"]
        
        # Keep most recent 500 incidents in memory
        self.incidents.insert(0, record)
        if len(self.incidents) > 500:
            self.incidents.pop()
            
        return record

    def get_incidents(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieves list of latest incidents."""
        return self.incidents[:limit]

    def get_stats(self) -> Dict[str, Any]:
        """Computes live aggregated system statistics."""
        # Consider barrier actively locked if a violation occurred within last 5 seconds
        is_locked = False
        if self.last_incident_time and (time.time() - self.last_incident_time < 5.0):
            is_locked = True

        return {
            "total_incidents": len(self.incidents),
            "total_checks": max(self.total_checks, len(self.incidents)),
            "barrier_state": "LOCKED" if is_locked else "UNLOCKED",
            "active_alert": is_locked,
            "last_incident_timestamp": self.last_incident_time
        }
