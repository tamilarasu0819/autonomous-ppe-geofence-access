"""
FastAPI Central Cloud / Network Telemetry Hub & WebSocket Service
Autonomous PPE Verification and Perimeter Access Control
"""

import os
import sys
import time
import logging
import asyncio
import subprocess
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Form, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# In-memory buffer holding the latest JPEG frame from Edge Engine
latest_frame: Optional[bytes] = None

# Global reference to running Edge Engine subprocess
edge_process: Optional[subprocess.Popen] = None

from storage import IncidentStorage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BackendHub")

app = FastAPI(
    title="Autonomous PPE Perimeter Access Telemetry API",
    description="Backend API and live WebSocket alert hub for construction hazard zone access control.",
    version="1.0.0"
)

# CORS middleware for local frontend and Vercel cloud dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure snapshot storage directory exists and mount static routes
SNAPSHOT_DIR = os.path.join(os.path.dirname(__file__), "snapshots")
os.makedirs(SNAPSHOT_DIR, exist_ok=True)
app.mount("/snapshots", StaticFiles(directory=SNAPSHOT_DIR), name="snapshots")

storage = IncidentStorage(snapshot_dir=SNAPSHOT_DIR)


class ConnectionManager:
    """Manages active WebSocket connections to push alerts to dashboard clients."""
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("New WebSocket client connected. Total clients: %d", len(self.active_connections))

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info("WebSocket client disconnected. Total clients: %d", len(self.active_connections))

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning("Failed to send WebSocket message: %s", e)


manager = ConnectionManager()


@app.get("/")
def root():
    return {
        "status": "online",
        "service": "Autonomous PPE Verification & Perimeter Access Control API",
        "docs": "/docs"
    }


@app.get("/api/stats")
def get_stats():
    """Returns aggregated live metrics for dashboard gauges."""
    return storage.get_stats()


@app.get("/api/violations")
def list_violations(limit: int = 50):
    """Retrieves chronological incident log."""
    return storage.get_incidents(limit=limit)


@app.post("/api/violations")
async def create_violation(
    timestamp: str = Form(...),
    iso_timestamp: str = Form(...),
    zone_id: str = Form(...),
    person_id: str = Form(...),
    missing_gear: str = Form(""),
    compliance_status: str = Form(...),
    ground_x: Optional[str] = Form("0.0"),
    ground_y: Optional[str] = Form("0.0"),
    snapshot: Optional[UploadFile] = File(None)
):
    """
    Receives violation telemetry from edge engine, saves evidence snapshot,
    records incident, and broadcasts real-time alert via WebSockets.
    """
    snapshot_filename = None
    snapshot_url = None

    if snapshot:
        filename = f"incident_{zone_id}_{person_id}_{int(time.time())}.jpg"
        filepath = os.path.join(SNAPSHOT_DIR, filename)
        content = await snapshot.read()
        with open(filepath, "wb") as f:
            f.write(content)
        snapshot_filename = filename
        snapshot_url = f"/snapshots/{filename}"

    incident_record = {
        "timestamp": int(timestamp) if timestamp.isdigit() else int(time.time()),
        "iso_timestamp": iso_timestamp,
        "zone_id": zone_id,
        "person_id": int(person_id) if person_id.isdigit() else person_id,
        "missing_gear": [g.strip() for g in missing_gear.split(",") if g.strip()],
        "compliance_status": compliance_status,
        "ground_position": [float(ground_x), float(ground_y)],
        "snapshot_url": snapshot_url
    }

    stored = storage.add_incident(incident_record)

    # Broadcast alert to all listening frontend dashboards
    await manager.broadcast({
        "type": "NEW_VIOLATION_ALERT",
        "data": stored,
        "stats": storage.get_stats()
    })

    return {"status": "success", "incident": stored}


@app.websocket("/ws/alerts")
async def websocket_alerts_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time live push alerts to the frontend."""
    await manager.connect(websocket)
    # Send initial status snapshot upon connection
    await websocket.send_json({
        "type": "INITIAL_STATE",
        "stats": storage.get_stats(),
        "recent_incidents": storage.get_incidents(limit=10)
    })
    try:
        while True:
            # Keepalive receiver
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.post("/api/stream/frame")
async def upload_stream_frame(request: Request):
    """
    Receives raw JPEG encoded byte frames from the Edge Engine
    and updates the in-memory MJPEG broadcast buffer.
    """
    global latest_frame
    frame_bytes = await request.body()
    if frame_bytes:
        latest_frame = frame_bytes
    return {"status": "ok"}


@app.get("/api/stream/video")
async def stream_video():
    """
    Streams the live OpenCV/YOLOv8 annotated edge camera feed
    as an MJPEG multipart stream to browser clients.
    """
    async def frame_generator():
        while True:
            if latest_frame is not None:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + latest_frame + b"\r\n"
                )
            await asyncio.sleep(0.033)  # ~30 FPS throttle to eliminate CPU spinning

    return StreamingResponse(
        frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


@app.get("/api/edge/status")
def get_edge_status():
    """
    Returns whether the edge vision engine process is actively running.
    """
    is_running = edge_process is not None and edge_process.poll() is None
    return {"running": is_running}


@app.post("/api/edge/start")
def start_edge_engine():
    """
    Spawns edge_engine/main.py as an asynchronous subprocess.
    """
    global edge_process
    if edge_process is not None and edge_process.poll() is None:
        return {"status": "already_running"}

    # Resolve project root and edge_engine script path
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    edge_script = os.path.join(project_root, "edge_engine", "main.py")
    if not os.path.exists(edge_script):
        edge_script = "edge_engine/main.py"
        project_root = os.getcwd()

    cmd = [sys.executable, edge_script]
    logger.info("Launching Edge Engine: %s in cwd: %s", cmd, project_root)

    try:
        edge_process = subprocess.Popen(
            cmd,
            cwd=project_root
        )
        return {"status": "started", "pid": edge_process.pid}
    except Exception as e:
        logger.error("Failed to start Edge Engine: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/edge/stop")
def stop_edge_engine():
    """
    Terminates the edge engine process and resets the live frame buffer.
    """
    global edge_process, latest_frame
    if edge_process is not None and edge_process.poll() is None:
        logger.info("Stopping Edge Engine (PID %s)...", edge_process.pid)
        try:
            edge_process.terminate()
            try:
                edge_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                logger.warning("Edge Engine did not exit within timeout; killing...")
                edge_process.kill()
        except Exception as e:
            logger.error("Error stopping Edge Engine: %s", e)
        finally:
            edge_process = None
            latest_frame = None
        return {"status": "stopped"}
    else:
        edge_process = None
        latest_frame = None
        return {"status": "not_running"}


