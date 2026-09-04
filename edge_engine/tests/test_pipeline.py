"""
Unit tests for Edge Engine: Telematics HAL, Homography Geofencing & Detector Logic
"""

import sys
import os
import unittest
import numpy as np

# Ensure edge_engine directory is in Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from telematics import TelematicsController, CRC16CCITT, TOKEN_ALLOW, TOKEN_DENIED, START_BYTE, STOP_BYTE
from geofence import SpatialGeofence
from detector import PPEDetector


class TestTelematicsHAL(unittest.TestCase):
    def setUp(self):
        self.hal = TelematicsController(mock_mode=True)

    def test_packet_structure_and_length(self):
        packet = self.hal.build_packet(TOKEN_DENIED, timestamp=1700000000)
        self.assertEqual(len(packet), 10, "Telematics byte frame must be exactly 10 bytes")
        self.assertEqual(packet[0], START_BYTE, "Packet must begin with 0xAA")
        self.assertEqual(packet[-1], STOP_BYTE, "Packet must end with 0x55")

    def test_crc16_integrity_and_verification(self):
        packet = self.hal.build_packet(TOKEN_DENIED, timestamp=1700000000)
        is_valid, parsed = TelematicsController.verify_packet(packet)
        self.assertTrue(is_valid, "Valid telematics frame should pass CRC-16 verification")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["state_token"], TOKEN_DENIED)
        self.assertEqual(parsed["state_str"], "DENIED")

        # Corrupt one bit in payload
        corrupted_packet = bytearray(packet)
        corrupted_packet[2] ^= 0xFF
        is_valid_corrupt, _ = TelematicsController.verify_packet(bytes(corrupted_packet))
        self.assertFalse(is_valid_corrupt, "Corrupted frame must fail CRC verification")

    def test_mock_dispatch(self):
        packet = self.hal.dispatch_state(TOKEN_DENIED)
        self.assertEqual(len(packet), 10)
        self.assertEqual(self.hal.current_state, TOKEN_DENIED)


class TestGeofenceMath(unittest.TestCase):
    def setUp(self):
        # 4 image calibration points and 4 ground plane metric points (5m x 8m)
        img_pts = [[200, 650], [1080, 650], [850, 320], [430, 320]]
        ground_pts = [[0.0, 0.0], [5.0, 0.0], [5.0, 8.0], [0.0, 8.0]]
        # Hazard zone polygon in image coordinates
        hazard_poly = [[350, 680], [930, 680], [780, 380], [500, 380]]

        self.geofence = SpatialGeofence(
            image_calibration_points=img_pts,
            ground_calibration_points=ground_pts,
            hazard_polygon_image=hazard_poly,
            zone_id="TEST_ZONE"
        )

    def test_foot_anchor_calculation(self):
        bbox = (100, 200, 300, 600)  # x1=100, y1=200, x2=300, y2=600
        anchor = SpatialGeofence.get_foot_anchor(bbox)
        # x_mid = (100+300)/2 = 200.0, y_max = 600.0
        self.assertEqual(anchor, (200.0, 600.0))

    def test_homography_projection(self):
        # Project corner image calibration point [200, 650] -> should map near [0.0, 0.0]
        ground_coord = self.geofence.project_point_to_ground((200.0, 650.0))
        self.assertAlmostEqual(ground_coord[0], 0.0, places=1)
        self.assertAlmostEqual(ground_coord[1], 0.0, places=1)

    def test_point_in_hazard_polygon(self):
        # Point inside hazard polygon (e.g. centroid near x=640, y=530)
        inside, dist = self.geofence.check_point_in_hazard((640.0, 530.0))
        self.assertTrue(inside, "Point (640, 530) should be inside the hazard polygon")
        self.assertGreater(dist, 0.0)

        # Point far outside hazard polygon (e.g. x=50, y=100)
        outside, dist_out = self.geofence.check_point_in_hazard((50.0, 100.0))
        self.assertFalse(outside, "Point (50, 100) should be outside the hazard polygon")
        self.assertLess(dist_out, 0.0)


class TestPPEDetector(unittest.TestCase):
    def test_upper_body_containment(self):
        person_bbox = (100, 100, 300, 500)  # width=200, height=400, top 35% is y in [100, 240]
        
        # Helmet correctly positioned on head: center at (200, 140)
        helmet_good = (160, 110, 240, 170)
        is_worn = PPEDetector.is_contained_in_upper_body(helmet_good, person_bbox)
        self.assertTrue(is_worn, "Helmet on head should pass containment check")

        # Helmet dropped on the ground: center at (200, 480)
        helmet_bad = (160, 460, 240, 500)
        is_worn_bad = PPEDetector.is_contained_in_upper_body(helmet_bad, person_bbox)
        self.assertFalse(is_worn_bad, "Helmet at feet should fail upper body containment check")


if __name__ == "__main__":
    unittest.main()
