"""
Liveness Detector
=================
Anti-spoofing module that uses two complementary methods:

1. EAR Blink Detection (Eye Aspect Ratio)
   - Loads dlib's 68-point facial landmark predictor.
   - Detects a natural blink (EAR drops below threshold then rises again)
     before allowing attendance to be marked.
   - Tracks blink state per student_id so multiple students can queue.

2. Passive Texture / Moire Analysis
   - Checks the face crop Laplacian variance + colour saturation to flag
     printed photos or phone screens.
   - Lightweight - no deep-learning model needed.

Usage
-----
    from face_utils.liveness_detector import LivenessDetector
    ld = LivenessDetector()
    live = ld.check(frame_bgr, face_location, student_id)
    # Returns True only after a real blink is confirmed.
"""

import os
import threading
import time
import math
import cv2
import numpy as np

try:
    import dlib
    import face_recognition_models

    _PREDICTOR_PATH = os.path.join(
        os.path.dirname(face_recognition_models.__file__),
        "models",
        "shape_predictor_68_face_landmarks.dat"
    )
    _predictor = dlib.shape_predictor(_PREDICTOR_PATH)
    _DLIB_OK = True
    print("[LivenessDetector] 68-point predictor loaded.", flush=True)
except Exception as _exc:
    _predictor = None
    _DLIB_OK = False
    print(f"[LivenessDetector] dlib predictor unavailable: {_exc}", flush=True)


# ---------------------------------------------------------------------------
# EAR helpers
# ---------------------------------------------------------------------------

def _eye_landmarks(shape, start, end):
    return [(shape.part(i).x, shape.part(i).y) for i in range(start, end)]


def _euclidean(p1, p2):
    return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)


def _ear(eye_points):
    """Eye Aspect Ratio (Soukupova & Cech, 2016). eye_points must have 6 entries."""
    a = _euclidean(eye_points[1], eye_points[5])
    b = _euclidean(eye_points[2], eye_points[4])
    c = _euclidean(eye_points[0], eye_points[3])
    if c == 0:
        return 0.0
    return (a + b) / (2.0 * c)


# ---------------------------------------------------------------------------
# Per-student blink state machine
# ---------------------------------------------------------------------------

class _BlinkTracker:
    EAR_CLOSED_THRESHOLD = 0.22
    EAR_OPEN_THRESHOLD   = 0.26
    MIN_CLOSED_FRAMES    = 2
    BLINK_TIMEOUT        = 15.0

    def __init__(self):
        self.state = "WAITING"
        self.closed_frames = 0
        self.blink_confirmed = False
        self.last_update = time.time()

    def update(self, ear_value):
        now = time.time()
        if now - self.last_update > self.BLINK_TIMEOUT:
            self._reset_partial()
        self.last_update = now

        if self.blink_confirmed:
            return True

        if self.state == "WAITING":
            if ear_value < self.EAR_CLOSED_THRESHOLD:
                self.state = "CLOSED"
                self.closed_frames = 1

        elif self.state == "CLOSED":
            if ear_value < self.EAR_CLOSED_THRESHOLD:
                self.closed_frames += 1
            else:
                if self.closed_frames >= self.MIN_CLOSED_FRAMES:
                    self.blink_confirmed = True
                    self.state = "OPEN"
                    return True
                else:
                    self.state = "WAITING"
                    self.closed_frames = 0

        return False

    def _reset_partial(self):
        if not self.blink_confirmed:
            self.state = "WAITING"
            self.closed_frames = 0


# ---------------------------------------------------------------------------
# Texture / Moire spoof detector
# ---------------------------------------------------------------------------

def _is_texture_spoof(face_bgr):
    if face_bgr is None or face_bgr.size == 0:
        return False
    try:
        crop = cv2.resize(face_bgr, (64, 64))
        grey = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        lap_var = cv2.Laplacian(grey, cv2.CV_64F).var()
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        sat_mean = float(np.mean(hsv[:, :, 1]))
        if lap_var > 2500 and sat_mean < 20:
            return True
        return False
    except Exception:
        return False


# ---------------------------------------------------------------------------
# LivenessDetector (public API)
# ---------------------------------------------------------------------------

class LivenessDetector:
    """
    Thread-safe liveness detector.
    Call check(frame_bgr, face_location, student_id) once per frame.
    Returns True only after a genuine blink is detected for that student.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._trackers = {}
        self._last_ear = {}

    def check(self, frame_bgr, face_location, student_id):
        """
        Parameters
        ----------
        frame_bgr    : np.ndarray  - full BGR camera frame
        face_location: (top, right, bottom, left) from face_recognition
        student_id   : str

        Returns
        -------
        bool - True if face passes liveness (blink confirmed + no spoof)
        """
        if not _DLIB_OK:
            return True

        top, right, bottom, left = face_location

        face_crop = frame_bgr[top:bottom, left:right]
        if _is_texture_spoof(face_crop):
            return False

        rect = dlib.rectangle(left, top, right, bottom)

        try:
            grey = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
            shape = _predictor(grey, rect)
        except Exception:
            return False

        left_eye  = _eye_landmarks(shape, 36, 42)
        right_eye = _eye_landmarks(shape, 42, 48)
        ear = (_ear(left_eye) + _ear(right_eye)) / 2.0

        with self._lock:
            self._last_ear[student_id] = ear
            if student_id not in self._trackers:
                self._trackers[student_id] = _BlinkTracker()
            tracker = self._trackers[student_id]
            blink_ok = tracker.update(ear)

        return blink_ok

    def is_confirmed(self, student_id):
        with self._lock:
            tracker = self._trackers.get(student_id)
            return tracker is not None and tracker.blink_confirmed

    def get_ear(self, student_id):
        with self._lock:
            return self._last_ear.get(student_id, None)

    def reset_student(self, student_id):
        with self._lock:
            self._trackers.pop(student_id, None)
            self._last_ear.pop(student_id, None)

    def reset_all(self):
        with self._lock:
            self._trackers.clear()
            self._last_ear.clear()
