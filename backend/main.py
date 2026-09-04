"""
FastAPI Central Cloud / Network Telemetry Hub & WebSocket Service
Autonomous PPE Verification and Perimeter Access Control
"""

import os
import time
import logging
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Form, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

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
