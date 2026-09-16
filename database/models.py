from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, event
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool
from datetime import datetime
import os
import sys
def get_app_dir():
    if getattr(sys, 'frozen', False):
        app_dir = os.path.dirname(sys.executable)
    else:
        app_dir = r"D:\codehub\attendance_system"

    os.makedirs(app_dir, exist_ok=True)
    return app_dir


APP_DIR = get_app_dir()

DB_PATH = os.path.join(APP_DIR, "attendance.db")


Base = declarative_base()


class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True)
    student_id = Column(String(20), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    department = Column(String(50))
    year = Column(String(10))
    email = Column(String(100))
    student_mobile = Column(String(20), nullable=True)
    parent_mobile = Column(String(20), nullable=True)
    registered_date = Column(DateTime, default=datetime.now)
    is_active = Column(Boolean, default=True)


class ActivityLog(Base):
    __tablename__ = "activity_log"

    id = Column(Integer, primary_key=True)
    event_type = Column(String(40), nullable=False)
    title = Column(String(120), nullable=False)
    detail = Column(String(255))
    student_id = Column(String(20))
    created_at = Column(DateTime, default=datetime.now)

class Attendance(Base):
    __tablename__ = "attendance"

    id = Column(Integer, primary_key=True)
    student_id = Column(String(20), nullable=False)
    name = Column(String(100), nullable=False)
    date = Column(DateTime, default=datetime.now)
    status = Column(String(20), default="present")
    session = Column(String(50))
    late_alert_sent = Column(Boolean, default=False)


def init_db():
    engine = create_engine(
        f"sqlite:///{DB_PATH}",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=NullPool
    )

    @event.listens_for(engine, "connect")
    def set_wal_mode(dbapi_conn, _):
        """Enable WAL journal mode for safe multi-process concurrent access."""
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

    Base.metadata.create_all(
        engine,
        checkfirst=True
    )

    # Safe, non-destructive migration for newly added columns
    try:
        with engine.connect() as conn:
            # Check students table columns
            student_cols = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(students)").fetchall()]
            if "student_mobile" not in student_cols:
                conn.exec_driver_sql("ALTER TABLE students ADD COLUMN student_mobile VARCHAR(20)")
            if "parent_mobile" not in student_cols:
                conn.exec_driver_sql("ALTER TABLE students ADD COLUMN parent_mobile VARCHAR(20)")

            # Check attendance table columns
            attendance_cols = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(attendance)").fetchall()]
            if "late_alert_sent" not in attendance_cols:
                conn.exec_driver_sql("ALTER TABLE attendance ADD COLUMN late_alert_sent BOOLEAN DEFAULT 0")

            conn.commit()
    except Exception as exc:
        print(f"Database migration check error: {exc}")

    return engine


_engine = None


def get_session():
    global _engine

    if _engine is None:
        _engine = init_db()

    Session = sessionmaker(bind=_engine)
    return Session()




