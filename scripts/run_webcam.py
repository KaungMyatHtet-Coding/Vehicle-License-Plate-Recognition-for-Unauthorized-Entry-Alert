"""Day 18 local OpenCV webcam demonstration runner.

Isolates all camera interaction in a single standalone CLI script.
The backend server startup never imports or requires this module.

This script calls the FastAPI backend HTTP API (localhost:8000) for each
frame — this ensures the webcam shares the same authorized-vehicle store
as the web UI.

Requires the backend server to be running:
    uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

Usage:
    python scripts/run_webcam.py --help
    python scripts/run_webcam.py --camera 0
    python scripts/run_webcam.py --camera 0 --fps 2 --cooldown 3.0
    python scripts/run_webcam.py --camera 0 --api-url http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from typing import Sequence

import cv2
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [WebcamDemo] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


class CameraUnavailableError(RuntimeError):
    """Raised when the requested camera index cannot be opened."""


class ServerUnavailableError(RuntimeError):
    """Raised when the backend API server cannot be reached."""


class WebcamRunner:
    """Local webcam demonstration runner that calls the FastAPI backend API.

    By routing each frame through the HTTP API, this runner shares the same
    authorized-vehicle store as the web UI — vehicles added via the browser
    are immediately visible here without any restart.
    """

    def __init__(
        self,
        camera_index: int = 0,
        target_fps: float = 2.0,
        cooldown_seconds: float = 3.0,
        api_base_url: str = "http://127.0.0.1:8000",
    ) -> None:
        self._camera_index = camera_index
        self._target_fps = target_fps
        self._cooldown_seconds = cooldown_seconds
        self._api_base_url = api_base_url.rstrip("/")
        self._analyze_url = f"{self._api_base_url}/api/recognition/analyze"
        self._last_seen_times: dict[str, float] = {}

    def _check_server(self) -> None:
        """Verify the backend API server is reachable before starting the loop."""
        health_url = f"{self._api_base_url}/health"
        try:
            resp = requests.get(health_url, timeout=5)
            resp.raise_for_status()
            logger.info("Backend server healthy at %s", self._api_base_url)
        except requests.RequestException as exc:
            raise ServerUnavailableError(
                f"Cannot reach backend at {self._api_base_url}/health — "
                "make sure the FastAPI server is running:\n"
                "  cd backend && .venv\\Scripts\\python.exe -m uvicorn app.main:app "
                "--reload --host 127.0.0.1 --port 8000"
            ) from exc

    def _recognize_frame(self, frame_bytes: bytes) -> dict | None:
        """POST one JPEG frame to the backend analyze endpoint and return JSON."""
        try:
            resp = requests.post(
                self._analyze_url,
                files={"file": ("frame.jpg", frame_bytes, "image/jpeg")},
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            logger.warning("API call failed: %s", exc)
            return None

    def _is_suppressed(self, plate: str, timestamp: float) -> bool:
        last = self._last_seen_times.get(plate)
        if last is not None and (timestamp - last) < self._cooldown_seconds:
            return True
        self._last_seen_times[plate] = timestamp
        return False

    def _draw_overlay(
        self,
        frame,  # type: ignore[no-untyped-def]
        plate: str | None,
        decision: str | None,
        suppressed: bool,
        fps: float,
        latency_ms: float,
    ):
        """Draw recognition result and performance overlay onto the frame."""
        h, w = frame.shape[:2]

        # FPS and latency top-left
        cv2.putText(
            frame,
            f"FPS: {fps:.1f}  Latency: {latency_ms:.0f}ms",
            (10, 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 255),
            2,
        )

        if plate:
            color = (0, 255, 0) if decision == "AUTHORIZED" else (0, 0, 255)
            if decision == "MANUAL_REVIEW":
                color = (0, 165, 255)  # orange
            label = plate if not suppressed else f"{plate} (dup)"
            decision_text = decision or "MANUAL_REVIEW"
            if suppressed:
                decision_text += " [suppressed]"

            cv2.rectangle(frame, (10, h - 70), (w - 10, h - 10), (0, 0, 0), -1)
            cv2.putText(
                frame,
                f"Plate: {label}",
                (15, h - 47),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                color,
                2,
            )
            cv2.putText(
                frame,
                f"Decision: {decision_text}",
                (15, h - 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                color,
                2,
            )
        else:
            cv2.putText(
                frame,
                "No plate detected",
                (10, h - 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (128, 128, 128),
                2,
            )

        return frame

    def open_camera(self) -> cv2.VideoCapture:
        """Open camera and raise CameraUnavailableError if it cannot be accessed."""
        cap = cv2.VideoCapture(self._camera_index)
        if not cap.isOpened():
            raise CameraUnavailableError(
                f"Camera index {self._camera_index} is unavailable or not connected. "
                "Ensure a physical camera is attached and no other application is using it."
            )
        return cap

    def run(self) -> int:
        """Run the webcam demo loop. Returns exit code 0 (success) or 1 (error)."""
        logger.info(
            "Starting local webcam demo — camera=%d target_fps=%.1f cooldown=%.1fs api=%s",
            self._camera_index,
            self._target_fps,
            self._cooldown_seconds,
            self._api_base_url,
        )
        logger.info("Press 'Q' or Ctrl+C to stop.")

        # Verify backend is running before opening camera
        try:
            self._check_server()
        except ServerUnavailableError as exc:
            logger.error("Backend unavailable: %s", exc)
            return 1

        try:
            cap = self.open_camera()
        except CameraUnavailableError as exc:
            logger.error("Camera unavailable: %s", exc)
            logger.info(
                "NOTE: The backend API server does not require a camera to start."
            )
            return 1

        frame_interval = 1.0 / self._target_fps
        last_sample_time = 0.0
        display_plate: str | None = None
        display_decision: str | None = None
        display_suppressed = False
        measured_fps = 0.0
        latency_ms = 0.0
        loop_times: list[float] = []

        try:
            while True:
                loop_start = time.perf_counter()
                ret, frame = cap.read()
                if not ret or frame is None:
                    logger.warning("Failed to read frame from camera. Retrying...")
                    time.sleep(0.05)
                    continue

                now = time.perf_counter()

                # Sample frame at target FPS for recognition
                if now - last_sample_time >= frame_interval:
                    last_sample_time = now
                    t0 = time.perf_counter()

                    ok, encoded = cv2.imencode(".jpg", frame)
                    if ok:
                        frame_bytes = encoded.tobytes()
                        result = self._recognize_frame(frame_bytes)
                        latency_ms = (time.perf_counter() - t0) * 1000

                        if result and result.get("status") == "completed":
                            ocr = result.get("ocr")
                            logging_result = result.get("logging")
                            plate = ocr.get("normalized_text") if ocr else None
                            decision = None
                            if logging_result:
                                decision = logging_result.get("decision", {}).get(
                                    "decision"
                                )

                            if plate:
                                suppressed = self._is_suppressed(plate, now)
                                display_plate = plate
                                display_decision = decision
                                display_suppressed = suppressed

                                if not suppressed:
                                    logger.info(
                                        "Plate=%s Decision=%s Latency=%.1fms",
                                        plate,
                                        decision,
                                        latency_ms,
                                    )
                            else:
                                display_plate = None
                                display_decision = None
                                display_suppressed = False
                        elif result and result.get("status") == "no_plate_detected":
                            display_plate = None
                            display_decision = None
                            display_suppressed = False

                # Track FPS
                loop_elapsed = time.perf_counter() - loop_start
                loop_times.append(loop_elapsed)
                if len(loop_times) > 30:
                    loop_times.pop(0)
                avg_loop = sum(loop_times) / len(loop_times)
                measured_fps = 1.0 / avg_loop if avg_loop > 0 else 0.0

                # Draw overlay
                frame = self._draw_overlay(
                    frame,
                    display_plate,
                    display_decision,
                    display_suppressed,
                    measured_fps,
                    latency_ms,
                )

                cv2.imshow("CVPX — Webcam Demo (Press Q to quit)", frame)

                # Check for quit
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), ord("Q"), 27):  # Q or Escape
                    logger.info("Stop signal received. Shutting down.")
                    break

        except KeyboardInterrupt:
            logger.info("Interrupted by user. Shutting down.")

        finally:
            cap.release()
            cv2.destroyAllWindows()
            logger.info("Webcam demo stopped cleanly.")

        return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="run_webcam.py",
        description=(
            "CVPX Local Webcam Demo — runs OpenCV-based license plate recognition "
            "on a local camera via the FastAPI backend HTTP API. "
            "The backend server MUST be running before starting this script."
        ),
    )
    parser.add_argument(
        "--camera",
        type=int,
        default=0,
        metavar="INDEX",
        help="Camera index to use (default: 0). Pass -1 to test camera-unavailable handling.",
    )
    parser.add_argument(
        "--fps",
        type=float,
        default=2.0,
        metavar="FPS",
        help="Target frames per second to sample for recognition (default: 2.0).",
    )
    parser.add_argument(
        "--cooldown",
        type=float,
        default=3.0,
        metavar="SECONDS",
        help="Duplicate suppression cooldown in seconds (default: 3.0).",
    )
    parser.add_argument(
        "--api-url",
        type=str,
        default="http://127.0.0.1:8000",
        metavar="URL",
        help="Backend API base URL (default: http://127.0.0.1:8000).",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    runner = WebcamRunner(
        camera_index=args.camera,
        target_fps=args.fps,
        cooldown_seconds=args.cooldown,
        api_base_url=args.api_url,
    )
    return runner.run()


if __name__ == "__main__":
    sys.exit(main())
