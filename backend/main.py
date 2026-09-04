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
latest_frame_id: int = 0

# Global reference to running Edge Engine subprocess
edge_process: Optional[subprocess.Popen] = None

# Global stream quality and inference settings
stream_config = {
    "quality": "balanced",
    "jpeg_quality": 70,
    "inference_size": 640,
    "mirror": False
}

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
    global latest_frame, latest_frame_id
    frame_bytes = await request.body()
    if frame_bytes:
        latest_frame = frame_bytes
        latest_frame_id += 1
    return {"status": "ok"}


@app.get("/api/stream/video")
async def stream_video(request: Request):
    """
    Streams the live OpenCV/YOLOv8 annotated edge camera feed
    as an MJPEG multipart stream to browser clients.
    Yields ONLY the newest available frame without buffering old frames.
    Exits immediately when client disconnects to prevent lingering sockets.
    """
    async def frame_generator():
        last_sent_id = -1
        try:
            while True:
                if await request.is_disconnected():
                    break
                curr_id = latest_frame_id
                curr_frame = latest_frame
                # Yield strictly when a new frame is available
                if curr_frame is not None and curr_id != last_sent_id:
                    last_sent_id = curr_id
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n\r\n" + curr_frame + b"\r\n"
                    )
                await asyncio.sleep(0.03)  # ~30 FPS limit for strictly real-time delivery
        except (asyncio.CancelledError, GeneratorExit):
            pass

    return StreamingResponse(
        frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )



@app.get("/api/edge/status")
async def get_edge_status():
    """
    Returns whether the edge vision engine process is actively running.
    """
    is_running = edge_process is not None and edge_process.poll() is None
    return {"running": is_running}


@app.post("/api/edge/start")
async def start_edge_engine():
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
async def stop_edge_engine():
    """
    Terminates the edge engine process and resets the live frame buffer.
    """
    global edge_process, latest_frame, latest_frame_id
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
            latest_frame_id = 0
        return {"status": "stopped"}
    else:
        edge_process = None
        latest_frame = None
        latest_frame_id = 0
        return {"status": "not_running"}


class QualityConfigUpdate(BaseModel):
    mode: Optional[str] = None  # "fast", "balanced", "hd"
    mirror: Optional[bool] = None


@app.get("/api/edge/config")
async def get_edge_config():
    """
    Returns the current stream quality and model inference configuration.
    """
    return stream_config


@app.post("/api/edge/config")
async def update_edge_config(config_in: QualityConfigUpdate):
    """
    Updates the stream compression, YOLO inference resolution, and mirror mode dynamically.
    Modes:
      - fast: jpeg_quality=50, inference_size=480 (lowest latency / high FPS)
      - balanced: jpeg_quality=70, inference_size=640 (standard balance)
      - hd: jpeg_quality=90, inference_size=1080 (high-resolution details)
    Mirror:
      - true: horizontal flip of raw camera frame before inference and HUD rendering
      - false: normal camera orientation
    """
    global stream_config
    if config_in.mode is not None:
        mode = config_in.mode.lower().strip()
        if mode == "fast":
            stream_config.update({"quality": "fast", "jpeg_quality": 50, "inference_size": 480})
        elif mode == "hd":
            stream_config.update({"quality": "hd", "jpeg_quality": 90, "inference_size": 1080})
        elif mode == "balanced":
            stream_config.update({"quality": "balanced", "jpeg_quality": 70, "inference_size": 640})

    if config_in.mirror is not None:
        stream_config["mirror"] = bool(config_in.mirror)

    logger.info("Stream configuration updated: %s", stream_config)
    return stream_config




