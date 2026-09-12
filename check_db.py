from sqlalchemy import create_engine, text

path = r"D:\codehub\attendance_system\attendance.db"

engine = create_engine("sqlite:///" + path)
with engine.connect() as conn:
    students = conn.execute(text("SELECT COUNT(*) FROM students")).scalar()
    attendance = conn.execute(text("SELECT COUNT(*) FROM attendance")).scalar()

print("Development DB:")
print("Students:", students)
print("Attendance:", attendance)
