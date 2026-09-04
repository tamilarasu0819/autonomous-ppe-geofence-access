"""
Spatial Geofencing, Planar Homography & Geometric Ray-Casting Module
Autonomous PPE Verification and Perimeter Access Control
"""

import cv2
import numpy as np
from typing import List, Tuple, Optional


class SpatialGeofence:
    """
    Manages camera-to-ground planar homography and point-in-polygon (PIP)
    hazard zone evaluations for foot contact points.
    """
    def __init__(
        self,
        image_calibration_points: List[List[float]],
        ground_calibration_points: List[List[float]],
        hazard_polygon_image: List[List[float]],
        zone_id: str = "HAZARD_ZONE_01",
        zone_name: str = "Excavation Pit Hazard Area"
    ):
        self.zone_id = zone_id
        self.zone_name = zone_name
        
        # 4-point image calibration references (u, v)
        self.src_pts = np.array(image_calibration_points, dtype=np.float32)
        # 4-point metric ground plane references (X, Y)
        self.dst_pts = np.array(ground_calibration_points, dtype=np.float32)
        
        # Compute 3x3 Planar Homography matrix H
        # H transforms image coordinates (u, v) -> ground plane coordinates (X, Y)
        self.H = cv2.getPerspectiveTransform(self.src_pts, self.dst_pts)
        self.H_inv = np.linalg.inv(self.H)
        
        # Hazard polygon in image coordinate space (as integer numpy array for OpenCV)
        self.polygon_image = np.array(hazard_polygon_image, dtype=np.int32)
        
        # Hazard polygon in metric ground plane coordinates (meters)
        self.polygon_ground = self.project_points_to_ground(self.polygon_image.astype(np.float32))

    @staticmethod
    def get_foot_anchor(bbox: Tuple[int, int, int, int]) -> Tuple[float, float]:
        """
        Extracts the bottom-center coordinate of the person's bounding box
        representing the physical ground contact anchor point.
        bbox format: (x1, y1, x2, y2)
        anchor: (x_mid, y_max) = ((x1 + x2) / 2.0, y2)
        """
        x1, y1, x2, y2 = bbox
        x_mid = (x1 + x2) / 2.0
        y_max = float(y2)
        return (x_mid, y_max)

    def project_point_to_ground(self, point: Tuple[float, float]) -> Tuple[float, float]:
        """
        Applies homography transformation to project an image-space 2D point (u, v)
        onto the metric ground plane (X_g, Y_g) in meters, eliminating perspective tilt.
        """
        pt_homogeneous = np.array([[[point[0], point[1]]]], dtype=np.float32)
        projected = cv2.perspectiveTransform(pt_homogeneous, self.H)
        return (float(projected[0][0][0]), float(projected[0][0][1]))

    def project_points_to_ground(self, points: np.ndarray) -> np.ndarray:
        """
        Vectorized homography projection of multiple points.
        points shape: (N, 2)
        """
        pts_reshaped = points.reshape(-1, 1, 2).astype(np.float32)
        projected = cv2.perspectiveTransform(pts_reshaped, self.H)
        return projected.reshape(-1, 2)

    def check_point_in_hazard(self, point: Tuple[float, float], measure_dist: bool = False) -> Tuple[bool, float]:
        """
        Evaluates whether a foot anchor point resides within the hazard polygon
        using Point-in-Polygon (PIP) ray-casting (cv2.pointPolygonTest).

        Returns:
            is_inside: True if inside or directly on the polygon boundary.
            distance: Signed distance to polygon edge (+ inside, - outside, 0 on edge).
        """
        pt_int = (float(point[0]), float(point[1]))
        # cv2.pointPolygonTest returns positive distance inside, negative outside, zero on edge
        dist = cv2.pointPolygonTest(self.polygon_image, pt_int, measureDist=True)
        is_inside = dist >= 0.0
        return is_inside, dist

    def evaluate_person(self, bbox: Tuple[int, int, int, int]) -> dict:
        """
        Performs full spatial evaluation for a person:
        - Extracts foot anchor point
        - Computes real-world ground plane position (meters)
        - Executes PIP test against hazard polygon
        """
        foot_anchor = self.get_foot_anchor(bbox)
        ground_pos = self.project_point_to_ground(foot_anchor)
        is_inside, dist = self.check_point_in_hazard(foot_anchor)
        
        return {
            "foot_anchor_image": foot_anchor,
            "ground_position_meters": ground_pos,
            "in_hazard_zone": is_inside,
            "signed_distance_px": round(dist, 2),
            "zone_id": self.zone_id
        }

    def render_overlay(self, frame: np.ndarray, is_alert_active: bool = False) -> np.ndarray:
        """
        Draws the calibrated hazard zone polygon onto the OpenCV frame
        with a semi-transparent danger overlay and dashed perimeter boundary.
        """
        overlay = frame.copy()
        
        # Dynamic color: pulsing vibrant red when violation alert is active, orange/amber when clear
        fill_color = (0, 0, 220) if is_alert_active else (0, 140, 255)
        border_color = (0, 0, 255) if is_alert_active else (0, 200, 255)
        alpha = 0.35 if is_alert_active else 0.20

        # Fill polygon with transparency
        cv2.fillPoly(overlay, [self.polygon_image], fill_color)
        cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)

        # Draw thick crisp outer boundary
        cv2.polylines(frame, [self.polygon_image], isClosed=True, color=border_color, thickness=3, lineType=cv2.LINE_AA)

        # Calculate visual centroid of polygon for text label placement
        M = cv2.moments(self.polygon_image)
        if M["m00"] != 0:
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
        else:
            cx, cy = self.polygon_image[0]

        # Draw Zone Header Label in center of polygon
        label_text = f"WARNING: {self.zone_name}" if not is_alert_active else f"BREACH DETECTED: {self.zone_id}"
        cv2.putText(
            frame,
            label_text,
            (cx - 160, cy),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            2,
            cv2.LINE_AA
        )

        return frame
