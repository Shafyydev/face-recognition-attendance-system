import unittest
from datetime import datetime, date, timedelta
from unittest.mock import patch, MagicMock
from database.models import get_session, Student, Attendance, ActivityLog
import notification_service
import app

class TestAuditFixes(unittest.TestCase):
    def setUp(self):
        self.session = get_session()
        self.test_sid = "TEST_AUDIT_01"
        self.test_student = self.session.query(Student).filter(Student.student_id == self.test_sid).first()
        if not self.test_student:
            self.test_student = Student(
                student_id=self.test_sid,
                name="Audit Test Student",
                department="Computer Science",
                year="3",
                student_mobile="9876543210",
                parent_mobile="9876543211",
                is_active=True
            )
            self.session.add(self.test_student)
            self.session.commit()

    def tearDown(self):
        self.session.query(Attendance).filter(Attendance.student_id == self.test_sid).delete()
        self.session.query(ActivityLog).filter(ActivityLog.student_id == self.test_sid).delete()
        self.session.commit()
        self.session.close()

    def test_reset_absentee_scheduler_does_not_spawn_process_absentee_check(self):
        """Test that reset_absentee_scheduler only resets _last_run_date and does not run process_absentee_check."""
        with patch.object(notification_service, 'process_absentee_check') as mock_check:
            notification_service.reset_absentee_scheduler()
            self.assertIsNone(notification_service._last_run_date)
            mock_check.assert_not_called()

    def test_send_late_alert_sunday_check_uses_record_date(self):
        """Test that send_late_alert checks the attendance record date, not wall-clock time."""
        # Create attendance record on a Thursday
        weekday_dt = datetime(2026, 10, 1, 9, 15) # Thursday
        att = Attendance(
            student_id=self.test_sid,
            name=self.test_student.name,
            date=weekday_dt,
            status='late',
            late_alert_sent=False
        )
        
        # Even if datetime.now() were Sunday, weekday record should not be suppressed by Sunday check
        with patch('notification_service.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 10, 4, 12, 0) # Sunday
            with patch('notification_service._async_send_late_alerts') as mock_async:
                res = notification_service.send_late_alert(self.test_student, att)
                self.assertTrue(res)

    def test_send_absent_alert_accepts_target_date(self):
        """Test that send_absent_alert checks target_date for Sunday suppression."""
        sunday_dt = date(2026, 10, 4) # Sunday
        weekday_dt = date(2026, 10, 1) # Thursday

        # Sunday target date should suppress absent alert
        self.assertFalse(notification_service.send_absent_alert(self.test_student, force=True, target_date=sunday_dt))

        # Weekday target date should proceed
        with patch('notification_service.dispatch_single_sms', return_value={"success": True}):
            res = notification_service.send_absent_alert(self.test_student, force=True, target_date=weekday_dt)
            self.assertTrue(res)

if __name__ == '__main__':
    unittest.main()
