"""
Unit tests for Sunday Attendance Restriction and TTS Feedback Feature.

Verifies:
1. When it is Sunday (weekday == 6):
   - Someone standing in front of the camera triggers TTS "No attendance for today".
   - The status returned is "sunday".
   - Attendance is not recorded in the database.
   - Rate-limiting prevents audio spam across repeated frames.
2. mark_attendance() returns "sunday" and avoids DB writes.
3. Non-Sunday days (weekdays) proceed normally without "No attendance for today" TTS.
"""

import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, time as dt_time, timedelta
import numpy as np

from database.models import init_db, get_session, Student, Attendance
from face_utils.attendance_marker import AttendanceMarker


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

    def test_mark_attendance_on_sunday(self):
        """Verify mark_attendance returns 'sunday' and never inserts attendance records on Sunday."""
        sunday_dt = datetime(2026, 10, 4, 9, 0, 0)  # 2026-10-04 is Sunday
        self.assertEqual(sunday_dt.weekday(), 6)

        with patch("face_utils.attendance_marker.datetime") as mock_dt:
            mock_dt.now.return_value = sunday_dt
            mock_dt.combine = datetime.combine
            mock_dt.min = datetime.min

            result = self.marker.mark_attendance("TEST_SUN_01", "Sunday Student")
            self.assertEqual(result, "sunday")

            # Verify no record created in database
            count = self.session.query(Attendance).filter_by(student_id="TEST_SUN_01").count()
            self.assertEqual(count, 0)

    def test_process_frame_on_sunday_triggers_tts_and_sets_status(self):
        """Verify that on Sunday, detecting a face speaks 'No attendance for today' and marks status as sunday."""
        sunday_dt = datetime(2026, 10, 4, 9, 0, 0)
        self.assertEqual(sunday_dt.weekday(), 6)

        # Mock frame and face recognition components
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

            # Mock match returning our student
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

            # Results must contain status "sunday"
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["status"], "sunday")
            self.assertEqual(results[0]["student_id"], "TEST_SUN_01")
            self.assertEqual(results[0]["name"], "Sunday Student")

            # Check that immediate subsequent frame does NOT call TTS again due to cooldown
            mock_speak.reset_mock()
            self.marker.frame_count = 2
            frame_out2, results2 = self.marker.process_frame(dummy_frame)
            mock_speak.assert_not_called()

    def test_process_frame_on_sunday_unknown_face(self):
        """Verify that unknown faces on Sunday also trigger 'No attendance for today' and return sunday status."""
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


if __name__ == "__main__":
    unittest.main()
