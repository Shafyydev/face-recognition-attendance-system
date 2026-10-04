import os
import sys
import time
import threading
import cv2
import numpy as np
import face_recognition
from datetime import datetime, timedelta
from datetime import time as dt_time

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

        self.matched_today = {}
        self._last_spoken_time = {}
        self._last_sunday_spoken_time = 0.0
        # Date override set by dashboard date-picker. None means "use today".
        self._attendance_date_override = None
        self.frame_count = 0

        self._pending_marks = set()
        self._attendance_generation = 0
        self._attendance_lock = threading.RLock()

        # Attendance is blocked until the dashboard sends 'release'.
        # Value is a float timestamp; marking is allowed when time.time() > _hold_until.
        self._hold_until = 0.0

        # Keep the existing frame-processing rate.
        self.PROCESS_EVERY_N_FRAMES = 3

        # Time cutoffs for attendance status
        self.LATE_AFTER = dt_time(8, 30)
        self.ABSENT_AFTER = dt_time(9, 30)

        # Preload today's existing attendance into matched_today
        self._preload_attendance_for_date(datetime.now().date())

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
        """Replace the in-memory embeddings with the persistent store.

        Also resets matched_today and the decision engine so that
        students who re-register in the same session are not stuck
        as 'already_present' from an earlier recognition hit.
        """

        self.embedding_encoder.known_embeddings.clear()
        self._load_embeddings()

        # Reset attendance state so re-registered students
        # are not blocked by a stale matched_today entry.
        with self._attendance_lock:
            self.matched_today.clear()
            self.decision_engine.reset()
            # Freeze marking until the dashboard explicitly releases.
            self._hold_until = float('inf')
            print('Recognition worker: matched_today reset on reload, hold active', flush=True)

    def hold(self):
        """Freeze attendance marking until release_hold() is called.

        Called when the user navigates to the registration page so that
        no attendance is written while the student is posing for samples.
        """
        self._hold_until = float('inf')
        print('Recognition worker: marking held (registration page)', flush=True)

    def release_hold(self, grace_seconds=3):
        """Allow attendance marking after grace_seconds have elapsed.

        Called by the worker when the dashboard sends a 'release' command.
        The grace period lets the student walk from the registration page
        to the camera before their first mark fires.
        """
        self._hold_until = time.time() + grace_seconds
        print(
            f'Recognition worker: hold released, marking allowed in '
            f'{grace_seconds}s',
            flush=True
        )

    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Attendance reset & date management
    # ------------------------------------------------------------------

    def _preload_attendance_for_date(self, att_date):
        """Preload in-memory matched_today from database for the specified date."""
        session = None
        try:
            session = get_session()
            start = datetime.combine(att_date, datetime.min.time())
            end = start + timedelta(days=1)
            records = session.query(Attendance).filter(
                Attendance.date >= start,
                Attendance.date < end
            ).all()
            with self._attendance_lock:
                self.matched_today.clear()
                for att in records:
                    if att.status in ('on_time', 'present', 'late'):
                        self.matched_today[att.student_id] = 'already_present'
                    elif att.status == 'absent':
                        if self.matched_today.get(att.student_id) != 'already_present':
                            self.matched_today[att.student_id] = 'camera_absent'
                    elif att.status in ('no_attendance', 'sunday'):
                        if self.matched_today.get(att.student_id) != 'already_present':
                            self.matched_today[att.student_id] = 'no_attendance'
                    else:
                        self.matched_today[att.student_id] = 'already_present'
                print(f"AttendanceMarker: Preloaded {len(records)} existing attendance records for {att_date}", flush=True)
        except Exception as exc:
            print(f"AttendanceMarker: Error preloading attendance for {att_date}: {exc}", flush=True)
        finally:
            if session:
                session.close()

    def set_attendance_date(self, date_str):
        """Set the attendance date override from the dashboard date-picker.

        date_str must be 'YYYY-MM-DD'. Pass None or '' to revert to today.
        Also clears matched_today and preloads existing attendance for that date.
        """
        import re as _re
        with self._attendance_lock:
            self._attendance_generation += 1
            if date_str and _re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
                from datetime import date as _date
                try:
                    self._attendance_date_override = _date.fromisoformat(date_str)
                    print(f'AttendanceMarker: attendance date set to {date_str}', flush=True)
                except ValueError:
                    self._attendance_date_override = None
            else:
                self._attendance_date_override = None
                print('AttendanceMarker: attendance date reverted to today', flush=True)

            self.matched_today.clear()
            self._pending_marks.clear()
            self.decision_engine.reset()
            self._last_spoken_time.clear()
            self._last_sunday_spoken_time = 0.0
            self._hold_until = 0.0

        # Preload existing attendance for the effective date
        self._preload_attendance_for_date(self._get_attendance_date())

    def _get_attendance_date(self):
        """Return the effective attendance date (override or today)."""
        with self._attendance_lock:
            return self._attendance_date_override or datetime.now().date()

    def reset(self):
        """Reset attendance state and invalidate pending background writes."""

        with self._attendance_lock:
            self._attendance_generation += 1
            self.matched_today.clear()
            self._pending_marks.clear()
            self.decision_engine.reset()
            self._last_spoken_time.clear()
            self._last_sunday_spoken_time = 0.0
            self._hold_until = 0.0
            self.session_id = datetime.now().strftime(
                "%Y%m%d_%H%M"
            )

            print(
                "Attendance reset - ready for new records"
            )

        self._preload_attendance_for_date(self._get_attendance_date())

    def unmark_student(self, student_id):
        """Remove a student from in-memory matched_today dict so they can be re-marked."""
        with self._attendance_lock:
            self.matched_today.pop(student_id, None)
            self._pending_marks.discard(student_id)
            if hasattr(self, 'decision_engine'):
                self.decision_engine.reset()

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

            # Use the date-picker override date (if set) to decide Sunday,
            # not necessarily today's calendar date.
            _eff_date = self._get_attendance_date()
            is_sunday = (_eff_date.weekday() == 6)

            for location in locations:
                top, right, bottom, left = location

                w = right - left
                h = bottom - top

                if w < 50 or h < 50:
                    continue

                # On Sunday, provide voice feedback for anyone detected in front of camera
                if is_sunday:
                    now_sec = time.time()
                    if now_sec - self._last_sunday_spoken_time > 3.5:
                        self._last_sunday_spoken_time = now_sec
                        try:
                            from tts_service import tts
                            tts.speak("No attendance for today")
                        except Exception as tts_exc:
                            print(f"TTS Sunday error: {tts_exc}", flush=True)

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
                        "No Attendance" if is_sunday else "Unknown"
                    )
                    if is_sunday:
                        results.append({
                            "student_id": "unknown",
                            "name": "Unknown",
                            "status": "sunday",
                            "box": [left, top, right, bottom]
                        })
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
                        "No Attendance" if is_sunday else "Unknown"
                    )
                    if is_sunday:
                        results.append({
                            "student_id": "unknown",
                            "name": "Unknown",
                            "status": "sunday",
                            "box": [left, top, right, bottom]
                        })
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

                    if is_sunday:
                        if student_id not in self.matched_today:
                            if student_id in self._pending_marks:
                                status = "no_attendance"
                            elif decision["status"] == "CONFIRMED":
                                if time.time() < self._hold_until:
                                    status = "confirming"
                                else:
                                    self._start_attendance_mark(
                                        student_id,
                                        name
                                    )
                                    status = "no_attendance"
                            else:
                                status = "confirming"
                        else:
                            status = "no_attendance"
                    elif student_id not in self.matched_today:
                        now_time = datetime.now().time()
                        if student_id in self._pending_marks:
                            status = "absent" if now_time > self.ABSENT_AFTER else "marked"
                        elif decision["status"] == "CONFIRMED":
                            if time.time() < self._hold_until:
                                # Dashboard has not yet signalled ready — keep
                                # showing the face box but do not write to DB.
                                status = "confirming"
                            else:
                                self._start_attendance_mark(
                                    student_id,
                                    name
                                )
                                if now_time > self.ABSENT_AFTER:
                                    status = "absent"
                                else:
                                    status = "marked"
                        else:
                            status = "confirming"
                    else:
                        db_status = self.matched_today[student_id]
                        if db_status == "camera_absent":
                            status = "absent"
                            
                            # Announce absent result ONCE per student (do not repeat)
                            if student_id not in self._last_spoken_time:
                                self._last_spoken_time[student_id] = time.time()
                                try:
                                    from tts_service import tts
                                    tts.speak("You are marked absent")
                                except Exception:
                                    pass
                        elif db_status in ("no_attendance", "sunday"):
                            status = "no_attendance"
                        else:
                            status = "already_present"

                    color = (0, 165, 255) if is_sunday else (0, 255, 0)

                    label_text = (
                        f"{name} (No Attendance Today)" if is_sunday else
                        f"{name} ({distance:.2f})"
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
                        "No Attendance" if is_sunday else reason
                    )
                    if is_sunday:
                        results.append({
                            "student_id": "unknown",
                            "name": "Unknown",
                            "status": "sunday",
                            "box": [left, top, right, bottom]
                        })

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
        color = (0, 165, 255) if "No Attendance" in text else (0, 0, 255)

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
                    "already_present",
                    "camera_absent",
                    "no_attendance",
                    "sunday"
                ):
                    self.matched_today[student_id] = result

                if result == "marked":
                    print(
                        f"MARKED: {name}"
                    )

                    # Speak the student's name aloud
                    try:
                        from tts_service import tts
                        tts.speak("Attendance marked")
                    except Exception as tts_exc:
                        print(f"TTS error: {tts_exc}", flush=True)

                elif result == "camera_absent":
                    print(
                        f"CAMERA ABSENT: {name}"
                    )
                    
                    try:
                        self._last_spoken_time[student_id] = time.time()
                        from tts_service import tts
                        tts.speak("You are marked absent")
                    except Exception as tts_exc:
                        print(f"TTS error: {tts_exc}", flush=True)

                elif result in ("no_attendance", "sunday"):
                    print(
                        f"SUNDAY PUNCH (NO ATTENDANCE): {name}"
                    )
                    now_sec = time.time()
                    if now_sec - self._last_sunday_spoken_time > 3.5:
                        self._last_sunday_spoken_time = now_sec
                        try:
                            from tts_service import tts
                            tts.speak("No attendance for today")
                        except Exception as tts_exc:
                            print(f"TTS Sunday error: {tts_exc}", flush=True)

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
            # Use the dashboard-selected date (or today if not overridden).
            attendance_date = self._get_attendance_date()
            start = datetime.combine(attendance_date, datetime.min.time())
            end = start + timedelta(days=1)

            existing = session.query(
                Attendance
            ).filter(
                Attendance.student_id == student_id,
                Attendance.date >= start,
                Attendance.date < end
            ).first()

            if existing:
                if existing.status == 'absent':
                    return "camera_absent"
                if existing.status == 'no_attendance':
                    return "no_attendance"
                return "already_present"

            # Check again after the database lookup.
            if (
                generation is not None and
                generation != self._attendance_generation
            ):
                return "cancelled"

            # ----------------------------------------------------------
            # On Sunday, punch student with status 'no_attendance'
            # (Never marked absent or late on Sunday)
            # ----------------------------------------------------------
            if attendance_date.weekday() == 6:
                record_dt = datetime.combine(attendance_date, datetime.now().time())
                attendance = Attendance(
                    student_id=student_id,
                    name=name,
                    date=record_dt,
                    status="no_attendance",
                    session=self.session_id
                )
                session.add(attendance)
                session.commit()
                print(f"ATTENDANCE DEBUG: Sunday punch committed {student_id} ({name}) for {attendance_date}", flush=True)
                return "no_attendance"

            # Check again after the database lookup.
            if (
                generation is not None and
                generation != self._attendance_generation
            ):
                return "cancelled"

            # Use actual wall-clock time for late/absent cutoffs;
            # the DATE comes from the override (or today).
            now_time = datetime.now().time()
            if now_time > self.ABSENT_AFTER:
                # Student arrived after the absent cutoff (9:30 AM).
                # Persist absent record in database if not already recorded.
                if not existing:
                    record_dt = datetime.combine(attendance_date, now_time)
                    attendance = Attendance(
                        student_id=student_id,
                        name=name,
                        date=record_dt,
                        status="absent",
                        session=self.session_id
                    )
                    session.add(attendance)
                    session.commit()
                    try:
                        from database.models import Student
                        from notification_service import send_absent_alert
                        student_record = session.query(Student).filter(Student.student_id == student_id).first()
                        if student_record:
                            send_absent_alert(student_record, target_date=attendance_date)
                    except Exception as alert_exc:
                        print(f"Absent alert trigger error: {alert_exc}", flush=True)
                return "camera_absent"
            elif now_time > self.LATE_AFTER:
                att_status = "late"
            else:
                att_status = "on_time"

            record_dt = datetime.combine(attendance_date, datetime.now().time())
            attendance = Attendance(
                student_id=student_id,
                name=name,
                date=record_dt,
                status=att_status,
                session=self.session_id
            )

            session.add(attendance)
            session.commit()

            print(f"ATTENDANCE DEBUG: commit successful {student_id}", flush=True)

            # ----------------------------------------------------------
            # Skip all SMS alerts on Sunday (college is closed)
            # ----------------------------------------------------------
            if attendance_date.weekday() == 6:
                return "marked"

            # ----------------------------------------------------------
            # Trigger late arrival alert if student arrived after cutoff
            # ----------------------------------------------------------
            if attendance.status == "late":
                try:
                    from database.models import Student
                    from notification_service import send_late_alert

                    student_record = session.query(Student).filter(
                        Student.student_id == student_id
                    ).first()

                    if student_record:
                        send_late_alert(student_record, attendance)
                    else:
                        print(f"Late alert skipped: Student record for {student_id} not found", flush=True)

                except Exception as alert_exc:
                    print(f"Late alert trigger error for {student_id}: {alert_exc}", flush=True)

            elif attendance.status == "absent":
                try:
                    from database.models import Student
                    from notification_service import send_absent_alert

                    student_record = session.query(Student).filter(
                        Student.student_id == student_id
                    ).first()

                    if student_record:
                        # Deduplication in notification_service ensures no duplicate SMS if already sent by scheduler
                        send_absent_alert(student_record)
                    else:
                        print(f"Absent alert skipped: Student record for {student_id} not found", flush=True)

                except Exception as alert_exc:
                    print(f"Absent alert trigger error for {student_id}: {alert_exc}", flush=True)

            return "marked"

        finally:
            session.close()






