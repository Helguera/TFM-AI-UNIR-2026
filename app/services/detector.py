"""
Person Detection Service - Based on rtsp_multi_person_detection.py
Manages camera workers for real-time person detection via RTSP streams.
"""
import cv2
import time
import threading
from pathlib import Path
from typing import Optional, Tuple, Dict, Callable
from datetime import datetime

from app.config import (
    PROTOTXT_PATH, CAFFEMODEL_PATH, EVIDENCES_DIR,
    DEFAULT_CONFIDENCE_THRESHOLD, DEFAULT_CONFIRM_FRAMES,
    DEFAULT_COOLDOWN_SECONDS, DEFAULT_TARGET_WIDTH
)

CLASSES = [
    "background", "aeroplane", "bicycle", "bird", "boat",
    "bottle", "bus", "car", "cat", "chair", "cow", "diningtable",
    "dog", "horse", "motorbike", "person", "pottedplant",
    "sheep", "sofa", "train", "tvmonitor"
]


def build_gstreamer_pipeline(rtsp_url: str, latency_ms: int = 100) -> str:
    return (
        f"rtspsrc location={rtsp_url} latency={latency_ms} ! "
        "rtph264depay ! h264parse ! avdec_h264 ! "
        "videoconvert ! appsink drop=true sync=false"
    )


def open_rtsp(rtsp_url: str) -> Tuple[cv2.VideoCapture, str]:
    """Try to open RTSP stream with FFMPEG first, then GStreamer."""
    cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
    if cap.isOpened():
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap, "FFMPEG"

    gst = build_gstreamer_pipeline(rtsp_url)
    cap = cv2.VideoCapture(gst, cv2.CAP_GSTREAMER)
    if cap.isOpened():
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap, "GSTREAMER"

    raise RuntimeError(f"Could not open RTSP stream: {rtsp_url}")


def load_detector(prototxt_path: str = PROTOTXT_PATH, model_path: str = CAFFEMODEL_PATH) -> cv2.dnn_Net:
    """Load the MobileNet SSD detector."""
    return cv2.dnn.readNetFromCaffe(prototxt_path, model_path)


def detect_persons(
    net: cv2.dnn_Net,
    frame,
    conf_thresh: float = 0.55
) -> Tuple[bool, float, Optional[Tuple[int, int, int, int]], list]:
    """
    Detect persons in frame.
    Returns: (person_found, best_confidence, best_box, all_detections)
    """
    (h, w) = frame.shape[:2]
    blob = cv2.dnn.blobFromImage(
        cv2.resize(frame, (300, 300)),
        scalefactor=0.007843,
        size=(300, 300),
        mean=127.5
    )
    net.setInput(blob)
    detections = net.forward()

    best_conf = 0.0
    best_box = None
    all_boxes = []

    for i in range(detections.shape[2]):
        confidence = float(detections[0, 0, i, 2])
        if confidence < conf_thresh:
            continue

        class_id = int(detections[0, 0, i, 1])
        if class_id >= len(CLASSES) or CLASSES[class_id] != "person":
            continue

        box = detections[0, 0, i, 3:7] * [w, h, w, h]
        (x1, y1, x2, y2) = box.astype("int")
        all_boxes.append((x1, y1, x2, y2, confidence))

        if confidence > best_conf:
            best_conf = confidence
            best_box = (x1, y1, x2, y2)

    return (best_box is not None), best_conf, best_box, all_boxes


