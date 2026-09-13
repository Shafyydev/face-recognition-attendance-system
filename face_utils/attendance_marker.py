import os
import sys
import threading
import cv2
import numpy as np
import face_recognition
from datetime import datetime, timedelta

from database.models import get_session, Attendance
from face_utils.embedding_encoder import EmbeddingEncoder
from face_utils.face_embedding_store import FaceEmbeddingStore
from face_utils.decision_engine import RecognitionDecisionEngine


class AttendanceMarker:
    def __init__(self):
        # --------------------------------------------------------------
        # Application paths
        # --------------------------------------------------------------
        if getattr(sys, 'frozen', False):
            app_dir = os.path.dirname(sys.executable)
        else:
            app_dir = os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))
            )

        known_faces_dir = os.path.join(
            app_dir,
            "data",
            "known_faces"
        )

        embedding_dir = os.path.join(
            app_dir,
            "data",
            "face_embeddings"
        )

        os.makedirs(known_faces_dir, exist_ok=True)
        os.makedirs(embedding_dir, exist_ok=True)

        # --------------------------------------------------------------
        # New embedding recognition system
        # --------------------------------------------------------------
        self.embedding_encoder = EmbeddingEncoder(
            known_faces_dir=known_faces_dir
        )

        self.embedding_store = FaceEmbeddingStore(
            storage_dir=embedding_dir
        )

        self._load_embeddings()

        self.decision_engine = RecognitionDecisionEngine(
            max_distance=0.50,
            min_margin=0.08,
            confirmation_frames=3,
            reset_after_misses=2
        )

        # --------------------------------------------------------------
        # Attendance state
        # --------------------------------------------------------------
        self.session_id = datetime.now().strftime(
            "%Y%m%d_%H%M"
        )

        self.matched_today = set()
        self.frame_count = 0

        self._pending_marks = set()
        self._attendance_generation = 0
        self._attendance_lock = threading.Lock()

        # Keep the existing frame-processing rate.
        self.PROCESS_EVERY_N_FRAMES = 3

    # ------------------------------------------------------------------
    # Embedding loading
    # ------------------------------------------------------------------

    def _load_embeddings(self):
        """
        Load persistent embeddings.

        If an existing student has no JSON embedding file yet,
        generate one from their existing known_faces image.
        This preserves all existing enrolled students during migration.
        """

        stored_students = self.embedding_store.load_all()

        # First load all persistent embeddings into the encoder.
        for student_id, data in stored_students.items():
            for embedding in data.get("embeddings", []):
                self.embedding_encoder.add_embedding(
                    student_id,
                    data["name"],
                    embedding
                )

        # Find existing known-face images which do not yet have
        # persistent embeddings.
        if not os.path.isdir(
            self.embedding_encoder.known_faces_dir
        ):
            return

        for filename in sorted(
            os.listdir(
                self.embedding_encoder.known_faces_dir
            )
        ):
            if not filename.lower().endswith(
                (".jpg", ".jpeg", ".png")
            ):
                continue

            student_id, name = (
                self.embedding_encoder.parse_student_info(
                    filename
                )
            )

            if not student_id:
                continue

            # Already loaded from persistent storage.
            if student_id in self.embedding_encoder.known_embeddings:
                continue

            image_path = os.path.join(
                self.embedding_encoder.known_faces_dir,
                filename
            )

            try:
                embedding = self.embedding_encoder.encode_image(
                    image_path
                )

                if embedding is None:
                    print(
                        f"WARNING: Could not create embedding: "
                        f"{filename}"
                    )
                    continue

                # Add to current recognition engine.
                self.embedding_encoder.add_embedding(
                    student_id,
                    name,
                    embedding
                )

                # Persist it for future launches.
                self.embedding_store.save_student(
                    student_id,
                    name,
                    [embedding]
                )

                print(
                    f"Created persistent embedding: {filename}"
                )

            except Exception as exc:
                print(
                    f"ERROR creating embedding for "
                    f"{filename}: {exc}"
                )

        print(
            f"Embedding students loaded: "
            f"{len(self.embedding_encoder.known_embeddings)}"
        )

    def reload_embeddings(self):
        """Replace the in-memory embeddings with the persistent store."""

        self.embedding_encoder.known_embeddings.clear()
        self._load_embeddings()

    # ------------------------------------------------------------------
    # Attendance reset
    # ------------------------------------------------------------------

    def reset(self):
        """Reset attendance state and invalidate pending background writes."""

        with self._attendance_lock:
            self._attendance_generation += 1
            self.matched_today.clear()
            self.decision_engine.reset()
            self.session_id = datetime.now().strftime(
                "%Y%m%d_%H%M"
            )

            print(
                "Attendance reset - ready for new records"
            )

    # ------------------------------------------------------------------
    # Frame processing
    # ------------------------------------------------------------------

    def process_frame(self, frame):
        self.frame_count += 1

        # Process every 3rd frame to save CPU.
        if (
            self.frame_count %
            self.PROCESS_EVERY_N_FRAMES
        ) != 0:
            return frame, []

        if frame is None or frame.size == 0:
            return frame, []

        # --------------------------------------------------------------
        # Face detection
        # --------------------------------------------------------------
        rgb = cv2.cvtColor(
            frame,
            cv2.COLOR_BGR2RGB
        )

        locations = face_recognition.face_locations(
            rgb,
            number_of_times_to_upsample=1,
            model="hog"
        )

        results = []
        matched_this_frame = set()

        if locations:
            # Largest face first.
            locations = sorted(
                locations,
                key=lambda box: (
                    (box[2] - box[0]) *
                    (box[1] - box[3])
                ),
                reverse=True
            )

            for location in locations:
                top, right, bottom, left = location

                w = right - left
                h = bottom - top

                if w < 50 or h < 50:
                    continue

                # ------------------------------------------------------
                # Generate live 128-D embedding.
                # ------------------------------------------------------
                encodings = face_recognition.face_encodings(
                    rgb,
                    known_face_locations=[location],
                    num_jitters=1
                )

                if not encodings:
                    self._draw_unknown(
                        frame,
                        left,
                        top,
                        right,
                        bottom,
                        "Unknown"
                    )
                    continue

                embedding = np.asarray(
                    encodings[0],
                    dtype=np.float32
                )

                # ------------------------------------------------------
                # Find best identity.
                # ------------------------------------------------------
                match = self.embedding_encoder.find_best_match(
                    embedding
                )

                if match is None:
                    self._draw_unknown(
                        frame,
                        left,
                        top,
                        right,
                        bottom,
                        "Unknown"
                    )
                    continue

                decision = self.decision_engine.update(
                    match
                )

                student_id = match["student_id"]
                name = match["name"]
                distance = match["distance"]
                margin = match["margin"]

                if decision["status"] in (
                    "CANDIDATE",
                    "CONFIRMED"
                ):
                    matched_this_frame.add(student_id)

                    if student_id not in self.matched_today:
                        if decision["status"] == "CONFIRMED":
                            self._start_attendance_mark(
                                student_id,
                                name
                            )
                            status = "marked"
                        else:
                            status = "confirming"
                    else:
                        status = "already_present"

                    color = (0, 255, 0)

                    label_text = (
                        f"{name} "
                        f"({distance:.2f})"
                    )

                    cv2.rectangle(
                        frame,
                        (left, top),
                        (right, bottom),
                        color,
                        2
                    )

                    cv2.putText(
                        frame,
                        label_text,
                        (left, max(20, top - 10)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6,
                        color,
                        2
                    )

                    results.append({
                        "student_id": student_id,
                        "name": name,
                        "status": status,
                        "box": [left, top, right, bottom]
                    })

                else:
                    # --------------------------------------------------
                    # Unknown / rejected face.
                    # --------------------------------------------------
                    reason = "Unknown"

                    if distance > 0.50:
                        reason = "Unknown"
                    elif margin < 0.08:
                        reason = "Uncertain"

                    self._draw_unknown(
                        frame,
                        left,
                        top,
                        right,
                        bottom,
                        reason
                    )

        return frame, results

    # ------------------------------------------------------------------
    # Recognition helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _draw_unknown(
        frame,
        left,
        top,
        right,
        bottom,
        text
    ):
        color = (0, 0, 255)

        cv2.rectangle(
            frame,
            (left, top),
            (right, bottom),
            color,
            2
        )

        cv2.putText(
            frame,
            text,
            (left, max(20, top - 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            color,
            2
        )

    def _start_attendance_mark(
        self,
        student_id,
        name
    ):
        with self._attendance_lock:
            if student_id in self.matched_today:
                return

            if student_id in self._pending_marks:
                return

            self._pending_marks.add(student_id)

            generation = self._attendance_generation

        threading.Thread(
            target=self._mark_attendance_background,
            args=(
                student_id,
                name,
                generation
            ),
            daemon=True
        ).start()

    # ------------------------------------------------------------------
    # Background attendance writing
    # ------------------------------------------------------------------

    def _mark_attendance_background(
        self,
        student_id,
        name,
        generation
    ):
        """Write attendance in the background."""

        try:
            with self._attendance_lock:

                # Cancel writes created before Clear Records.
                if generation != self._attendance_generation:
                    return

                result = self.mark_attendance(
                    student_id,
                    name,
                    generation
                )

                if result in (
                    "marked",
                    "already_present"
                ):
                    self.matched_today.add(
                        student_id
                    )

                if result == "marked":
                    print(
                        f"MARKED: {name}"
                    )

        except Exception as exc:
            print(
                f"Attendance write error for "
                f"{name}: {exc}"
            )

        finally:
            with self._attendance_lock:
                self._pending_marks.discard(
                    student_id
                )

    def mark_attendance(
        self,
        student_id,
        name,
        generation=None
    ):
        # This method is normally called by the background worker
        # while _attendance_lock is already held.

        if (
            generation is not None and
            generation != self._attendance_generation
        ):
            return "cancelled"

        session = get_session()

        try:
            today = datetime.now().date()
            start = datetime.combine(today, datetime.min.time())
            end = start + timedelta(days=1)

            existing = session.query(
                Attendance
            ).filter(
                Attendance.student_id == student_id,
                Attendance.date >= start,
                Attendance.date < end
            ).first()

            if existing:
                return "already_present"

            # Check again after the database lookup.
            if (
                generation is not None and
                generation != self._attendance_generation
            ):
                return "cancelled"

            attendance = Attendance(
                student_id=student_id,
                name=name,
                status="present",
                session=self.session_id
            )

            session.add(attendance)

            print(f"ATTENDANCE DEBUG: committing {student_id} | {name} | session={self.session_id}", flush=True)

            session.commit()

            print(f"ATTENDANCE DEBUG: commit successful {student_id}", flush=True)

            

            return "marked"

        finally:
            session.close()






