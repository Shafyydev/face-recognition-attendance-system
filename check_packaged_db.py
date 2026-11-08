"""
Packaged Database Inspection Utility
Inspects the SQLite database bundled with the standalone PyInstaller build
at dist/AttendanceSystem/attendance.db (or custom specified path).
"""

import os
from sqlalchemy import create_engine, text

DEFAULT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "dist",
    "AttendanceSystem",
    "attendance.db"
)
DB_PATH = os.environ.get("PACKAGED_DB_PATH", DEFAULT_PATH)


def inspect_packaged_database():
    print("=" * 60)
    print("PACKAGED EXECUTABLE DATABASE INSPECTION")
    print(f"Target Path: {DB_PATH}")
    print("=" * 60)

    if not os.path.exists(DB_PATH):
        print(f"\n[INFO] No packaged database found at: {DB_PATH}")
        print("       Build the standalone executable via build.bat first,")
        print("       or run the packaged AttendanceSystem.exe to initialize it.")
        return

    engine = create_engine(f"sqlite:///{DB_PATH}")
    try:
        with engine.connect() as conn:
            # 1. Students summary
            total_students = conn.execute(text("SELECT COUNT(*) FROM students")).scalar() or 0
            active_students = conn.execute(text("SELECT COUNT(*) FROM students WHERE is_active = 1")).scalar() or 0
            print(f"\nStudents:")
            print(f"  • Total registered : {total_students}")
            print(f"  • Active accounts  : {active_students}")
            print(f"  • Inactive accounts: {total_students - active_students}")

            # 2. Attendance summary
            total_attendance = conn.execute(text("SELECT COUNT(*) FROM attendance")).scalar() or 0
            print(f"\nAttendance Records:")
            print(f"  • Total entries    : {total_attendance}")

            status_counts = conn.execute(
                text("SELECT status, COUNT(*) FROM attendance GROUP BY status ORDER BY COUNT(*) DESC")
            ).fetchall()
            if status_counts:
                for status, count in status_counts:
                    print(f"    - {status:16}: {count}")

            # 3. Activity Log summary
            total_activities = conn.execute(text("SELECT COUNT(*) FROM activity_log")).scalar() or 0
            print(f"\nActivity Logs:")
            print(f"  • Total logged events: {total_activities}")

            recent_activities = conn.execute(
                text("SELECT event_type, COUNT(*) FROM activity_log GROUP BY event_type ORDER BY COUNT(*) DESC LIMIT 5")
            ).fetchall()
            if recent_activities:
                print("  • Top event types:")
                for ev_type, count in recent_activities:
                    print(f"    - {ev_type:24}: {count}")

        print("\n" + "=" * 60)
        print("[OK] Packaged database inspection completed.")
        print("=" * 60)

    except Exception as exc:
        print(f"\n[!] Error inspecting packaged database: {exc}")


if __name__ == "__main__":
    inspect_packaged_database()
