"""
Camera Abstraction Layer with Threaded Capture & Auto-Reconnection
Autonomous PPE Verification and Perimeter Access Control
"""

import cv2
import time
import logging
import threading
import numpy as np
from typing import Union, Tuple, Optional

logger = logging.getLogger("CameraCapture")


class VideoStream:
    """
    High-performance camera reader supporting:
    - Built-in webcam index (e.g. 0)
    - External USB cameras (e.g. 1, 2)
    - IP/RTSP streams ("rtsp://...")
    - Video files ("path/to/video.mp4")
    - Synthetic fallback frame generator for test environments without physical webcams.
    """
    def __init__(
        self,
        source: Union[int, str] = 0,
        width: int = 1280,
        height: int = 720,
        fps: int = 30,
        reconnect_timeout_sec: float = 5.0,
        max_reconnect_attempts: int = 10,
        buffer_size: int = 1
    ):
        self.source = source
        self.target_width = width
        self.target_height = height
        self.target_fps = fps
        self.reconnect_timeout = reconnect_timeout_sec
        self.max_reconnect_attempts = max_reconnect_attempts
        self.buffer_size = buffer_size

        self.cap: Optional[cv2.VideoCapture] = None
        self.grabbed: bool = False
        self.frame: Optional[np.ndarray] = None
        self.stopped: bool = False
        self.lock = threading.Lock()
        self.thread: Optional[threading.Thread] = None
        self.use_synthetic_fallback: bool = False
        self._synthetic_counter: int = 0

        self._init_capture()

    def _init_capture(self) -> bool:
        """Initializes VideoCapture backend."""
        logger.info("Initializing VideoStream from source: %s", self.source)
        try:
            # On Windows, cv2.CAP_DSHOW can significantly reduce webcam startup time
            if isinstance(self.source, int):
                self.cap = cv2.VideoCapture(self.source, cv2.CAP_DSHOW)
            else:
                self.cap = cv2.VideoCapture(self.source)

            if not self.cap or not self.cap.isOpened():
                logger.warning("Could not open source %s. Will attempt retry or synthetic fallback.", self.source)
                return False

            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.target_width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.target_height)
            self.cap.set(cv2.CAP_PROP_FPS, self.target_fps)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, self.buffer_size)

            ret, frame = self.cap.read()
            if ret and frame is not None:
                self.frame = frame
                self.grabbed = True
                logger.info("Successfully opened stream (%dx%d)", frame.shape[1], frame.shape[0])
                return True
            else:
                logger.warning("VideoCapture initialized but failed initial frame grab.")
                return False
        except Exception as e:
            logger.error("Exception during VideoCapture init: %s", e)
            return False

    def start(self) -> "VideoStream":
        """Starts the dedicated background reader thread."""
        if not self.grabbed:
            success = self._attempt_reconnect()
            if not success:
                logger.warning("Activating synthetic test frame fallback generator.")
                self.use_synthetic_fallback = True
                self.grabbed = True
                self.frame = self._generate_synthetic_frame()

        self.stopped = False
        self.thread = threading.Thread(target=self._update, daemon=True, name="VideoStreamThread")
        self.thread.start()
        return self

    def _update(self):
        """Continuous frame polling loop running in dedicated thread."""
        while not self.stopped:
            if self.use_synthetic_fallback:
                time.sleep(1.0 / self.target_fps)
                with self.lock:
                    self.frame = self._generate_synthetic_frame()
                    self.grabbed = True
                continue

            if self.cap is None or not self.cap.isOpened():
                logger.warning("Camera disconnected. Initiating reconnection routine...")
                reconnected = self._attempt_reconnect()
                if not reconnected:
                    logger.warning("Stream unavailable. Falling back to synthetic feed.")
                    self.use_synthetic_fallback = True
                    continue

            ret, frame = self.cap.read()
            if ret and frame is not None:
                with self.lock:
                    self.frame = frame
                    self.grabbed = True
            else:
                # Frame drop or stream freeze
                with self.lock:
                    self.grabbed = False
                time.sleep(0.01)

    def _attempt_reconnect(self) -> bool:
        """Handles camera reconnection with retry count."""
        attempts = 0
        while attempts < self.max_reconnect_attempts and not self.stopped:
            attempts += 1
            logger.info("Reconnection attempt %d/%d...", attempts, self.max_reconnect_attempts)
            if self.cap is not None:
                self.cap.release()
                self.cap = None

            time.sleep(self.reconnect_timeout / self.max_reconnect_attempts)
            if self._init_capture():
                logger.info("Reconnected to video source successfully.")
                return True

        return False

    def _generate_synthetic_frame(self) -> np.ndarray:
        """
        Generates an animated test card frame with timestamp, simulation worker,
        and perimeter guides when physical camera hardware is absent.
        """
        self._synthetic_counter += 1
        frame = np.zeros((self.target_height, self.target_width, 3), dtype=np.uint8)
        frame[:] = (35, 30, 30)  # Dark industrial background

        # Grid lines
        for y in range(0, self.target_height, 60):
            cv2.line(frame, (0, y), (self.target_width, y), (45, 45, 45), 1)
        for x in range(0, self.target_width, 60):
            cv2.line(frame, (x, 0), (x, self.target_height), (45, 45, 45), 1)

        # Simulation watermark banner
        cv2.putText(
            frame,
            f"SYNTHETIC CAMERA FEED [OFFLINE DEMO MODE] - {time.strftime('%H:%M:%S')}",
            (30, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 200, 255),
            2
        )

        # Draw a simulated worker walking across the frame
        cycle = (self._synthetic_counter % 300) / 300.0
        # Simulated worker moves from x=250 to x=950
        sim_x = int(250 + cycle * 700)
        sim_y = int(350 + (cycle * 200))
        h, w = 240, 80

        # Person bounding box representation
        cv2.rectangle(frame, (sim_x - w // 2, sim_y - h), (sim_x + w // 2, sim_y), (100, 200, 100), 2)
        cv2.putText(
            frame,
            "SIM_PERSON_01",
            (sim_x - w // 2, sim_y - h - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (100, 255, 100),
            1
        )
        return frame

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Returns the latest captured frame thread-safely."""
        with self.lock:
            if not self.grabbed or self.frame is None:
                return False, None
            return True, self.frame.copy()

    def stop(self):
        """Signals reader thread to exit and releases camera."""
        self.stopped = True
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        logger.info("VideoStream stopped cleanly.")
