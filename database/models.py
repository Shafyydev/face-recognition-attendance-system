from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker
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


def init_db():
    engine = create_engine(
        f"sqlite:///{DB_PATH}",
        echo=False
    )

    Base.metadata.create_all(
        engine,
        checkfirst=True
    )

    return engine


_engine = None


def get_session():
    global _engine

    if _engine is None:
        _engine = init_db()

    Session = sessionmaker(bind=_engine)
    return Session()




