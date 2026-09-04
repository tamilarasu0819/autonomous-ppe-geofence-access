"""
Hardware Abstraction Layer (HAL) & Serial Telematics Module
Autonomous PPE Verification and Perimeter Access Control
"""

import struct
import time
import logging
from typing import Optional, Tuple

logger = logging.getLogger("TelematicsHAL")

# Protocol Constants
START_BYTE = 0xAA
STOP_BYTE = 0x55

# State Tokens
TOKEN_ALLOW = 0x01   # Barrier Unlocked / Normal
TOKEN_DENIED = 0x02  # Barrier Locked / Alarm Triggered

class CRC16CCITT:
    """
    Standard CRC-16-CCITT (Poly: 0x1021, Init: 0xFFFF) implementation.
    Used for packet integrity verification across UART communication links.
    """
    @staticmethod
    def calculate(data: bytes) -> int:
        crc = 0xFFFF
        for byte in data:
            crc ^= (byte << 8)
            for _ in range(8):
                if crc & 0x8000:
                    crc = ((crc << 1) ^ 0x1021) & 0xFFFF
                else:
                    crc = (crc << 1) & 0xFFFF
        return crc


class TelematicsController:
    """
    Hardware Abstraction Layer for Barrier Servos and Warning Buzzers.
    Handles serialization of state tokens, CRC checksum validation,
    and physical or simulated UART transmission.
    """
    def __init__(self, port: str = "COM3", baud_rate: int = 115200, mock_mode: bool = True):
        self.port = port
        self.baud_rate = baud_rate
        self.mock_mode = mock_mode
        self.serial_conn = None
        self._msg_sequence = 0
        self.current_state = TOKEN_ALLOW

        if not self.mock_mode:
            self._connect_serial()
        else:
            logger.info("Telematics Controller initialized in MOCK_MODE = True (Simulated UART @ %d baud)", self.baud_rate)

    def _connect_serial(self) -> bool:
        """Establishes connection to physical serial port."""
        try:
            import serial
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baud_rate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.1
            )
            logger.info("Physical UART connection opened on %s @ %d baud", self.port, self.baud_rate)
            return True
        except Exception as e:
            logger.error("Failed to connect to physical serial port %s: %s. Falling back to MOCK_MODE.", self.port, e)
            self.mock_mode = True
            return False

    def build_packet(self, state_token: int, timestamp: Optional[int] = None) -> bytes:
        """
        Builds the 10-byte binary telematics packet:
        [START: 0xAA (1B)]
        [MSG_ID: sequence counter (1B)]
        [STATE_TOKEN: 0x01 or 0x02 (1B)]
        [TIMESTAMP: uint32 Unix epoch seconds (4B)]
        [CRC-16: CCITT checksum over payload (2B)]
        [STOP: 0x55 (1B)]
        """
        self._msg_sequence = (self._msg_sequence + 1) & 0xFF
        msg_id = self._msg_sequence
        
        if timestamp is None:
            timestamp = int(time.time())
        
        # Pack header and payload: MSG_ID (B), STATE_TOKEN (B), TIMESTAMP (I: 4 bytes unsigned int big-endian)
        payload = struct.pack(">BBI", msg_id, state_token, timestamp)
        
        # Calculate CRC-16 over the payload
        crc = CRC16CCITT.calculate(payload)
        
        # Pack full 10-byte frame: START (B), PAYLOAD (6B), CRC (H: 2 bytes unsigned short big-endian), STOP (B)
        frame = struct.pack(">B", START_BYTE) + payload + struct.pack(">HB", crc, STOP_BYTE)
        return frame

    @staticmethod
    def verify_packet(frame: bytes) -> Tuple[bool, Optional[dict]]:
        """
        Validates incoming or recorded telematics byte frame.
        Returns (is_valid, parsed_dict).
        """
        if len(frame) != 10:
            return False, None
        
        start_byte, msg_id, state_token, timestamp, crc, stop_byte = struct.unpack(">BBBIHB", frame)
        if start_byte != START_BYTE or stop_byte != STOP_BYTE:
            return False, None
        
        payload = struct.pack(">BBI", msg_id, state_token, timestamp)
        expected_crc = CRC16CCITT.calculate(payload)
        if crc != expected_crc:
            return False, None
        
        return True, {
            "msg_id": msg_id,
            "state_token": state_token,
            "state_str": "ALLOW" if state_token == TOKEN_ALLOW else "DENIED",
            "timestamp": timestamp,
            "crc": hex(crc)
        }

    def dispatch_state(self, state_token: int) -> bytes:
        """
        Dispatches barrier/buzzer state token via physical serial or mock simulation.
        """
        self.current_state = state_token
        packet = self.build_packet(state_token)
        hex_repr = " ".join(f"0x{b:02X}" for b in packet)

        if self.mock_mode:
            # Visual console banners as required by project specifications
            if state_token == TOKEN_DENIED:
                print("\n" + "=" * 65)
                print(">>> [TELEMATICS HAL ALERT] <<<")
                print("[BARRIER: LOCKED]   - Physical servo latch activated")
                print("[BUZZER: PULSED]    - High-frequency perimeter audible alarm")
                print(f"[UART SIMULATION]  - Frame: [{hex_repr}] ({len(packet)} bytes)")
                print("=" * 65 + "\n")
            else:
                print(f"[BARRIER: UNLOCKED] - Perimeter access permitted | UART: [{hex_repr}]")
        else:
            if self.serial_conn and self.serial_conn.is_open:
                try:
                    self.serial_conn.write(packet)
                    self.serial_conn.flush()
                except Exception as e:
                    logger.error("Serial write failed: %s", e)
            else:
                logger.warning("Serial connection not open. State packet dropped.")

        return packet

    def close(self):
        """Releases serial connection gracefully."""
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
            logger.info("Serial connection closed.")
