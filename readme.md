# Autonomous PPE Verification and Perimeter Access Control for Construction

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg)](https://fastapi.tiangolo.com)
[![Ultralytics YOLOv8](https://img.shields.io/badge/YOLOv8-Inference-blueviolet.svg)](https://docs.ultralytics.com/)
[![React + Vite](https://img.shields.io/badge/Frontend-React%20%2B%20Vite%20%2B%20Tailwind-61DAFB.svg)](https://vitejs.dev/)

An end-to-end cyber-physical vision and access control system that replaces passive CCTV surveillance with active perimeter interlock. The system detects workers and their mandatory Personal Protective Equipment (PPE) in real-time video streams, evaluates their physical position relative to dynamic hazard zones using homography projection and point-in-polygon ray-casting, and transmits low-latency binary serial state tokens to control physical access barriers (servos, buzzers, and gates).

---

## Architecture Overview

```
+-----------------------------------------------------------------------------------+
|                            EDGE COMPUTING RUNNER                                 |
|                                                                                   |
|  +--------------------+       +----------------------+       +-----------------+  |
|  | Video Ingestion    | ----> | YOLOv8 Vision Engine | ----> | Geofence Math   |  |
|  | (Webcam/USB/RTSP)  |       | (Person & PPE Gear)  |       | (Homography PIP)|  |
|  +--------------------+       +----------------------+       +-----------------+  |
|                                                                       |           |
|                                                                       v           |
|  +--------------------+       +----------------------+       +-----------------+  |
|  | Async Telemetry    | <---- | State Arbiter Logic  | ----> | Telematics HAL  |  |
|  | (Evidence Worker)  |       | (Access Permitted /  |       | (UART 115200    |  |
|  +--------------------+       |  Hazard Breach)      |       |  CRC-16 CCITT)  |  |
|            |                  +----------------------+       +-----------------+  |
+------------|----------------------------------------------------------|-----------+
             | REST + Multipart                                         | Serial / Mock
             v                                                          v
+-----------------------------+                           +-------------------------+
|   FASTAPI BACKEND HUB       |                           |  PHYSICAL ACCESS GATE   |
| - REST Incident Storage     |                           | - Microcontroller / MCU |
| - WebSocket Alert Streaming |                           | - Servo Motor Latch     |
| - Snapshot Static Serving   |                           | - Warning Buzzer        |
+-----------------------------+                           +-------------------------+
             |
             | WebSockets (/ws/alerts)
             v
+-----------------------------+
|   REACT + VITE DASHBOARD    |
| - Real-Time Barrier Status  |
| - Incident Telemetry Stream |
| - Snapshot Visual Inspector |
+-----------------------------+
```

---

## Key Features

1. **Unified Camera Abstraction (`camera.py`)**:
   - Supports laptop webcam (`0`), external USB cameras (`1, 2`), or network RTSP IP streams (`rtsp://...`).
   - Dedicated reader thread with automatic reconnection logic and synthetic test pattern generator fallback.

2. **YOLOv8 Detection & Spatial Containment (`detector.py`)**:
   - Uses Ultralytics YOLOv8 for human detection and accessories.
   - Evaluates anatomical containment: verifies whether protective gear centers lie within the head or torso bounding regions of the respective individual.
   - Built-in simulation toggle (`M` key) to simulate compliance state transitions live on laptop webcams.

3. **Homography & Point-in-Polygon Geofencing (`geofence.py`)**:
   - Extracts the ground contact anchor point at the foot base: $(x_{mid}, y_{max})$.
   - Projects 2D camera coordinates $(u, v)$ onto a top-down metric ground plane $(X_g, Y_g)$ using planar homography matrix $H$:
     $$\begin{bmatrix} x' \\ y' \\ w \end{bmatrix} = H \begin{bmatrix} u \\ v \\ 1 \end{bmatrix}, \quad X_g = \frac{x'}{w}, \quad Y_g = \frac{y'}{w}$$
   - Evaluates hazard polygon containment using ray-casting (`cv2.pointPolygonTest`).

4. **Structured UART Telematics Protocol (`telematics.py`)**:
   - Binary frame format (10 bytes total):
     ```
     [ 0xAA | MSG_ID (1B) | STATE_TOKEN (1B) | TIMESTAMP (4B) | CRC-16 (2B) | 0x55 ]
     ```
   - State tokens: `0x01` = `ALLOW` (Barrier Unlocked), `0x02` = `DENIED` (Barrier Locked / Alarm Active).
   - Standard CRC-16-CCITT checksum calculation over payload with error verification.
   - Hardware Abstraction Layer (HAL): In `MOCK_MODE = True`, prints visual console banners (`[BARRIER: LOCKED]`, `[BUZZER: PULSED]`). In `MOCK_MODE = False`, writes directly to physical serial COM ports at 115200 baud.

5. **Asynchronous Telemetry Dispatcher (`telemetry.py`)**:
   - Background non-blocking queue capturing cropped violation evidence snapshots and posting metadata payloads to the central backend without stalling the 30 FPS video loop.

6. **Full-Stack Cloud & Dashboard Ready**:
   - **Backend (`backend/`)**: FastAPI, WebSockets (`/ws/alerts`), Procfile for Render deployment.
   - **Frontend (`frontend/`)**: React 18, Vite, Tailwind CSS, Lucide icons, `vercel.json` deployment config.

---

## Directory Structure

```
autonomous-ppe-geofence-access/
├── edge_engine/                   # Local Computer Vision & Telematics Runner
│   ├── config.yaml                # Unified camera, geofence, and telematics config
│   ├── camera.py                  # Threaded camera capture & auto-reconnect
│   ├── detector.py                # YOLOv8 inference & PPE containment logic
│   ├── geofence.py                # Homography matrix & Point-in-Polygon math
│   ├── telematics.py              # Hardware Abstraction Layer & CRC-16 packet framing
│   ├── telemetry.py               # Async snapshot saving & HTTP dispatcher
│   ├── main.py                    # Master edge orchestration loop with OpenCV HUD
│   ├── requirements.txt           # Edge dependencies
│   └── tests/
│       └── test_pipeline.py       # Unit tests for telematics, homography & detector
├── backend/                       # FastAPI Central Incident & WebSocket Hub
│   ├── main.py                    # REST endpoints & WebSocket alert broadcast
│   ├── storage.py                 # In-memory & disk incident repository
│   ├── Procfile                   # Cloud runner profile for Render
│   └── requirements.txt           # Backend dependencies
├── frontend/                      # Web Monitoring & Incident Response Dashboard
│   ├── src/                       # React components & live WebSocket hooks
│   ├── package.json               # Frontend dependencies (React, Vite, Tailwind)
│   ├── vite.config.js             # Vite configuration
│   ├── tailwind.config.js         # Tailwind configuration
│   └── vercel.json                # Vercel SPA routing configuration
└── README.md
```

---

## Quickstart Guide

### 1. Run the Local Edge Engine

```bash
# 1. Navigate to edge engine
cd edge_engine

# 2. Run unit tests
python -m unittest tests/test_pipeline.py

# 3. Start the edge vision and telematics runner
python main.py
```

#### Keyboard Controls in Edge HUD:
- `Q` or `ESC`: Quit pipeline cleanly.
- `M`: Toggle mock PPE compliance simulation (switches worker between Compliant and Violation states).
- `S`: Save manual evidence snapshot.

### 2. Run the Central Backend Hub

```bash
cd backend
uvicorn main:app --reload --port 8000
```
- API Docs: `http://localhost:8000/docs`
- WebSocket Alert Stream: `ws://localhost:8000/ws/alerts`

### 3. Run the Monitoring Dashboard

```bash
cd frontend
npm install
npm run dev
```
Open `http://localhost:3000` to inspect live access barrier status, telemetry feeds, and violation snapshot evidence.

---

## Telematics Packet Specification

| Field | Size | Type | Value / Description |
| :--- | :--- | :--- | :--- |
| `START_BYTE` | 1 Byte | Hex | `0xAA` |
| `MSG_ID` | 1 Byte | uint8 | Rolling sequence counter (0 - 255) |
| `STATE_TOKEN` | 1 Byte | uint8 | `0x01` = ALLOW (Barrier Unlocked)<br>`0x02` = DENIED (Barrier Locked) |
| `TIMESTAMP` | 4 Bytes | uint32 (BE) | Unix epoch timestamp in seconds |
| `CRC-16` | 2 Bytes | uint16 (BE) | CRC-16-CCITT checksum over bytes 1..6 |
| `STOP_BYTE` | 1 Byte | Hex | `0x55` |

---

## License
MIT License. Built for industrial safety and autonomous cyber-physical perimeter access control.