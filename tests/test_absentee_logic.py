"""
Unit tests for Absentee alerts, scheduler filtering, deduplication, and manual correction logic.
"""

import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, time, timedelta

from database.models import init_db, get_session, Student, Attendance, ActivityLog
import notification_service
from notification_service import send_absent_alert, format_parent_absent_message, format_parent_correction_message
from app import app


class TestAbsenteeAndCorrectionLogic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        self.session = get_session()
        self.test_ids = ["TEST_ABS_1", "TEST_ABS_2", "TEST_ABS_3"]
        for sid in self.test_ids:
            self.session.query(Attendance).filter(Attendance.student_id == sid).delete()
            self.session.query(Student).filter(Student.student_id == sid).delete()
            self.session.query(ActivityLog).filter(ActivityLog.student_id == sid).delete()
        self.session.commit()

        # Add 3 test students
        self.s1 = Student(student_id="TEST_ABS_1", name="Student One", department="Computer Science", year="III", parent_mobile="9876543210")
        self.s2 = Student(student_id="TEST_ABS_2", name="Student Two", department="Computer Science", year="III", parent_mobile="9876543211")
        self.s3 = Student(student_id="TEST_ABS_3", name="Student Three", department="Computer Science", year="III", parent_mobile="9876543212")
        self.session.add_all([self.s1, self.s2, self.s3])
        self.session.commit()

    def tearDown(self):
        for sid in self.test_ids:
            self.session.query(Attendance).filter(Attendance.student_id == sid).delete()
            self.session.query(Student).filter(Student.student_id == sid).delete()
            self.session.query(ActivityLog).filter(ActivityLog.student_id == sid).delete()
        self.session.commit()
        self.session.close()

    def test_absent_message_template(self):
        """Verify professional absent SMS format matches requirements."""
        dt = datetime(2026, 9, 27, 9, 31)
        msg = format_parent_absent_message("Student One", "TEST_ABS_1", "III", "Computer Science", dt)
        self.assertEqual(
            msg,
            "Dear Parent, Your Son/Daughter Student One (TEST_ABS_1) of III - Computer Science is absent in the college today (27/09/2026). St.Joseph's College of Arts & Science (Autonomous) - Cuddalore."
        )

    def test_absent_deduplication(self):
        """Verify send_absent_alert does not send duplicate SMS unless force=True."""
        monday = datetime(2026, 9, 28, 10, 0) # Monday
        with patch("notification_service.dispatch_single_sms") as mock_dispatch, \
             patch("notification_service.datetime") as mock_dt:
            mock_dt.now.return_value = monday
            mock_dt.combine = datetime.combine
            mock_dt.min = datetime.min
            mock_dispatch.return_value = {"success": True}
            
            # First alert
            send_absent_alert(self.s1)
            import time as py_time
            py_time.sleep(0.8)

            # Check ActivityLog recorded
            log = self.session.query(ActivityLog).filter(
                ActivityLog.student_id == "TEST_ABS_1",
                ActivityLog.event_type == "absent_alert_sent"
            ).first()
            self.assertIsNotNone(log)

            call_count_after_first = mock_dispatch.call_count

            # Second alert without force should be skipped
            send_absent_alert(self.s1, force=False)
            py_time.sleep(0.8)
            self.assertEqual(mock_dispatch.call_count, call_count_after_first)

            # Third alert with force=True should proceed
            send_absent_alert(self.s1, force=True)
            py_time.sleep(0.8)
            self.assertGreater(mock_dispatch.call_count, call_count_after_first)

    def test_manual_override_no_correction_sms(self):
        """Verify manual override to on_time does NOT send correction alert."""
        now = datetime.now()
        with app.test_client() as client:
            with patch("notification_service.send_correction_alert") as mock_correction:
                res = client.post("/api/attendance/manual", json={
                    "student_id": "TEST_ABS_2",
                    "status": "on_time",
                    "date": now.strftime("%Y-%m-%d")
                })
                self.assertEqual(res.status_code, 200)
                mock_correction.assert_not_called()

    def test_sunday_sms_suppression(self):
        """Verify that Sunday suppresses SMS alerts."""
        with patch("datetime.datetime") as mock_dt:
            # 2026-09-27 is Sunday
            mock_dt.now.return_value = datetime(2026, 9, 27, 10, 0)
            mock_dt.combine = datetime.combine
            mock_dt.min = datetime.min
            res = send_absent_alert(self.s1, force=True)
            self.assertFalse(res)


if __name__ == "__main__":
    unittest.main()
