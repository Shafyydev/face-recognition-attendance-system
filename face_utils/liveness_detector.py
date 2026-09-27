"""
Liveness Detector  —  Passive Motion Anti-Spoofing
===================================================
Detects whether a face is LIVE by measuring natural micro-motion across
consecutive frames.

A real human face always shows subtle natural movement — breathing,
tiny head sway, muscle micro-tremors. A printed photo or phone screen
held still is perfectly static.

Method
------
For each recognised student, we accumulate face crops across N_FRAMES
consecutive frames. We then compute the standard deviation of per-pixel
intensity differences between successive frames (mean absolute diff / MAD).

  - Static source (photo, screen) : MAD ≈ 0–0.8   → SPOOF
  - Live face                     : MAD > threshold → LIVE

No user action is required. Works with glasses. Works at low resolution.
Requires no dlib landmark model.

Technique reference: "Face Liveness Detection From a Single Image via
Micro-texture Analysis" (Pan et al.) — simplified passive variant.
"""

import threading
import time
import cv2
import numpy as np


# ---------------------------------------------------------------------------
# Per-student motion tracker
# ---------------------------------------------------------------------------

class _MotionTracker:
    """
    Collects face crop pairs and accumulates motion energy.

    Once enough motion has been observed (above LIVE_MAD_THRESHOLD
    for REQUIRED_LIVE_FRAMES out of WINDOW_FRAMES), the face is
    flagged as live.
    """

    WINDOW_FRAMES        = 20    # rolling window of frame-diffs to analyse
    REQUIRED_LIVE_FRAMES = 5     # how many diffs must exceed the threshold
    LIVE_MAD_THRESHOLD   = 1.2   # mean-abs-diff score to count as "motion"
    CROP_SIZE            = (48, 48)  # normalise crops before diff
    TIMEOUT              = 15.0  # reset if no face seen for this long

    def __init__(self):
        self._prev_crop   = None   # previous greyscale face crop
        self._diffs       = []     # rolling list of MAD scores
        self.live_confirmed = False
        self.last_update  = time.time()

    # ------------------------------------------------------------------

    def update(self, face_bgr):
        """
        Feed a new face crop. Returns True when liveness is confirmed.

        Parameters
        ----------
        face_bgr : np.ndarray — BGR face crop (any size, will be resized)
        """
        if self.live_confirmed:
            return True

        now = time.time()
        if now - self.last_update > self.TIMEOUT:
            self._reset()
        self.last_update = now

        if face_bgr is None or face_bgr.size == 0:
            return False

        try:
            # Normalise crop size and convert to greyscale
            grey = cv2.cvtColor(
                cv2.resize(face_bgr, self.CROP_SIZE),
                cv2.COLOR_BGR2GRAY
            ).astype(np.float32)
        except Exception:
            return False

        if self._prev_crop is None:
            self._prev_crop = grey
            return False

        # Compute Mean Absolute Difference between successive crops
        mad = float(np.mean(np.abs(grey - self._prev_crop)))
        self._prev_crop = grey

        self._diffs.append(mad)
        if len(self._diffs) > self.WINDOW_FRAMES:
            self._diffs.pop(0)

        # Count how many recent diffs show real motion
        live_count = sum(
            1 for d in self._diffs if d > self.LIVE_MAD_THRESHOLD
        )

        if len(self._diffs) >= self.WINDOW_FRAMES and live_count >= self.REQUIRED_LIVE_FRAMES:
            self.live_confirmed = True
            print(
                f"[LivenessDetector] LIVE confirmed — "
                f"motion frames={live_count}/{self.WINDOW_FRAMES} "
                f"avg_mad={sum(self._diffs)/len(self._diffs):.2f}",
                flush=True
            )
            return True

        return False

    def progress(self):
        """
        Return a 0.0–1.0 progress value for UI feedback while waiting.
        """
        if self.live_confirmed:
            return 1.0
        if not self._diffs:
            return 0.0
        live_count = sum(
            1 for d in self._diffs if d > self.LIVE_MAD_THRESHOLD
        )
        return min(1.0, live_count / self.REQUIRED_LIVE_FRAMES)

    def _reset(self):
        self._prev_crop = None
        self._diffs = []
        self.live_confirmed = False


# ---------------------------------------------------------------------------
# Passive texture / screen detector  (secondary check — kept from v1)
# ---------------------------------------------------------------------------

def _is_texture_spoof(face_bgr):
    """
    Quick heuristic: very high sharpness + near-zero colour saturation
    suggests a greyscale printout or screen capture.
    """
    if face_bgr is None or face_bgr.size == 0:
        return False
    try:
        crop = cv2.resize(face_bgr, (64, 64))
        grey = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        lap_var = cv2.Laplacian(grey, cv2.CV_64F).var()
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        sat_mean = float(np.mean(hsv[:, :, 1]))
        return lap_var > 2500 and sat_mean < 20
    except Exception:
        return False


# ---------------------------------------------------------------------------
# LivenessDetector  (public API — same interface as before)
# ---------------------------------------------------------------------------

class LivenessDetector:
    """
    Thread-safe passive motion liveness detector.

    Call check(frame_bgr, face_location, student_id) once per frame.
    Returns True after enough natural micro-motion is detected.
    No user action required. Works with glasses. Works at low resolution.
    """

    def __init__(self):
        self._lock     = threading.Lock()
        self._trackers = {}   # student_id -> _MotionTracker

    # ------------------------------------------------------------------

    def check(self, frame_bgr, face_location, student_id):
        """
        Parameters
        ----------
        frame_bgr    : np.ndarray  — full BGR camera frame (any resolution)
        face_location: (top, right, bottom, left) from face_recognition
        student_id   : str

        Returns
        -------
        bool  — True if the face passes liveness (sufficient motion detected
                and not flagged as a static texture spoof)
        """
        top, right, bottom, left = face_location

        # Clamp to frame bounds
        h, w = frame_bgr.shape[:2]
        top    = max(0, min(top,    h - 1))
        bottom = max(0, min(bottom, h))
        left   = max(0, min(left,   w - 1))
        right  = max(0, min(right,  w))

        face_crop = frame_bgr[top:bottom, left:right]

        if face_crop.size == 0:
            return False

        # Secondary: passive texture / screen check
        if _is_texture_spoof(face_crop):
            return False

        # Primary: passive motion check
        with self._lock:
            if student_id not in self._trackers:
                self._trackers[student_id] = _MotionTracker()
            tracker = self._trackers[student_id]

        # Release lock before doing computation
        return tracker.update(face_crop)

    # ------------------------------------------------------------------

    def get_progress(self, student_id):
        """Return 0.0–1.0 liveness confirmation progress for a student."""
        with self._lock:
            tracker = self._trackers.get(student_id)
        if tracker is None:
            return 0.0
        return tracker.progress()

    def is_confirmed(self, student_id):
        with self._lock:
            tracker = self._trackers.get(student_id)
        return tracker is not None and tracker.live_confirmed

    def reset_student(self, student_id):
        with self._lock:
            self._trackers.pop(student_id, None)

    def reset_all(self):
        with self._lock:
            self._trackers.clear()
