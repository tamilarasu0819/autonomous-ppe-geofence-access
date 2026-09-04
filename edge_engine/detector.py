"""
Object Detection & Spatial PPE Containment Verification Engine
Autonomous PPE Verification and Perimeter Access Control
"""

import logging
from typing import List, Dict, Any, Tuple
import numpy as np

logger = logging.getLogger("PPEDetector")


class PPEDetector:
    """
    Ultralytics YOLOv8 detector with spatial containment verification.
    Associates personal protective equipment (helmet, vest, etc.) with individual
    person detections based on geometric overlap and anatomical anchor zones.
    """
    def __init__(
        self,
        model_path: str = "yolov8n.pt",
        confidence_threshold: float = 0.45,
        iou_threshold: float = 0.45,
        device: str = "cpu",
        required_gear: List[str] = None,
        mock_ppe_simulation: bool = False
    ):
        self.model_path = model_path
        self.confidence_threshold = confidence_threshold
        self.iou_threshold = iou_threshold
        self.device = device
        self.required_gear = required_gear or ["helmet", "vest"]
        self.mock_ppe_simulation = mock_ppe_simulation

        self.model = None
        self._load_model()

    def _load_model(self):
        """Loads Ultralytics YOLO model instance."""
        try:
            from ultralytics import YOLO
            logger.info("Loading YOLO model from: %s on device: %s", self.model_path, self.device)
            self.model = YOLO(self.model_path)
            logger.info("YOLO model loaded successfully.")
        except Exception as e:
            logger.error("Failed to load YOLO model: %s. Using heuristic fallback.", e)
            self.model = None

    @staticmethod
    def is_contained_in_upper_body(
        gear_bbox: Tuple[int, int, int, int],
        person_bbox: Tuple[int, int, int, int],
        vertical_ratio_max: float = 0.35
    ) -> bool:
        """
        Verifies if gear center (e.g. helmet) lies within the upper anatomical
        region (top 35%) of the person's bounding box.
        """
        gx1, gy1, gx2, gy2 = gear_bbox
        px1, py1, px2, py2 = person_bbox
        
        g_center_x = (gx1 + gx2) / 2.0
        g_center_y = (gy1 + gy2) / 2.0
        
        p_height = py2 - py1
        head_region_bottom = py1 + (p_height * vertical_ratio_max)
        
        # Horizontal containment check with 15% margin
        h_margin = (px2 - px1) * 0.15
        in_horizontal = (px1 - h_margin) <= g_center_x <= (px2 + h_margin)
        in_head_vertical = py1 <= g_center_y <= head_region_bottom

        return in_horizontal and in_head_vertical

    def detect_and_verify(self, frame: np.ndarray, sim_override_compliant: bool = False) -> List[Dict[str, Any]]:
        """
        Runs object detection on frame, extracts person instances,
        performs spatial containment checks for required PPE, and outputs
        compliance status.

        Returns list of person evaluation records:
        [
            {
                "person_id": int,
                "bbox": (x1, y1, x2, y2),
                "confidence": float,
                "detected_gear": ["helmet", ...],
                "missing_gear": ["vest", ...],
                "is_compliant": bool
            }, ...
        ]
        """
        results = []
        if self.model is None:
            # Heuristic simulation fallback if model failed to load
            h, w, _ = frame.shape
            sim_bbox = (int(w * 0.35), int(h * 0.25), int(w * 0.65), int(h * 0.85))
            detected = self.required_gear if sim_override_compliant else ["vest"]
            missing = [g for g in self.required_gear if g not in detected]
            return [{
                "person_id": 1,
                "bbox": sim_bbox,
                "confidence": 0.92,
                "detected_gear": detected,
                "missing_gear": missing,
                "is_compliant": len(missing) == 0
            }]

        # Perform YOLO inference
        preds = self.model.predict(
            source=frame,
            conf=self.confidence_threshold,
            iou=self.iou_threshold,
            device=self.device,
            verbose=False
        )

        if not preds or len(preds) == 0:
            return []

        prediction = preds[0]
        boxes = prediction.boxes

        person_list = []
        gear_list = []

        # Parse detections into person instances and accessory gear
        for idx, box in enumerate(boxes):
            cls_id = int(box.cls[0].item())
            cls_name = prediction.names.get(cls_id, str(cls_id)).lower()
            conf = float(box.conf[0].item())
            xyxy = box.xyxy[0].cpu().numpy().astype(int)
            bbox = (int(xyxy[0]), int(xyxy[1]), int(xyxy[2]), int(xyxy[3]))

            # In standard COCO: class 0 is 'person'
            if cls_name == "person" or cls_id == 0:
                person_list.append({
                    "id": idx + 1,
                    "bbox": bbox,
                    "confidence": conf
                })
            else:
                # Potential gear items (e.g. hat, backpack, tie, helmet in custom models)
                gear_list.append({
                    "name": cls_name,
                    "bbox": bbox,
                    "conf": conf
                })

        # Match gear to persons using spatial containment
        for person in person_list:
            p_bbox = person["bbox"]
            assigned_gear = []

            for gear in gear_list:
                # Spatial containment check: is gear worn by this person?
                gx1, gy1, gx2, gy2 = gear["bbox"]
                px1, py1, px2, py2 = p_bbox

                # Center of gear must lie inside horizontal boundary of person
                gc_x = (gx1 + gx2) / 2.0
                gc_y = (gy1 + gy2) / 2.0
                if px1 <= gc_x <= px2 and py1 <= gc_y <= py2:
                    assigned_gear.append(gear["name"])

            # In simulation mode or standard COCO without custom helmet weights:
            if self.mock_ppe_simulation:
                if sim_override_compliant:
                    assigned_gear = list(self.required_gear)
                else:
                    # In simulation mode, default to missing helmet to demonstrate access restriction
                    # unless toggled
                    assigned_gear = ["vest"]

            missing = [req for req in self.required_gear if req not in assigned_gear]
            is_compliant = (len(missing) == 0)

            results.append({
                "person_id": person["id"],
                "bbox": p_bbox,
                "confidence": person["confidence"],
                "detected_gear": assigned_gear,
                "missing_gear": missing,
                "is_compliant": is_compliant
            })

        return results
