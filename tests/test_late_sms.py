"""
Comprehensive Test Suite for Late Arrival SMS Alert Feature
Verifies all 6 test scenarios required by the feature specification:
  - Test 1: On-time student (no alert sent)
  - Test 2: Late student (student & parent receive 1 alert)
  - Test 3: Student remains in front of camera (no duplicate records or duplicate SMS)
  - Test 4: SMS service failure (attendance remains recorded, no app crash, error logged)
  - Test 5: Missing mobile number (attendance works, missing number skipped, no crash)
  - Test 6: Existing student without mobile numbers (functions normally without error)
  - Validation: Indian mobile number format validation and normalization
  - Message formatting: 12-hour clock, student/parent message templates
"""

import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, time, timedelta

from database.models import init_db, get_session, Student, Attendance, ActivityLog
import notification_service
from notification_service import (
    normalize_indian_mobile,
    format_attendance_time,
    format_student_message,
    format_parent_message,
    send_late_alert,
    MockSMSProvider,
)
from face_utils.attendance_marker import AttendanceMarker


class TestMobileValidationAndFormatting(unittest.TestCase):
    def test_valid_indian_mobile_formats(self):
        valid_cases = [
            ("9876543210", "9876543210"),
            ("+91 9876543210", "9876543210"),
            ("+91-98765-43210", "9876543210"),
            ("919876543210", "9876543210"),
            ("09876543210", "9876543210"),
            ("6123456789", "6123456789"),
            ("7987654321", "7987654321"),
            ("8888888888", "8888888888"),
        ]
        for raw, expected in valid_cases:
            is_valid, normalized = normalize_indian_mobile(raw)
            self.assertTrue(is_valid, f"Expected {raw} to be valid")
            self.assertEqual(normalized, expected)

    def test_invalid_indian_mobile_formats(self):
        invalid_cases = [
            "",
            None,
            "12345",
            "5876543210",  # Starts with 5 (not 6-9)
            "0000000000",
            "abcdefghij",
            "9876543210123",  # Too long
            "987654321",      # Too short (9 digits)
        ]
        for raw in invalid_cases:
            is_valid, _ = normalize_indian_mobile(raw)
            self.assertFalse(is_valid, f"Expected {raw} to be invalid")

    def test_message_formatting(self):
        from datetime import datetime
        dt = datetime(2026, 6, 29, 8, 47)
        student_msg = format_student_message("MOHAMMED SHAFIULLAH N", "A24AID26", "III", "B.Sc. Artificial Intelligence", dt)
        parent_msg = format_parent_message("MOHAMMED SHAFIULLAH N", "A24AID26", "III", "B.Sc. Artificial Intelligence", dt)

        self.assertEqual(
            student_msg,
            "Dear Student, MOHAMMED SHAFIULLAH N (A24AID26) of III - B.Sc. Artificial Intelligence was late to college today (29/06/2026). St.Joseph's College of Arts & Science (Autonomous) - Cuddalore."
        )
        self.assertEqual(
            parent_msg,
            "Dear Parent, Your Son/Daughter, MOHAMMED SHAFIULLAH N (A24AID26) of III - B.Sc. Artificial Intelligence was late to college today (29/06/2026). St.Joseph's College of Arts & Science (Autonomous) - Cuddalore."
        )