class CameraWorker(threading.Thread):
    """
    Thread per camera: RTSP capture + detection + events.
    Does NOT use imshow/waitKey. Only updates the last processed frame.
    """
    def __init__(
        self,
        camera_id: int,
        camera_name: str,
        rtsp_url: str,
        on_alert_callback: Optional[Callable] = None,
        target_width: int = DEFAULT_TARGET_WIDTH,
        conf_thresh: float = DEFAULT_CONFIDENCE_THRESHOLD,
        confirm_frames: int = DEFAULT_CONFIRM_FRAMES,
        cooldown_s: int = DEFAULT_COOLDOWN_SECONDS,
        reconnect_wait_s: float = 2.0
    ):
        super().__init__(daemon=True)
        self.camera_id = camera_id
        self.camera_name = camera_name
        self.rtsp_url = rtsp_url
        self.target_width = target_width
        self.conf_thresh = conf_thresh
        self.confirm_frames = confirm_frames
        self.cooldown_s = cooldown_s
        self.reconnect_wait_s = reconnect_wait_s
        self.on_alert_callback = on_alert_callback

        # Output directory for this camera
        self.out_dir = EVIDENCES_DIR / f"camera_{camera_id}"
        self.out_dir.mkdir(parents=True, exist_ok=True)

        # Detection network (thread-safe - one per thread)
        self.net = load_detector()

        self.cap = None
        self.backend = "?"
        self.stop_flag = threading.Event()

        # State for detection confirmation
        self.consecutive_person_frames = 0
        self.last_alert_time = 0.0

        # FPS calculation
        self.fps = 0.0
        self.prev_time = time.time()

        # Shared frame (only the last one)
        self._lock = threading.Lock()
        self._last_frame = None
        self._last_raw_frame = None  # Without overlays
        self._status = "INITIALIZING"
        self._error = None

    def stop(self):
        self.stop_flag.set()

    def get_status(self) -> dict:
        with self._lock:
            return {
                "camera_id": self.camera_id,
                "camera_name": self.camera_name,
                "status": self._status,
                "fps": round(self.fps, 1),
                "backend": self.backend,
                "error": self._error,
                "consecutive_detections": self.consecutive_person_frames,
                "cooldown_remaining": max(0, int(self.cooldown_s - (time.time() - self.last_alert_time)))
            }

    def get_last_frame(self) -> Optional[bytes]:
        """Get last processed frame as JPEG bytes."""
        with self._lock:
            if self._last_frame is None:
                return None
            _, buffer = cv2.imencode('.jpg', self._last_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            return buffer.tobytes()

    def get_last_frame_raw(self):
        """Get last raw frame (numpy array)."""
        with self._lock:
            if self._last_raw_frame is None:
                return None
            return self._last_raw_frame.copy()

    def _set_last_frame(self, frame, raw_frame=None):
        with self._lock:
            self._last_frame = frame
            self._last_raw_frame = raw_frame if raw_frame is not None else frame

    def _set_status(self, status: str, error: str = None):
        with self._lock:
            self._status = status
            self._error = error

    def _connect(self):
        self._set_status("CONNECTING")
        self.cap, self.backend = open_rtsp(self.rtsp_url)
        self._set_status("RUNNING")
        print(f"[Camera {self.camera_id}] Connected via {self.backend}")

    def _reconnect(self, reason: str):
        try:
            if self.cap is not None:
                self.cap.release()
        except Exception:
            pass
        self.cap = None
        self._set_status("RECONNECTING", reason)
        print(f"[Camera {self.camera_id}] Reconnecting in {self.reconnect_wait_s}s. Reason: {reason}")
        time.sleep(self.reconnect_wait_s)

    def _save_alert_image(self, frame) -> str:
        """Save alert image and return path."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        img_file = self.out_dir / f"intrusion_{ts}.jpg"
        cv2.imwrite(str(img_file), frame)
        return str(img_file)

    def run(self):
        while not self.stop_flag.is_set():
            if self.cap is None or not self.cap.isOpened():
                try:
                    self._connect()
                except Exception as e:
                    self._reconnect(str(e))
                    continue

            ok, frame = self.cap.read()
            if not ok or frame is None:
                self._reconnect("Invalid frame / stream loss")
                continue

            raw_frame = frame.copy()

            # Resize for performance
            h, w = frame.shape[:2]
            if self.target_width and w != self.target_width:
                scale = self.target_width / float(w)
                frame = cv2.resize(frame, (self.target_width, int(h * scale)), interpolation=cv2.INTER_AREA)
                raw_frame = frame.copy()

            # Detection
            person_found, best_conf, best_box, all_boxes = detect_persons(
                self.net, frame, conf_thresh=self.conf_thresh
            )
            
            if person_found:
                self.consecutive_person_frames += 1
            else:
                self.consecutive_person_frames = 0

            # Event handling
            now = time.time()
            in_cooldown = (now - self.last_alert_time) < self.cooldown_s

            if self.consecutive_person_frames >= self.confirm_frames and not in_cooldown:
                # Save image and trigger alert
                image_path = self._save_alert_image(raw_frame)
                detail = f"Person detected conf={best_conf:.2f} confirm_frames={self.consecutive_person_frames}"
                
                print(f"[Camera {self.camera_id}] ALERT: Intrusion detected - {image_path}")
                
                # Call the alert callback if provided
                if self.on_alert_callback:
                    self.on_alert_callback(
                        camera_id=self.camera_id,
                        event_type="INTRUSION",
                        confidence=best_conf,
                        detail=detail,
                        image_path=image_path
                    )

                self.last_alert_time = now
                self.consecutive_person_frames = 0

            # FPS calculation
            dt = now - self.prev_time
            self.prev_time = now
            if dt > 0:
                instant_fps = 1.0 / dt
                self.fps = 0.9 * self.fps + 0.1 * instant_fps

            # Draw overlays
            for (x1, y1, x2, y2, conf) in all_boxes:
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(frame, f"person {conf:.2f}", (x1, max(20, y1 - 10)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2, cv2.LINE_AA)

            status_text = "PERSON DETECTED" if person_found else "MONITORING"
            cooldown_left = max(0, int(self.cooldown_s - (now - self.last_alert_time)))
            status_color = (0, 0, 255) if person_found else (0, 255, 0)

            cv2.putText(frame, f"{self.camera_name} | {status_text} | FPS: {self.fps:.1f}",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, status_color, 2, cv2.LINE_AA)
            cv2.putText(frame, f"Confirm: {self.consecutive_person_frames}/{self.confirm_frames} | Cooldown: {cooldown_left}s",
                        (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA)

            self._set_last_frame(frame, raw_frame)

        # Cleanup
        try:
            if self.cap is not None:
                self.cap.release()
        except Exception:
            pass
        self._set_status("STOPPED")


class DetectionManager:
    """
    Singleton manager for all camera workers.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._workers: Dict[int, CameraWorker] = {}
        self._alert_callback: Optional[Callable] = None
        EVIDENCES_DIR.mkdir(parents=True, exist_ok=True)
        self._initialized = True

    def set_alert_callback(self, callback: Callable):
        """Set the callback function for alerts."""
        self._alert_callback = callback

    def start_camera(
        self,
        camera_id: int,
        camera_name: str,
        rtsp_url: str,
        conf_thresh: float = DEFAULT_CONFIDENCE_THRESHOLD,
        confirm_frames: int = DEFAULT_CONFIRM_FRAMES,
        cooldown_s: int = DEFAULT_COOLDOWN_SECONDS
    ) -> bool:
        """Start detection for a camera."""
        if camera_id in self._workers:
            # Already running
            return True

        try:
            worker = CameraWorker(
                camera_id=camera_id,
                camera_name=camera_name,
                rtsp_url=rtsp_url,
                on_alert_callback=self._alert_callback,
                conf_thresh=conf_thresh,
                confirm_frames=confirm_frames,
                cooldown_s=cooldown_s
            )
            worker.start()
            self._workers[camera_id] = worker
            return True
        except Exception as e:
            print(f"Error starting camera {camera_id}: {e}")
            return False

    def stop_camera(self, camera_id: int) -> bool:
        """Stop detection for a camera."""
        if camera_id not in self._workers:
            return True

        worker = self._workers.pop(camera_id)
        worker.stop()
        worker.join(timeout=3.0)
        return True

    def get_camera_status(self, camera_id: int) -> Optional[dict]:
        """Get status of a specific camera."""
        worker = self._workers.get(camera_id)
        if worker:
            return worker.get_status()
        return None

    def get_all_statuses(self) -> Dict[int, dict]:
        """Get status of all running cameras."""
        return {cam_id: w.get_status() for cam_id, w in self._workers.items()}

    def get_frame(self, camera_id: int) -> Optional[bytes]:
        """Get the last frame from a camera as JPEG bytes."""
        worker = self._workers.get(camera_id)
        if worker:
            return worker.get_last_frame()
        return None

    def is_running(self, camera_id: int) -> bool:
        """Check if a camera is running."""
        return camera_id in self._workers

    def stop_all(self):
        """Stop all cameras."""
        for camera_id in list(self._workers.keys()):
            self.stop_camera(camera_id)


# Global instance
detection_manager = DetectionManager()

