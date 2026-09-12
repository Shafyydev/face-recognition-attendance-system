# Face Recognition Attendance System

A local desktop attendance application that registers students from a webcam, recognizes enrolled faces in a live camera feed, and records attendance in SQLite. The user interface is a Flask dashboard displayed in a `pywebview` desktop window; the Flask app can also be run directly in a browser during development.

> This project handles biometric and attendance data. Read the [Privacy and operational notes](#privacy-and-operational-notes) before using it with real people.

## What it does

- Shows a live camera preview and reports camera/server status.
- Registers a student with an ID, name, department, year, and **five** validated webcam face samples.
- Stores 128-dimensional face embeddings as per-student JSON data and keeps a representative enrolled image.
- Runs face recognition in a separate process so camera capture and the dashboard remain responsive.
- Uses multi-frame confirmation before creating an attendance record, then prevents duplicate attendance for the same student on the same date.
- Provides attendance history, daily totals, CSV export, printable reports, activity history, and date-specific record clearing.
- Lets an operator view, edit, delete, filter, print, and export student records from the dashboard.
- Can be packaged as a Windows desktop application with PyInstaller.

## Recognition flow

1. The dashboard registration flow submits five camera frames. Each frame must contain a usable face.
2. `face_recognition` detects the largest HOG face and produces a 128-D encoding for each valid sample.
3. The application saves the embeddings in `data/face_embeddings/<student-id>.json` and one representative image in `data/known_faces/`.
4. The camera thread sends only the newest resized frame to an isolated recognition process.
5. Each live encoding is compared with all samples for each enrolled student; the best per-student distance wins.
6. A match must have a distance of at most `0.50`, an identity margin of at least `0.08`, and remain consistent for three processed frames before it is confirmed.
7. A confirmed student is written to the SQLite attendance table in a background thread. Existing attendance for that student on the current date is not duplicated.

These thresholds and the confirmation rules are implementation details, not a claim of accuracy or liveness detection.

## Technology

- Python
- Flask and Jinja templates
- `pywebview` desktop window
- OpenCV camera capture and JPEG streaming
- `face_recognition` / dlib face encodings
- NumPy
- SQLite with SQLAlchemy
- PyInstaller for Windows packaging

## Project layout

```text
attendance_system/
|-- app.py                       # Flask routes, camera loop, and dashboard APIs
|-- launcher.py                  # Desktop-window entry point
|-- database/
|   `-- models.py                # SQLite models and database-session helpers
|-- face_utils/
|   |-- attendance_marker.py     # Recognition and attendance workflow
|   |-- embedding_encoder.py     # 128-D embedding creation and matching
|   |-- face_embedding_store.py  # JSON embedding persistence
|   |-- decision_engine.py       # Multi-frame confirmation logic
|   |-- recognition_worker.py    # Isolated recognition-process target
|   |-- face_encoder.py          # Legacy OpenCV face-encoder utility
|   `-- cascade.py               # Haar-cascade path/loading helper
|-- templates/
|   |-- dashboard.html           # Attendance dashboard and student management
|   `-- register.html            # Five-sample registration flow
|-- tools/                       # Command-line helpers
|-- tests/                       # Executable recognition and decision-engine checks
|-- AttendanceSystem.spec        # PyInstaller configuration
|-- build.bat                    # Windows packaging script
`-- requirements.txt             # Python dependencies