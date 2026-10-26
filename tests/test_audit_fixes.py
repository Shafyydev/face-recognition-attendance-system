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

    def test_process_absentee_check_skips_when_attendance_cleared(self):
        """Test that process_absentee_check does not re-mark students absent after attendance is cleared."""
        weekday_dt = date(2026, 10, 15) # Thursday
        start_of_day = datetime.combine(weekday_dt, datetime.min.time())
        end_of_day = start_of_day + timedelta(days=1)
        
        try:
            # Log attendance_cleared for that date
            clear_log = ActivityLog(
                event_type="attendance_cleared",
                title="Attendance records cleared",
                detail="Test clear",
                student_id=self.test_sid,
                created_at=start_of_day + timedelta(hours=10)
            )
            self.session.add(clear_log)
            self.session.commit()

            # Run automated absentee check without force
            with patch('notification_service.send_absent_alert') as mock_alert:
                notification_service.process_absentee_check(force=False, target_date=weekday_dt)
                mock_alert.assert_not_called()

            # When forced, it should proceed
            with patch('notification_service.send_absent_alert') as mock_alert:
                notification_service.process_absentee_check(force=True, target_date=weekday_dt)
                mock_alert.assert_called()
        finally:
            self.session.query(Attendance).filter(
                Attendance.date >= start_of_day, Attendance.date < end_of_day
            ).delete()
            self.session.query(ActivityLog).filter(
                ActivityLog.created_at >= start_of_day, ActivityLog.created_at < end_of_day
            ).delete()
            self.session.commit()

    def test_clear_today_preserves_activity_logs(self):
        """Test that /api/clear_today does not wipe ActivityLog."""
        test_dt = date(2026, 10, 22)
        start_of_day = datetime.combine(test_dt, datetime.min.time())
        end_of_day = start_of_day + timedelta(days=1)
        
        try:
            count_before = self.session.query(ActivityLog).filter(
                ActivityLog.event_type == 'absentee_scheduler_run',
                ActivityLog.created_at >= start_of_day,
                ActivityLog.created_at < end_of_day
            ).count()

            # Add an attendance record and an activity log
            att = Attendance(
                student_id=self.test_sid,
                name=self.test_student.name,
                date=start_of_day + timedelta(hours=9),
                status='on_time'
            )
            act = ActivityLog(
                event_type='absentee_scheduler_run',
                title='Scheduler Run',
                detail='Ran at 9:30',
                created_at=start_of_day + timedelta(hours=9, minutes=30)
            )
            self.session.add_all([att, act])
            self.session.commit()

            with app.app.test_client() as client:
                res = client.post('/api/clear_today', json={'date': '2026-10-22'})
                self.assertEqual(res.status_code, 200)

                # Attendance should be deleted
                att_count = self.session.query(Attendance).filter(
                    Attendance.student_id == self.test_sid,
                    Attendance.date >= start_of_day,
                    Attendance.date < end_of_day
                ).count()
                self.assertEqual(att_count, 0)

                # ActivityLog for absentee_scheduler_run should NOT be deleted
                act_count = self.session.query(ActivityLog).filter(
                    ActivityLog.event_type == 'absentee_scheduler_run',
                    ActivityLog.created_at >= start_of_day,
                    ActivityLog.created_at < end_of_day
                ).count()
                self.assertEqual(act_count, count_before + 1)
        finally:
            self.session.query(Attendance).filter(
                Attendance.date >= start_of_day, Attendance.date < end_of_day
            ).delete()
            self.session.query(ActivityLog).filter(
                ActivityLog.created_at >= start_of_day, ActivityLog.created_at < end_of_day
            ).delete()
            self.session.commit()


if __name__ == '__main__':
    unittest.main()
