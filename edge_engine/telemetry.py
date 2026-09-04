"""
Asynchronous Telemetry & Evidence Capture Dispatcher
Autonomous PPE Verification and Perimeter Access Control
"""

import os
import cv2
import time
import queue
import logging
import threading
import requests
import numpy as np
from typing import Dict, Any, Optional

logger = logging.getLogger("TelemetryDispatcher")


class TelemetryDispatcher:
    """
    Background worker that persists cropped/full evidence snapshot images
    and dispatches violation telemetry JSON payloads to the central backend.
    Ensures zero latency impact on the primary 30 FPS video inference loop.
    """
    def __init__(
        self,
        backend_url: str = "http://127.0.0.1:8000/api/violations",
        enabled: bool = True,
        snapshot_dir: str = "evidence_snapshots",
        cooldown_seconds: float = 4.0
    ):
        self.backend_url = backend_url
        self.enabled = enabled
        self.snapshot_dir = snapshot_dir
        self.cooldown_seconds = cooldown_seconds

        os.makedirs(self.snapshot_dir, exist_ok=True)

        self._queue = queue.Queue(maxsize=100)
        self._last_alert_timestamps: Dict[str, float] = {}
        self._lock = threading.Lock()
        self._stopped = False
        
        self._worker_thread = threading.Thread(
            target=self._process_queue,
            daemon=True,
            name="TelemetryWorkerThread"
        )
        self._worker_thread.start()

    def record_violation(
        self,
        frame: np.ndarray,
        person_eval: Dict[str, Any],
        geofence_eval: Dict[str, Any]
    ) -> bool:
        """
        Enqueues an incident event if outside the cooldown threshold.
        Returns True if enqueued, False if throttled by cooldown.
        """
        if not self.enabled:
            return False

        person_id = person_eval.get("person_id", 0)
        zone_id = geofence_eval.get("zone_id", "DEFAULT_ZONE")
        cooldown_key = f"{zone_id}_{person_id}"

        current_time = time.time()
        with self._lock:
            last_time = self._last_alert_timestamps.get(cooldown_key, 0.0)
            if (current_time - last_time) < self.cooldown_seconds:
                # Cooldown active; skip duplicate incident logging
                return False
            self._last_alert_timestamps[cooldown_key] = current_time

        # Deep copy frame for asynchronous snapshot persistence
        event_data = {
            "timestamp": int(current_time),
            "iso_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(current_time)),
            "zone_id": zone_id,
            "person_id": person_id,
            "missing_gear": person_eval.get("missing_gear", []),
            "compliance_status": "DENIED_PPE_VIOLATION",
            "bbox": person_eval.get("bbox", (0, 0, 0, 0)),
            "ground_position_meters": geofence_eval.get("ground_position_meters", (0.0, 0.0)),
            "frame_copy": frame.copy()
        }

        try:
            self._queue.put_nowait(event_data)
            return True
        except queue.Full:
            logger.warning("Telemetry queue full. Dropping event.")
            return False

    def _process_queue(self):
        """Worker thread loop consuming violation events."""
        while not self._stopped:
            try:
                event = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue

            try:
                # 1. Save evidence frame snapshot
                frame = event.pop("frame_copy")
                timestamp = event["timestamp"]
                person_id = event["person_id"]
                zone_id = event["zone_id"]
                
                filename = f"violation_{zone_id}_p{person_id}_{timestamp}.jpg"
                filepath = os.path.join(self.snapshot_dir, filename)
                
                # Annotate evidence frame with incident watermark
                annotated = frame.copy()
                cv2.rectangle(
                    annotated,
                    (20, 20),
                    (620, 100),
                    (0, 0, 0),
                    -1
                )
                cv2.putText(
                    annotated,
                    f"EVIDENCE: INCIDENT ALERT [{event['compliance_status']}]",
                    (30, 50),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 0, 255),
                    2
                )
                cv2.putText(
                    annotated,
                    f"Time: {event['iso_timestamp']} | Zone: {zone_id} | Missing: {', '.join(event['missing_gear'])}",
                    (30, 80),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.45,
                    (255, 255, 255),
                    1
                )

                cv2.imwrite(filepath, annotated)
                event["snapshot_filename"] = filename
                event["snapshot_path"] = filepath

                # 2. Dispatch HTTP payload to backend
                self._send_payload(event, filepath)
            except Exception as e:
                logger.error("Error processing telemetry queue item: %s", e)
            finally:
                self._queue.task_done()

    def _send_payload(self, event_data: Dict[str, Any], filepath: str):
        """Dispatches violation data and snapshot to REST backend."""
        try:
            # We send payload as JSON or multipart if file is attached
            with open(filepath, "rb") as img_f:
                files = {"snapshot": (os.path.basename(filepath), img_f, "image/jpeg")}
                data = {
                    "timestamp": str(event_data["timestamp"]),
                    "iso_timestamp": event_data["iso_timestamp"],
                    "zone_id": event_data["zone_id"],
                    "person_id": str(event_data["person_id"]),
                    "missing_gear": ",".join(event_data["missing_gear"]),
                    "compliance_status": event_data["compliance_status"],
                    "ground_x": str(event_data["ground_position_meters"][0]),
                    "ground_y": str(event_data["ground_position_meters"][1]),
                }
                resp = requests.post(self.backend_url, data=data, files=files, timeout=3.0)
                if resp.status_code in (200, 201):
                    logger.info("Successfully posted incident to backend: %s", resp.json())
                else:
                    logger.warning("Backend returned status %d: %s", resp.status_code, resp.text)
        except requests.exceptions.RequestException as e:
            # Expected if backend is not started yet during local standalone testing
            logger.info("Telemetry post skipped (Backend offline or unreachable): %s", e)

    def stop(self):
        """Stops the dispatcher worker cleanly."""
        self._stopped = True
