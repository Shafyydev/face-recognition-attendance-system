import os
from sqlalchemy import create_engine, text

path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist", "AttendanceSystem", "attendance.db")

engine = create_engine("sqlite:///" + path)

with engine.connect() as conn:
    students = conn.execute(text("SELECT COUNT(*) FROM students")).scalar()
    attendance = conn.execute(text("SELECT COUNT(*) FROM attendance")).scalar()

print("Packaged EXE DB:")
print("Students:", students)
print("Attendance:", attendance)
