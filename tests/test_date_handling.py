import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, date, timedelta
import numpy as np
from database.models import init_db, get_session, Student, Attendance, ActivityLog
from face_utils.attendance_marker import AttendanceMarker
from app import app, _selected_attendance_date_lock

class TestAttendanceDateHandling(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        self.session = get_session()
        self.session.query(Attendance).filter(Attendance.student_id.like("TEST_DATE_%")).delete()
        self.session.query(Student).filter(Student.student_id.like("TEST_DATE_%")).delete()
        self.session.query(ActivityLog).filter(ActivityLog.student_id.like("TEST_DATE_%")).delete()
        self.session.commit()

        # Create test student
        self.student = Student(
            student_id="TEST_DATE_01",
            name="Date Test Student",
            student_mobile="9876543210",
            parent_mobile="9876543211",
            year="I",
            department="AI&DS"
        )
        self.session.add(self.student)
        self.session.commit()

        self.marker = AttendanceMarker()

    def tearDown(self):
        self.session.query(Attendance).filter(Attendance.student_id.like("TEST_DATE_%")).delete()
        self.session.query(Student).filter(Student.student_id.like("TEST_DATE_%")).delete()
        self.session.query(ActivityLog).filter(ActivityLog.student_id.like("TEST_DATE_%")).delete()
        self.session.commit()
        self.session.close()

    def test_previous_date_no_existing_attendance(self):
        """When a previous date is selected and no attendance exists, mark for that selected date."""
        from datetime import time as dt_time
        target_date_str = "2026-10-01"  # Thursday
        target_date = date(2026, 10, 1)

        self.marker.set_attendance_date(target_date_str)
        self.marker.LATE_AFTER = dt_time(23, 59, 59)
        self.marker.ABSENT_AFTER = dt_time(23, 59, 59)
        self.assertEqual(self.marker._get_attendance_date(), target_date)

        result = self.marker.mark_attendance("TEST_DATE_01", "Date Test Student")
        self.assertEqual(result, "marked")

        record = self.session.query(Attendance).filter_by(student_id="TEST_DATE_01").first()
        self.assertIsNotNone(record)
        self.assertEqual(record.date.date(), target_date)
        self.assertEqual(record.status, "on_time")

    def test_previous_date_existing_attendance(self):
        """When a previous date is selected and attendance ALREADY exists, detect existing attendance."""
        target_date_str = "2026-10-01"
        target_date = date(2026, 10, 1)

        # Insert existing attendance for 2026-10-01
        existing_att = Attendance(
            student_id="TEST_DATE_01",
            name="Date Test Student",
            date=datetime.combine(target_date, datetime.min.time()) + timedelta(hours=8, minutes=15),
            status="on_time",
            session="TEST_SESSION"
        )
        self.session.add(existing_att)
        self.session.commit()

        # Set date in marker
        self.marker.set_attendance_date(target_date_str)
        self.assertIn("TEST_DATE_01", self.marker.matched_today)
        self.assertEqual(self.marker.matched_today["TEST_DATE_01"], "already_present")

        # mark_attendance must recognize existing attendance and NOT insert a duplicate
        result = self.marker.mark_attendance("TEST_DATE_01", "Date Test Student")
        self.assertEqual(result, "already_present")
        self.assertNotEqual(result, "no_attendance")

        count = self.session.query(Attendance).filter_by(student_id="TEST_DATE_01").count()
        self.assertEqual(count, 1)

    def test_future_date_no_silent_replacement(self):
        """Future date should be preserved and used as selected, not replaced with today."""
        future_date_str = "2026-11-15"
        future_date = date(2026, 11, 15)

        self.marker.set_attendance_date(future_date_str)
        self.assertEqual(self.marker._get_attendance_date(), future_date)

    def test_set_attendance_date_api_sync(self):
        """Verify /api/set_attendance_date synchronizes date with backend."""
        with app.test_client() as client, patch("notification_service.send_absent_alert"):
            # Set to 2026-10-01
            res = client.post("/api/set_attendance_date", json={"date": "2026-10-01"})
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.get_json()["date"], "2026-10-01")

            # Check GET returns the set date
            res_get = client.get("/api/set_attendance_date")
            self.assertEqual(res_get.status_code, 200)
            self.assertEqual(res_get.get_json()["date"], "2026-10-01")

            # Reset back to today
            res_reset = client.post("/api/set_attendance_date", json={"date": ""})
            self.assertEqual(res_reset.status_code, 200)
            self.assertEqual(res_reset.get_json()["date"], "today")

    def test_background_mark_no_deadlock(self):
        """Verify _start_attendance_mark runs in background thread without deadlock."""
        import time
        from datetime import time as dt_time
        target_date_str = "2026-10-01"
        target_date = date(2026, 10, 1)

        self.marker.set_attendance_date(target_date_str)
        self.marker.LATE_AFTER = dt_time(23, 59, 59)
        self.marker.ABSENT_AFTER = dt_time(23, 59, 59)
        self.marker._start_attendance_mark("TEST_DATE_01", "Date Test Student")

        # Wait up to 2 seconds for background thread to complete
        start_wait = time.time()
        while time.time() - start_wait < 2.0:
            if "TEST_DATE_01" in self.marker.matched_today:
                break
            time.sleep(0.05)

        self.assertIn("TEST_DATE_01", self.marker.matched_today)
        self.assertEqual(self.marker.matched_today["TEST_DATE_01"], "marked")
        self.assertNotIn("TEST_DATE_01", self.marker._pending_marks)

        record = self.session.query(Attendance).filter_by(student_id="TEST_DATE_01").first()
        self.assertIsNotNone(record)
        self.assertEqual(record.date.date(), target_date)

    def test_date_switch_and_remark(self):
        """Switching dates clears pending state and preloads new date."""
        import time
        from datetime import time as dt_time
        self.marker.LATE_AFTER = dt_time(23, 59, 59)
        self.marker.ABSENT_AFTER = dt_time(23, 59, 59)

        # Mark on 2026-10-01
        self.marker.set_attendance_date("2026-10-01")
        self.marker.LATE_AFTER = dt_time(23, 59, 59)
        self.marker.ABSENT_AFTER = dt_time(23, 59, 59)
        self.marker._start_attendance_mark("TEST_DATE_01", "Date Test Student")
        time.sleep(0.2)
        self.assertIn("TEST_DATE_01", self.marker.matched_today)

        # Switch to 2026-10-02
        self.marker.set_attendance_date("2026-10-02")
        self.marker.LATE_AFTER = dt_time(23, 59, 59)
        self.marker.ABSENT_AFTER = dt_time(23, 59, 59)
        self.assertNotIn("TEST_DATE_01", self.marker.matched_today)
        self.assertEqual(len(self.marker._pending_marks), 0)

        # Now mark on 2026-10-02
        self.marker._start_attendance_mark("TEST_DATE_01", "Date Test Student")
        time.sleep(0.2)
        self.assertIn("TEST_DATE_01", self.marker.matched_today)

        records = self.session.query(Attendance).filter_by(student_id="TEST_DATE_01").all()
        self.assertEqual(len(records), 2)
        dates = {r.date.date() for r in records}
        self.assertEqual(dates, {date(2026, 10, 1), date(2026, 10, 2)})

    def test_sunday_selection_punch(self):
        """Selected date is Sunday -> punches with status 'no_attendance'."""
        import time
        sunday_date_str = "2026-09-27"  # Sunday
        self.marker.set_attendance_date(sunday_date_str)
        self.marker._start_attendance_mark("TEST_DATE_01", "Date Test Student")
        time.sleep(0.2)

        self.assertIn("TEST_DATE_01", self.marker.matched_today)
        self.assertEqual(self.marker.matched_today["TEST_DATE_01"], "no_attendance")

        record = self.session.query(Attendance).filter_by(student_id="TEST_DATE_01").first()
        self.assertIsNotNone(record)
        self.assertEqual(record.status, "no_attendance")
        self.assertEqual(record.date.date(), date(2026, 9, 27))

    def test_cutoff_on_selected_date(self):
        """Cutoff logic (late / absent) strictly applies to selected dates as well."""
        from datetime import time as dt_time
        target_date_str = "2026-10-03"

        # Case A: Current time is past absent cutoff -> camera_absent, record saved in DB
        self.marker.set_attendance_date(target_date_str)
        self.marker.ABSENT_AFTER = dt_time(0, 0, 0) # Force past absent cutoff
        result = self.marker.mark_attendance("TEST_DATE_01", "Date Test Student")
        self.assertEqual(result, "camera_absent")

        rec_absent = self.session.query(Attendance).filter_by(student_id="TEST_DATE_01").first()
        self.assertIsNotNone(rec_absent)
        self.assertEqual(rec_absent.status, "absent")
        self.assertEqual(rec_absent.date.date(), date(2026, 10, 3))

        # Clear record so Case B can test late status cleanly
        self.session.query(Attendance).filter_by(student_id="TEST_DATE_01").delete()
        self.session.commit()
        self.marker.matched_today.clear()

        # Case B: Current time is between late and absent cutoff -> late
        self.marker.set_attendance_date(target_date_str)
        self.marker.LATE_AFTER = dt_time(0, 0, 0)
        self.marker.ABSENT_AFTER = dt_time(23, 59, 59)
        result = self.marker.mark_attendance("TEST_DATE_01", "Date Test Student")
        self.assertEqual(result, "marked")

        rec = self.session.query(Attendance).filter_by(student_id="TEST_DATE_01").first()
        self.assertIsNotNone(rec)
        self.assertEqual(rec.status, "late")
        self.assertEqual(rec.date.date(), date(2026, 10, 3))

    def test_process_frame_full_flow(self):
        """Verify process_frame transitions from confirming to marked to already_present without hanging."""
        from unittest.mock import patch
        import numpy as np
        import time
        from datetime import time as dt_time

        self.marker.set_attendance_date("2026-10-01")
        self.marker.LATE_AFTER = dt_time(23, 59, 59)
        self.marker.ABSENT_AFTER = dt_time(23, 59, 59)
        # Ensure every frame is processed
        self.marker.PROCESS_EVERY_N_FRAMES = 1

        mock_location = [(50, 150, 150, 50)]  # top, right, bottom, left (100x100 box)
        mock_encoding = [np.zeros(128, dtype=np.float32)]
        mock_match = {
            "student_id": "TEST_DATE_01",
            "name": "Date Test Student",
            "distance": 0.20,
            "margin": 0.30
        }

        dummy_frame = np.zeros((240, 320, 3), dtype=np.uint8)

        with patch("face_recognition.face_locations", return_value=mock_location), \
             patch("face_recognition.face_encodings", return_value=mock_encoding), \
             patch.object(self.marker.embedding_encoder, "find_best_match", return_value=mock_match):

            # Frame 1: Candidate (confirming)
            _, res1 = self.marker.process_frame(dummy_frame.copy())
            self.assertEqual(len(res1), 1)
            self.assertEqual(res1[0]["status"], "confirming")

            # Frame 2: Candidate (confirming)
            _, res2 = self.marker.process_frame(dummy_frame.copy())
            self.assertEqual(len(res2), 1)
            self.assertEqual(res2[0]["status"], "confirming")

            # Frame 3: Confirmed -> marked
            _, res3 = self.marker.process_frame(dummy_frame.copy())
            self.assertEqual(len(res3), 1)
            self.assertEqual(res3[0]["status"], "marked")

            # Wait for background thread to write to DB
            time.sleep(0.3)

            # Frame 4: Next frame should show already_present
            _, res4 = self.marker.process_frame(dummy_frame.copy())
            self.assertEqual(len(res4), 1)
            self.assertEqual(res4[0]["status"], "already_present")

            # Verify in DB
            record = self.session.query(Attendance).filter_by(student_id="TEST_DATE_01").first()
            self.assertIsNotNone(record)
            self.assertEqual(record.date.date(), date(2026, 10, 1))

    def test_date_switching_reconciles_database_and_sms(self):
        """Switching date past cutoff immediately updates database with absent records and sends SMS."""
        with app.test_client() as client:
            with patch("notification_service.send_absent_alert") as mock_alert:
                # 2026-10-01 is Thursday (past weekday)
                res = client.post("/api/set_attendance_date", json={"date": "2026-10-01"})
                self.assertEqual(res.status_code, 200)

                # Check Attendance DB table has absent record for TEST_DATE_01
                rec = self.session.query(Attendance).filter_by(student_id="TEST_DATE_01").first()
                self.assertIsNotNone(rec)
                self.assertEqual(rec.status, "absent")
                self.assertEqual(rec.date.date(), date(2026, 10, 1))

                # Check /api/attendance returns absent record
                att_res = client.get("/api/attendance?date=2026-10-01")
                self.assertEqual(att_res.status_code, 200)
                data = att_res.get_json()
                matching = [row for row in data if row["student_id"] == "TEST_DATE_01"]
                self.assertEqual(len(matching), 1)
                self.assertEqual(matching[0]["status"], "absent")

                # Verify absent alert SMS was dispatched
                mock_alert.assert_called()

    def test_tts_speaks_absent_only_once(self):
        """TTS message announces absent once and does not repeat in subsequent frames."""
        self.marker.PROCESS_EVERY_N_FRAMES = 1
        self.marker.frame_count = 0
        dummy_frame = np.zeros((240, 320, 3), dtype=np.uint8)
        mock_location = [(50, 150, 150, 50)]
        mock_encoding = [np.zeros(128, dtype=np.float32)]
        mock_match = {
            "student_id": "TEST_DATE_01",
            "name": "Date Test Student",
            "distance": 0.25,
            "margin": 0.20
        }

        # Mark student as camera_absent in marker for a weekday (e.g. 2026-10-01, Thursday)
        self.marker.set_attendance_date("2026-10-01")
        self.marker.matched_today["TEST_DATE_01"] = "camera_absent"
        self.marker._last_spoken_time.clear()

        with patch("face_recognition.face_locations", return_value=mock_location), \
             patch("face_recognition.face_encodings", return_value=mock_encoding), \
             patch.object(self.marker.embedding_encoder, "find_best_match", return_value=mock_match), \
             patch("tts_service.tts.speak") as mock_tts:

            # Frame 1: Should speak absent
            _, res1 = self.marker.process_frame(dummy_frame.copy())
            self.assertEqual(len(res1), 1)
            self.assertEqual(res1[0]["status"], "absent")
            mock_tts.assert_called_once_with("You are marked absent")

            # Frame 2: Should NOT speak again
            mock_tts.reset_mock()
            _, res2 = self.marker.process_frame(dummy_frame.copy())
            self.assertEqual(len(res2), 1)
            self.assertEqual(res2[0]["status"], "absent")
            mock_tts.assert_not_called()


if __name__ == "__main__":
    unittest.main()
