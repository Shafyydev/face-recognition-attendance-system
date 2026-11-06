# Face Recognition Attendance System

**A desktop-based student attendance management system powered by real-time face recognition and computer vision.**

[**View Source Code →**](https://github.com/Shafyydev/face-recognition-attendance-system)

![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-000000?logo=flask&logoColor=white)
![OpenCV](https://img.shields.io/badge/OpenCV-5C3EE8?logo=opencv&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-003B57?logo=sqlite&logoColor=white)
![NumPy](https://img.shields.io/badge/NumPy-013243?logo=numpy&logoColor=white)

---

## Overview

The Face Recognition Attendance System is a local desktop application designed to automate student attendance using webcam-based face recognition.

Developed using Python, OpenCV, Flask, and SQLite, the application enables operators to register students, recognize enrolled faces through a live camera feed, record attendance, and manage attendance records through a centralized dashboard.

The user interface runs inside a desktop window powered by `pywebview`. The Flask application can also be opened directly in a browser during development.

## Application Preview

![Face Recognition Attendance System Dashboard](face_recognition_attendance_system%20preview.png)

*The dashboard displays attendance statistics, live camera monitoring, student records, attendance status, and recent activity.*

## Features

- **Student Registration** — Register students using their ID, name, department, academic year, and five validated webcam face samples.
- **Real-Time Face Recognition** — Detect and recognize enrolled faces from a live camera feed.
- **Automated Attendance** — Record attendance after a face match satisfies the configured confirmation rules.
- **Duplicate Prevention** — Prevent duplicate attendance records for the same student on the same date.
- **Student Management** — View, edit, filter, and delete student records.
- **Attendance History** — Review attendance records and daily attendance totals.
- **CSV Export** — Export attendance data for external analysis.
- **Printable Reports** — Generate print-friendly attendance reports.
- **Activity History** — Track relevant application activity.
- **Date-Specific Record Clearing** — Clear attendance records for a selected date.
- **Desktop Application** — Access the dashboard through a `pywebview` desktop window.
- **Background Recognition** — Run face recognition in a separate process to help keep the dashboard responsive.
- **Windows Packaging** — Package the application as a Windows desktop executable using PyInstaller.

## Getting Started

### Prerequisites

- **Python**: Version 3.10 or 3.11 recommended
- **Webcam**: Standard USB or integrated webcam
- **C++ Build Tools**: Required for `dlib` compilation (e.g., Visual Studio C++ Build Tools on Windows)

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Shafyydev/face-recognition-attendance-system.git
   cd face-recognition-attendance-system
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv venv
   # On Windows:
   .\venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment settings (optional):**
   ```bash
   copy .env.example .env    # Windows
   cp .env.example .env      # macOS/Linux
   ```

### Running the Application

- **Desktop Window (Recommended):**
  ```bash
  python launcher.py
  ```

- **Web Browser Dashboard (Development Mode):**
  ```bash
  python app.py
  ```
  Then open `http://localhost:5000` in your web browser.

### Environment Configuration

Configure optional environment variables in `.env` (copy from `.env.example`):

| Variable | Description | Default |
|---|---|---|
| `COLLEGE_NAME` | Institution name shown in SMS alerts and reports | `St.Joseph's College of Arts & Science (Autonomous) - Cuddalore` |
| `SMS_ENABLED` | Toggle automated SMS notifications (`true` / `false`) | `true` |
| `SMS_PROVIDER` | SMS delivery provider (`mock`, `sms-gate`, `textlocal`, `fast2sms`, `twilio`) | `mock` |
| `SMS_API_URL` | Android SMS Gate IP & port (auto-discovered if empty) | `http://192.168.1.100:8080` |
| `SMS_SENDER_ID` | Registered 6-character sender ID header | `STJOSEPH` |
| `ATTENDANCE_DB_PATH` | Path to the SQLite attendance database | `attendance.db` |

## How It Works

1. **Student Registration** — The operator enters the student's ID, name, department, and academic year.
2. **Face Sampling** — The application captures five webcam frames and validates that each contains a usable face.
3. **Face Encoding** — The `face_recognition` library generates 128-dimensional face embeddings from valid samples.
4. **Data Storage** — Embeddings are stored as per-student JSON data, with a representative enrolled image saved separately.
5. **Live Recognition** — The application processes camera frames and compares detected faces against enrolled student samples.
6. **Identity Confirmation** — A candidate must satisfy the configured face-distance threshold, identity margin, and three-frame consistency requirement.
7. **Attendance Recording** — Confirmed matches are written to the SQLite attendance database in a background thread.
8. **Record Management** — Operators can review attendance history, filter records, print reports, and export attendance data.

## Recognition Configuration

| Parameter | Configuration |
|---|---|
| Face encoding | 128-dimensional embeddings |
| Face detection | HOG-based detection |
| Maximum match distance | `0.50` |
| Minimum identity margin | `0.08` |
| Confirmation consistency | 3 processed frames |
| Registration samples | 5 webcam frames |
| Attendance database | SQLite |
| Embedding storage | Per-student JSON files |

These values describe the current implementation settings. They do not guarantee recognition accuracy, prove identity, or provide liveness detection.

## Technology Stack

| Technology | Purpose |
|---|---|
| Python | Core application logic |
| Flask | Dashboard routes and application APIs |
| Jinja | Rendering dashboard templates |
| pywebview | Desktop application window |
| OpenCV | Webcam capture and image processing |
| face_recognition | Face detection and face encoding |
| dlib | Face-recognition model support |
| NumPy | Numerical operations |
| SQLite | Local attendance database |
| SQLAlchemy | Database models and session management |
| PyInstaller | Windows application packaging |

## Project Structure

```text
attendance_system/
├── app.py                      # Flask web server, REST API endpoints & route handlers
├── launcher.py                 # Desktop application runner using pywebview
├── notification_service.py     # SMS alerts (SMS Gate/Twilio/Textlocal) & daily absentee scheduler
├── tts_service.py              # Asynchronous text-to-speech feedback service (pyttsx3)
├── check_db.py                 # CLI inspection tool for database counts and audit logs
├── database/
│   ├── __init__.py
│   └── models.py               # SQLAlchemy models (Student, Attendance, ActivityLog)
├── face_utils/
│   ├── attendance_marker.py    # Multi-frame streak validation and attendance logging
│   ├── cascade.py              # Haar cascade face detection loader
│   ├── decision_engine.py      # Face distance and identity margin matching engine
│   ├── embedding_encoder.py    # 128D face embedding generator and cache
│   ├── face_embedding_store.py # Persistent per-student JSON embedding storage
│   ├── liveness_detector.py    # Eye aspect ratio & blink verification logic
│   └── recognition_worker.py   # Isolated multi-processing worker for face recognition
├── templates/
│   ├── dashboard.html          # Main administrator dashboard and statistics UI
│   └── register.html           # 5-sample guided student face enrollment interface
├── tests/                      # Automated test suite (date handling, SMS, decision engine)
├── tools/                      # Standalone CLI tools for registration and runners
├── requirements.txt            # Python dependencies
└── .env.example                # Environment configuration template
```

## Key Capabilities

The application combines computer vision, database management, and desktop interface development in a single attendance workflow.

- Webcam-based student registration and identification
- Multi-frame identity confirmation
- Local storage of attendance records
- Student and attendance record management
- CSV exports and printable reports
- Separate recognition processing to help maintain dashboard responsiveness

## Privacy and Security

This application processes biometric information and student attendance data. Appropriate safeguards are necessary before using it with real students.

- Obtain informed consent and any required institutional authorization before collecting facial data.
- Restrict access to stored face embeddings, student details, and attendance records.
- Protect local database files and embedding data against unauthorized access.
- Establish appropriate retention and deletion policies.
- Evaluate false matches and missed detections before relying on the system for official attendance.
- Do not treat automated recognition as infallible.
- Do not assume the configured thresholds prevent spoofing or guarantee identity.

The application is designed for local operation. Its actual security depends on the deployment environment, access controls, and operational practices.

## Potential Improvements

- Liveness detection and anti-spoofing safeguards
- Recognition evaluation under different lighting and camera conditions
- More comprehensive false-positive and false-negative analysis
- Role-based access control for operators
- Stronger protection for biometric data
- Automated backup and recovery for attendance records

These are potential enhancements, not claims about existing functionality.

## About the Developer

**Shafiullah** is a B.Sc. Artificial Intelligence student interested in software development, computer vision, and practical AI applications.

This project demonstrates the application of Python, face recognition, database management, and desktop application development to a real-world attendance management problem.

## Repository

**[Explore the Face Recognition Attendance System on GitHub →](https://github.com/Shafyydev/face-recognition-attendance-system)**

---

**Developed by Mohammed Shafiullah N**