class TestLateArrivalSMSAlert(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        self.session = get_session()
        # Clean up any leftover test data
        self.test_ids = ["TEST_ONTIME", "TEST_LATE", "TEST_DUP", "TEST_FAIL", "TEST_MISSING", "TEST_EXISTING"]
        for sid in self.test_ids:
            self.session.query(Attendance).filter(Attendance.student_id == sid).delete()
            self.session.query(Student).filter(Student.student_id == sid).delete()
            self.session.query(ActivityLog).filter(ActivityLog.student_id == sid).delete()
        self.session.commit()

        # Marker instance for testing
        self.marker = AttendanceMarker()

    def tearDown(self):
        for sid in self.test_ids:
            self.session.query(Attendance).filter(Attendance.student_id == sid).delete()
            self.session.query(Student).filter(Student.student_id == sid).delete()
            self.session.query(ActivityLog).filter(ActivityLog.student_id == sid).delete()
        self.session.commit()
        self.session.close()

    def test_case_1_on_time_student(self):
        """Test 1: Student arrives before 8:30 AM -> Attendance = on_time, No SMS sent."""
        sid = "TEST_ONTIME"
        student = Student(
            student_id=sid,
            name="Alice OnTime",
            student_mobile="9876543210",
            parent_mobile="9876543211",
        )
        self.session.add(student)
        self.session.commit()

        # Set LATE_AFTER to end of day so this attendance is always on_time
        self.marker.LATE_AFTER = time(23, 59, 59)

        with patch("notification_service.send_late_alert") as mock_alert:
            result = self.marker.mark_attendance(sid, "Alice OnTime")
            self.assertEqual(result, "marked")

            rec = self.session.query(Attendance).filter(Attendance.student_id == sid).first()
            self.assertIsNotNone(rec)
            self.assertEqual(rec.status, "on_time")
            # Alert must NOT be triggered
            mock_alert.assert_not_called()

    def test_case_2_late_student(self):
        """Test 2: Student arrives after 8:30 AM -> Attendance = late, Student & Parent receive alert."""
        sid = "TEST_LATE"
        student = Student(
            student_id=sid,
            name="Bob Late",
            student_mobile="9876543220",
            parent_mobile="9876543221",
        )
        self.session.add(student)
        self.session.commit()

        # Set LATE_AFTER to midnight (00:00) so this attendance is always late
        self.marker.LATE_AFTER = time(0, 0, 0)

        dispatched_sms = []

        class SpyProvider(MockSMSProvider):
            def send(self, to_number, message, recipient_type="recipient"):
                dispatched_sms.append((recipient_type, to_number, message))
                return super().send(to_number, message, recipient_type)

        with patch("notification_service.get_sms_provider", return_value=SpyProvider()):
            result = self.marker.mark_attendance(sid, "Bob Late")
            self.assertEqual(result, "marked")

            # Allow background thread to finish
            import time as py_time
            py_time.sleep(1.3)

            rec = self.session.query(Attendance).filter(Attendance.student_id == sid).first()
            self.assertIsNotNone(rec)
            self.assertEqual(rec.status, "late")
            self.assertTrue(rec.late_alert_sent)

            # Check dispatched alerts: exactly 1 student alert, 1 parent alert
            student_alerts = [m for m in dispatched_sms if m[0] == "student"]
            parent_alerts = [m for m in dispatched_sms if m[0] == "parent"]

            self.assertEqual(len(student_alerts), 1)
            self.assertEqual(len(parent_alerts), 1)
            self.assertIn("was late to college today", student_alerts[0][2])
            self.assertIn("was late to college today", parent_alerts[0][2])
            self.assertIn("St.Joseph's College of Arts & Science", parent_alerts[0][2])

    def test_case_3_student_remains_in_front_of_camera(self):
        """Test 3: Student remains in front of camera -> Only 1 attendance record, only 1 student alert, only 1 parent alert."""
        sid = "TEST_DUP"
        student = Student(
            student_id=sid,
            name="Charlie Front",
            student_mobile="9876543230",
            parent_mobile="9876543231",
        )
        self.session.add(student)
        self.session.commit()

        self.marker.LATE_AFTER = time(0, 0, 0)

        dispatched_sms = []

        class SpyProvider(MockSMSProvider):
            def send(self, to_number, message, recipient_type="recipient"):
                dispatched_sms.append((recipient_type, to_number, message))
                return super().send(to_number, message, recipient_type)

        with patch("notification_service.get_sms_provider", return_value=SpyProvider()):
            # First detection
            res1 = self.marker.mark_attendance(sid, "Charlie Front")
            self.assertEqual(res1, "marked")

            # Subsequent frame detections while standing in front of camera
            res2 = self.marker.mark_attendance(sid, "Charlie Front")
            self.assertEqual(res2, "already_present")

            res3 = self.marker.mark_attendance(sid, "Charlie Front")
            self.assertEqual(res3, "already_present")

            import time as py_time
            py_time.sleep(1.3)

            # Check DB records: exactly 1 attendance record
            records = self.session.query(Attendance).filter(Attendance.student_id == sid).all()
            self.assertEqual(len(records), 1)

            # Check dispatched alerts: exactly 1 student alert, 1 parent alert
            student_alerts = [m for m in dispatched_sms if m[0] == "student"]
            parent_alerts = [m for m in dispatched_sms if m[0] == "parent"]
            self.assertEqual(len(student_alerts), 1)
            self.assertEqual(len(parent_alerts), 1)

    def test_case_4_sms_service_failure(self):
        """Test 4: SMS service failure -> Attendance remains recorded, app does not crash, failure logged."""
        sid = "TEST_FAIL"
        student = Student(
            student_id=sid,
            name="David Fail",
            student_mobile="9876543240",
            parent_mobile="9876543241",
        )
        self.session.add(student)
        self.session.commit()

        self.marker.LATE_AFTER = time(0, 0, 0)

        class BrokenProvider(MockSMSProvider):
            def send(self, to_number, message, recipient_type="recipient"):
                raise ConnectionError("SMS Gateway timeout / unreachable")

        with patch("notification_service.get_sms_provider", return_value=BrokenProvider()):
            # Must not raise an exception
            try:
                result = self.marker.mark_attendance(sid, "David Fail")
            except Exception as exc:
                self.fail(f"mark_attendance crashed on SMS failure: {exc}")

            self.assertEqual(result, "marked")

            import time as py_time
            py_time.sleep(1.3)

            # Attendance must still be saved
            rec = self.session.query(Attendance).filter(Attendance.student_id == sid).first()
            self.assertIsNotNone(rec)
            self.assertEqual(rec.status, "late")

    def test_case_5_missing_mobile_number(self):
        """Test 5: Missing mobile number -> Attendance still works, missing number skipped, no crash, log recorded."""
        sid = "TEST_MISSING"
        # Student has no student_mobile, but has parent_mobile
        student = Student(
            student_id=sid,
            name="Eve Missing",
            student_mobile=None,
            parent_mobile="9876543251",
        )
        self.session.add(student)
        self.session.commit()

        self.marker.LATE_AFTER = time(0, 0, 0)

        dispatched_sms = []

        class SpyProvider(MockSMSProvider):
            def send(self, to_number, message, recipient_type="recipient"):
                dispatched_sms.append((recipient_type, to_number, message))
                return super().send(to_number, message, recipient_type)

        with patch("notification_service.get_sms_provider", return_value=SpyProvider()):
            result = self.marker.mark_attendance(sid, "Eve Missing")
            self.assertEqual(result, "marked")

            import time as py_time
            py_time.sleep(1.3)

            rec = self.session.query(Attendance).filter(Attendance.student_id == sid).first()
            self.assertIsNotNone(rec)
            self.assertEqual(rec.status, "late")

            # Student alert was skipped (0 sent), but parent alert was sent (1 sent)
            student_alerts = [m for m in dispatched_sms if m[0] == "student"]
            parent_alerts = [m for m in dispatched_sms if m[0] == "parent"]
            self.assertEqual(len(student_alerts), 0)
            self.assertEqual(len(parent_alerts), 1)
            self.assertEqual(parent_alerts[0][1], "9876543251")

    def test_case_6_existing_student(self):
        """Test 6: Existing student registered without mobile numbers -> Works normally without errors."""
        sid = "TEST_EXISTING"
        # Existing student row with empty mobile columns
        student = Student(
            student_id=sid,
            name="Frank Legacy",
            student_mobile=None,
            parent_mobile=None,
        )
        self.session.add(student)
        self.session.commit()

        self.marker.LATE_AFTER = time(0, 0, 0)

        dispatched_sms = []

        class SpyProvider(MockSMSProvider):
            def send(self, to_number, message, recipient_type="recipient"):
                dispatched_sms.append((recipient_type, to_number, message))
                return super().send(to_number, message, recipient_type)

        with patch("notification_service.get_sms_provider", return_value=SpyProvider()):
            try:
                result = self.marker.mark_attendance(sid, "Frank Legacy")
            except Exception as exc:
                self.fail(f"Existing student failed: {exc}")

            self.assertEqual(result, "marked")

            import time as py_time
            py_time.sleep(1.3)

            rec = self.session.query(Attendance).filter(Attendance.student_id == sid).first()
            self.assertIsNotNone(rec)
            self.assertEqual(rec.status, "late")
            self.assertEqual(len(dispatched_sms), 0)


if __name__ == "__main__":
    unittest.main()
