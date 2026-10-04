"""
Unit tests for Sunday Attendance Restriction and TTS Feedback Feature.

Verifies:
1. When it is Sunday (weekday == 6):
   - Confirmed student check-in punches attendance with status 'no_attendance' (never absent/late).
   - TTS feedback says 'No attendance for today'.
   - The status returned in results is 'no_attendance'.
   - Repeated frames do not spam duplicate records or audio.
   - Unknown faces trigger 'No attendance for today' without DB punch.
2. Manual override is completely disabled on Sunday (returns 403).
"""

import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, time as dt_time, timedelta
import numpy as np

from database.models import init_db, get_session, Student, Attendance
from face_utils.attendance_marker import AttendanceMarker
from app import app


class TestSundayFeature(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        self.session = get_session()
        self.session.query(Attendance).delete()
        self.session.query(Student).delete()

        # Create a test student
        self.student = Student(
            student_id="TEST_SUN_01",
            name="Sunday Student",
            student_mobile="9876543210",
            parent_mobile="9876543211",
            year="I",
            department="AI&DS"
        )
        self.session.add(self.student)
        self.session.commit()

        self.marker = AttendanceMarker()

    def tearDown(self):
        self.session.query(Attendance).delete()
        self.session.query(Student).delete()
        self.session.commit()
        self.session.close()

    def test_mark_attendance_on_sunday_punches_no_attendance(self):
        """Verify mark_attendance records 'no_attendance' on Sunday and never marks absent or late."""
        sunday_dt = datetime(2026, 10, 4, 10, 30, 0)  # 10:30 AM is after absent cutoff 9:30 AM!
        self.assertEqual(sunday_dt.weekday(), 6)

        with patch("face_utils.attendance_marker.datetime") as mock_dt:
            mock_dt.now.return_value = sunday_dt
            mock_dt.combine = datetime.combine
            mock_dt.min = datetime.min

            result = self.marker.mark_attendance("TEST_SUN_01", "Sunday Student")
            self.assertEqual(result, "no_attendance")

            # Verify record was created in database with status 'no_attendance' (NOT absent!)
            record = self.session.query(Attendance).filter_by(student_id="TEST_SUN_01").first()
            self.assertIsNotNone(record)
            self.assertEqual(record.status, "no_attendance")
            self.assertNotEqual(record.status, "absent")
            self.assertNotEqual(record.status, "late")

            # Verify second mark returns 'no_attendance' and does not duplicate
            result2 = self.marker.mark_attendance("TEST_SUN_01", "Sunday Student")
            self.assertEqual(result2, "no_attendance")
            count = self.session.query(Attendance).filter_by(student_id="TEST_SUN_01").count()
            self.assertEqual(count, 1)

    def test_process_frame_on_sunday_triggers_tts_and_punches_student(self):
        """Verify that on Sunday, detecting a known student speaks 'No attendance for today' and punches them."""
        sunday_dt = datetime(2026, 10, 4, 9, 45, 0)
        self.assertEqual(sunday_dt.weekday(), 6)

        dummy_frame = np.zeros((240, 320, 3), dtype=np.uint8)
        dummy_face_location = (30, 150, 130, 50)  # top, right, bottom, left (h=100, w=100)
        dummy_encoding = np.zeros(128, dtype=np.float32)

        with patch("face_utils.attendance_marker.datetime") as mock_dt, \
             patch("face_utils.attendance_marker.face_recognition.face_locations", return_value=[dummy_face_location]), \
             patch("face_utils.attendance_marker.face_recognition.face_encodings", return_value=[dummy_encoding]), \
             patch("tts_service.tts.speak") as mock_speak:

            mock_dt.now.return_value = sunday_dt
            mock_dt.combine = datetime.combine
            mock_dt.min = datetime.min

            # Reset frame count so PROCESS_EVERY_N_FRAMES triggers
            self.marker.frame_count = 2

            self.marker.embedding_encoder.find_best_match = MagicMock(return_value={
                "student_id": "TEST_SUN_01",
                "name": "Sunday Student",
                "distance": 0.25,
                "margin": 0.20
            })
            self.marker.decision_engine.update = MagicMock(return_value={"status": "CONFIRMED"})

            frame_out, results = self.marker.process_frame(dummy_frame)

            # TTS must be called with "No attendance for today"
            mock_speak.assert_called_with("No attendance for today")

            # Results must contain status "no_attendance"
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["status"], "no_attendance")
            self.assertEqual(results[0]["student_id"], "TEST_SUN_01")
            self.assertEqual(results[0]["name"], "Sunday Student")

            # Check that immediate subsequent frame does NOT call TTS again due to cooldown
            mock_speak.reset_mock()
            self.marker.frame_count = 2
            frame_out2, results2 = self.marker.process_frame(dummy_frame)
            mock_speak.assert_not_called()

    def test_process_frame_on_sunday_unknown_face(self):
        """Verify that unknown faces on Sunday also trigger 'No attendance for today'."""
        sunday_dt = datetime(2026, 10, 4, 10, 0, 0)
        dummy_frame = np.zeros((240, 320, 3), dtype=np.uint8)
        dummy_face_location = (30, 150, 130, 50)

        with patch("face_utils.attendance_marker.datetime") as mock_dt, \
             patch("face_utils.attendance_marker.face_recognition.face_locations", return_value=[dummy_face_location]), \
             patch("face_utils.attendance_marker.face_recognition.face_encodings", return_value=[]), \
             patch("tts_service.tts.speak") as mock_speak:

            mock_dt.now.return_value = sunday_dt
            mock_dt.combine = datetime.combine
            mock_dt.min = datetime.min

            self.marker.frame_count = 2
            frame_out, results = self.marker.process_frame(dummy_frame)

            mock_speak.assert_called_with("No attendance for today")
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["status"], "sunday")
            self.assertEqual(results[0]["student_id"], "unknown")
            self.assertEqual(results[0]["name"], "Unknown")

    def test_manual_override_disabled_on_sunday(self):
        """Verify that manual override is completely disabled on Sunday (returns 403)."""
        sunday_str = "2026-10-04"
        with app.test_client() as client:
            res = client.post("/api/attendance/manual", json={
                "student_id": "TEST_SUN_01",
                "status": "on_time",
                "date": sunday_str
            })
            self.assertEqual(res.status_code, 403)
            self.assertIn("Manual override is disabled on Sundays", res.get_json().get("error", ""))


if __name__ == "__main__":
    unittest.main()
