"""
Main Orchestration Runner for Autonomous PPE Verification & Perimeter Access Control
Phase 1 Core Vision, Geofencing, and Telematics Pipeline
"""

import os
import sys
import time
import argparse
import logging
import yaml
import cv2
import numpy as np

# Configure logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (%(name)s) %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("EdgeEngineMain")

# Import local modules
from camera import VideoStream
from detector import PPEDetector
from geofence import SpatialGeofence
from telematics import TelematicsController, TOKEN_ALLOW, TOKEN_DENIED
from telemetry import TelemetryDispatcher


def load_config(config_path: str) -> dict:
    """Loads YAML configuration file."""
    if not os.path.exists(config_path):
        logger.error("Configuration file not found: %s", config_path)
        sys.exit(1)
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def draw_hud(
    frame: np.ndarray,
    barrier_state: int,
    fps: float,
    person_count: int,
    violation_count: int,
    mock_ppe_mode: bool,
    sim_compliant_override: bool
) -> np.ndarray:
    """
    Renders top status dashboard header HUD onto the frame.
    """
    h, w, _ = frame.shape
    
    # Top banner background
    cv2.rectangle(frame, (0, 0), (w, 75), (20, 20, 25), -1)
    cv2.line(frame, (0, 75), (w, 75), (60, 60, 70), 2)

    # Title
    cv2.putText(
        frame,
        "AUTONOMOUS PPE VERIFICATION & PERIMETER ACCESS CONTROL",
        (20, 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (255, 255, 255),
        2,
        cv2.LINE_AA
    )

    # Subtitle / FPS / Stats
    mode_str = "COMPLIANT" if sim_compliant_override else "SIM_VIOLATION"
    cv2.putText(
        frame,
        f"FPS: {fps:.1f} | Active Persons: {person_count} | Violations: {violation_count} | PPE Mode: {mode_str} [Key 'M' to toggle]",
        (20, 55),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        (180, 180, 180),
        1,
        cv2.LINE_AA
    )

    # Barrier Access Status Badge (Top Right)
    badge_w = 270
    badge_h = 50
    badge_x = w - badge_w - 20
    badge_y = 12

    if barrier_state == TOKEN_DENIED:
        # Red warning badge
        cv2.rectangle(frame, (badge_x, badge_y), (badge_x + badge_w, badge_y + badge_h), (0, 0, 180), -1)
        cv2.rectangle(frame, (badge_x, badge_y), (badge_x + badge_w, badge_y + badge_h), (0, 0, 255), 2)
        cv2.putText(
            frame,
            "LOCKED: ACCESS DENIED",
            (badge_x + 15, badge_y + 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            2,
            cv2.LINE_AA
        )
        cv2.putText(
            frame,
            "PERIMETER HAZARD ACTIVE",
            (badge_x + 15, badge_y + 42),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.40,
            (220, 220, 255),
            1,
            cv2.LINE_AA
        )
    else:
        # Green allowed badge
        cv2.rectangle(frame, (badge_x, badge_y), (badge_x + badge_w, badge_y + badge_h), (0, 140, 40), -1)
        cv2.rectangle(frame, (badge_x, badge_y), (badge_x + badge_w, badge_y + badge_h), (0, 220, 60), 2)
        cv2.putText(
            frame,
            "UNLOCKED: NORMAL ACCESS",
            (badge_x + 12, badge_y + 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            2,
            cv2.LINE_AA
        )
        cv2.putText(
            frame,
            "ZONE ALL-CLEAR / COMPLIANT",
            (badge_x + 12, badge_y + 42),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.40,
            (200, 255, 200),
            1,
            cv2.LINE_AA
        )

    # Bottom helper footer
    cv2.rectangle(frame, (0, h - 28), (w, h), (15, 15, 18), -1)
    cv2.putText(
        frame,
        "Press [Q]: Exit  |  [M]: Toggle PPE Simulation (Violation <-> Compliant)  |  [S]: Manual Evidence Snapshot",
        (20, h - 10),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.42,
        (150, 150, 150),
        1,
        cv2.LINE_AA
    )

    return frame


def render_person_annotations(
    frame: np.ndarray,
    person: dict,
    geofence_eval: dict
) -> np.ndarray:
    """
    Renders bounding boxes, foot anchor points, ground coordinates,
    and compliance status tags for an individual person.
    """
    x1, y1, x2, y2 = person["bbox"]
    is_compliant = person["is_compliant"]
    in_hazard = geofence_eval["in_hazard_zone"]
    foot_x, foot_y = geofence_eval["foot_anchor_image"]
    ground_x, ground_y = geofence_eval["ground_position_meters"]

    # Determine color scheme based on compliance and zone status
    if in_hazard and not is_compliant:
        # Severe breach: Red
        box_color = (0, 0, 255)
        tag_bg = (0, 0, 200)
        status_text = f"BREACH! MISSING: {','.join(person['missing_gear']).upper()}"
    elif in_hazard and is_compliant:
        # Authorized entry inside hazard: Yellow / Green
        box_color = (0, 220, 255)
        tag_bg = (0, 160, 180)
        status_text = "AUTHORIZED (PPE VERIFIED)"
    elif not is_compliant:
        # Non-compliant but outside hazard zone: Orange
        box_color = (0, 140, 255)
        tag_bg = (0, 100, 200)
        status_text = f"CAUTION: MISSING {','.join(person['missing_gear']).upper()}"
    else:
        # Fully compliant and outside: Bright Green
        box_color = (0, 230, 80)
        tag_bg = (0, 160, 40)
        status_text = "COMPLIANT (PPE OK)"

    # Draw person bounding box
    cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, 2)

    # Draw foot contact point (ground anchor) with crosshair
    cv2.circle(frame, (int(foot_x), int(foot_y)), 7, box_color, -1)
    cv2.circle(frame, (int(foot_x), int(foot_y)), 10, (255, 255, 255), 2)
    cv2.line(frame, (int(foot_x) - 14, int(foot_y)), (int(foot_x) + 14, int(foot_y)), box_color, 1)

    # Status tag banner above head
    tag_h = 24
    tag_w = max(240, (x2 - x1))
    tag_y1 = max(80, y1 - tag_h)
    cv2.rectangle(frame, (x1, tag_y1), (x1 + tag_w, tag_y1 + tag_h), tag_bg, -1)
    cv2.rectangle(frame, (x1, tag_y1), (x1 + tag_w, tag_y1 + tag_h), (255, 255, 255), 1)
    cv2.putText(
        frame,
        f"P{person['person_id']}: {status_text}",
        (x1 + 6, tag_y1 + 16),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.42,
        (255, 255, 255),
        1,
        cv2.LINE_AA
    )

    # Ground coordinate telemetry label below feet
    coord_text = f"Ground Pos: ({ground_x:.2f}m, {ground_y:.2f}m)"
    cv2.putText(
        frame,
        coord_text,
        (int(foot_x) - 70, min(frame.shape[0] - 35, int(foot_y) + 20)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.40,
        (255, 255, 0),
        1,
        cv2.LINE_AA
    )

    return frame


def main():
    parser = argparse.ArgumentParser(description="Autonomous PPE & Perimeter Access Control Edge Runner")
    parser.add_argument("--config", type=str, default="edge_engine/config.yaml", help="Path to config.yaml")
    parser.add_argument("--source", type=str, default=None, help="Override camera source index or RTSP URL")
    parser.add_argument("--mock-hardware", action="store_true", default=None, help="Force mock hardware mode")
    parser.add_argument("--headless", action="store_true", help="Run without OpenCV GUI display window")
    args = parser.parse_args()

    # Load configuration
    cfg = load_config(args.config)

    camera_cfg = cfg.get("camera", {})
    detector_cfg = cfg.get("detector", {})
    geofence_cfg = cfg.get("geofence", {})
    telematics_cfg = cfg.get("telematics", {})
    telemetry_cfg = cfg.get("telemetry", {})

    # Override options via CLI if provided
    cam_source = camera_cfg.get("source", 0)
    if args.source is not None:
        try:
            cam_source = int(args.source)
        except ValueError:
            cam_source = args.source

    mock_hardware = telematics_cfg.get("mock_mode", True)
    if args.mock_hardware is not None:
        mock_hardware = args.mock_hardware

    logger.info("==========================================================")
    logger.info("Initializing Autonomous PPE Access Control Edge Engine")
    logger.info("Camera Source: %s", cam_source)
    logger.info("Mock Hardware: %s", mock_hardware)
    logger.info("Hazard Zone: %s (%s)", geofence_cfg.get("zone_id"), geofence_cfg.get("zone_name"))
    logger.info("==========================================================")

    # 1. Initialize Video Capture
    camera = VideoStream(
        source=cam_source,
        width=camera_cfg.get("width", 1280),
        height=camera_cfg.get("height", 720),
        fps=camera_cfg.get("fps", 30),
        reconnect_timeout_sec=camera_cfg.get("reconnect_timeout_sec", 5.0),
        max_reconnect_attempts=camera_cfg.get("max_reconnect_attempts", 10),
        buffer_size=camera_cfg.get("buffer_size", 1)
    ).start()

    # 2. Initialize Geofence & Homography Math Engine
    geofence = SpatialGeofence(
        image_calibration_points=geofence_cfg["calibration_image_points"],
        ground_calibration_points=geofence_cfg["calibration_ground_points"],
        hazard_polygon_image=geofence_cfg["hazard_polygon_image"],
        zone_id=geofence_cfg.get("zone_id", "HAZARD_ZONE_01"),
        zone_name=geofence_cfg.get("zone_name", "Perimeter Hazard Zone")
    )

    # 3. Initialize YOLOv8 PPE Detector
    detector = PPEDetector(
        model_path=detector_cfg.get("model_path", "yolov8n.pt"),
        confidence_threshold=detector_cfg.get("confidence_threshold", 0.45),
        iou_threshold=detector_cfg.get("iou_threshold", 0.45),
        device=detector_cfg.get("device", "cpu"),
        required_gear=detector_cfg.get("required_gear", ["helmet", "vest"]),
        mock_ppe_simulation=detector_cfg.get("mock_ppe_simulation", True)
    )

    # 4. Initialize Telematics Controller (HAL)
    telematics = TelematicsController(
        port=telematics_cfg.get("serial_port", "COM3"),
        baud_rate=telematics_cfg.get("baud_rate", 115200),
        mock_mode=mock_hardware
    )

    # 5. Initialize Asynchronous Telemetry Dispatcher
    telemetry = TelemetryDispatcher(
        backend_url=telemetry_cfg.get("backend_url", "http://127.0.0.1:8000/api/violations"),
        enabled=telemetry_cfg.get("enabled", True),
        snapshot_dir=telemetry_cfg.get("snapshot_dir", "evidence_snapshots"),
        cooldown_seconds=telemetry_cfg.get("cooldown_seconds", 4.0)
    )

    current_barrier_state = TOKEN_ALLOW
    sim_compliant_override = False
    fps_time = time.time()
    fps_counter = 0
    current_fps = 0.0

    window_name = "Autonomous PPE Verification & Perimeter Access Control"
    if not args.headless:
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(window_name, 1280, 720)

    logger.info("Edge pipeline execution loop started.")

    try:
        while True:
            grabbed, frame = camera.read()
            if not grabbed or frame is None:
                time.sleep(0.01)
                continue

            # Update FPS tracking
            fps_counter += 1
            if time.time() - fps_time >= 1.0:
                current_fps = fps_counter / (time.time() - fps_time)
                fps_counter = 0
                fps_time = time.time()

            # Step 1: Detect persons and verify PPE
            persons = detector.detect_and_verify(frame, sim_override_compliant=sim_compliant_override)

            # Step 2: Evaluate spatial geofence inclusion and breaches
            violations_in_hazard = []
            evaluations = []

            for person in persons:
                eval_data = geofence.evaluate_person(person["bbox"])
                evaluations.append(eval_data)

                # Check breach condition: Inside hazard zone AND missing required PPE
                if eval_data["in_hazard_zone"] and not person["is_compliant"]:
                    violations_in_hazard.append((person, eval_data))

            # Step 3: Determine Physical Access Barrier State
            if len(violations_in_hazard) > 0:
                desired_state = TOKEN_DENIED
            else:
                desired_state = TOKEN_ALLOW

            # Step 4: Dispatch Telematics State Change / Keepalive
            if desired_state != current_barrier_state:
                telematics.dispatch_state(desired_state)
                current_barrier_state = desired_state

            # Step 5: Asynchronous Evidence & Telemetry Logging
            for person, eval_data in violations_in_hazard:
                telemetry.record_violation(frame, person, eval_data)

            # Step 6: Visual Rendering
            if not args.headless:
                display_frame = frame.copy()

                # Render hazard polygon overlay
                is_alert = (current_barrier_state == TOKEN_DENIED)
                display_frame = geofence.render_overlay(display_frame, is_alert_active=is_alert)

                # Render individual person annotations
                for person, eval_data in zip(persons, evaluations):
                    display_frame = render_person_annotations(display_frame, person, eval_data)

                # Render Top HUD & Barrier Badge
                display_frame = draw_hud(
                    display_frame,
                    barrier_state=current_barrier_state,
                    fps=current_fps,
                    person_count=len(persons),
                    violation_count=len(violations_in_hazard),
                    mock_ppe_mode=detector.mock_ppe_simulation,
                    sim_compliant_override=sim_compliant_override
                )

                cv2.imshow(window_name, display_frame)

                # Handle keyboard inputs
                key = cv2.waitKey(1) & 0xFF
                if key in (ord('q'), ord('Q'), 27):  # 'q' or ESC
                    logger.info("User requested exit via keyboard.")
                    break
                elif key in (ord('m'), ord('M')):
                    sim_compliant_override = not sim_compliant_override
                    logger.info("Toggled Mock PPE override. Compliant: %s", sim_compliant_override)
                elif key in (ord('s'), ord('S')):
                    manual_path = os.path.join(telemetry.snapshot_dir, f"manual_snapshot_{int(time.time())}.jpg")
                    cv2.imwrite(manual_path, display_frame)
                    logger.info("Saved manual snapshot: %s", manual_path)

    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received.")
    finally:
        logger.info("Cleaning up pipeline resources...")
        camera.stop()
        telemetry.stop()
        telematics.close()
        if not args.headless:
            cv2.destroyAllWindows()
        logger.info("Edge pipeline terminated cleanly.")


if __name__ == "__main__":
    main()
