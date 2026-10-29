
# Face Recognition Attendance System

**A desktop-based attendance management system using real-time face recognition, Python, OpenCV, Flask, and SQLite.**

[**View Source Code →**](https://github.com/Shafyydev/face-recognition-attendance-system)

![Python](https://img.shields.io/badge/Python-3.x-3776AB?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-Web%20Framework-000000?logo=flask&logoColor=white)
![OpenCV](https://img.shields.io/badge/OpenCV-Computer%20Vision-5C3EE8?logo=opencv&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-Database-003B57?logo=sqlite&logoColor=white)
![License](https://img.shields.io/badge/License-See%20Repository-lightgrey)

---

## Overview

The Face Recognition Attendance System is a local desktop application designed to automate student attendance using webcam-based face recognition.

It allows an operator to register students, recognize enrolled faces through a live camera feed, record attendance, and manage attendance records through a dashboard.

The desktop interface is built using Flask and Jinja templates, displayed inside a `pywebview` window. The Flask application can also run directly in a web browser during development.

Attendance records are stored in SQLite, while enrolled face embeddings are maintained as per-student JSON data.

## Features

- **Face Registration** — Registers students using five validated webcam face samples.
- **Real-Time Face Recognition** — Detects and compares faces captured from a live camera feed.
- **Student Management** — View, edit, filter, and delete student records.
- **Automated Attendance** — Records attendance after a face match passes the configured confirmation rules.
- **Duplicate Prevention** — Prevents multiple attendance records for the same student on the same date.
- **Attendance History** — View historical attendance records and daily attendance totals.
- **CSV Export** — Export attendance data for external analysis.
- **Printable Reports** — Generate print-friendly attendance reports.
- **Activity History** — Maintain a record of relevant application activity.
- **Date-Specific Clearing** — Clear attendance records for a selected date.
- **Desktop Interface** — Runs in a desktop window powered by `pywebview`.
- **Background Recognition** — Uses a separate process for face recognition to help keep the dashboard responsive.
- **Windows Packaging** — Supports packaging as a Windows desktop application using PyInstaller.

## System Workflow

1. **Student Registration** — The operator enters student details, including student ID, name, department, and academic year.
2. **Face Sampling** — The application captures five webcam frames and validates that each contains a usable face.
3. **Embedding Generation** — The `face_recognition` library generates 128-dimensional face encodings from valid samples.
4. **Data Storage** — Face embeddings are saved as JSON data, with a representative enrolled image stored separately.
5. **Live Recognition** — The application processes camera frames and compares detected faces against enrolled student samples.
6. **Match Confirmation** — A candidate identity must satisfy the configured distance threshold, identity margin, and three-frame consistency requirement.
7. **Attendance Recording** — Confirmed matches are written to the SQLite attendance database in a background thread.
8. **Record Management** — Operators can review attendance history, generate reports, and export records.

## Recognition Configuration

The recognition workflow uses the following configured decision rules:

| Parameter | Configuration |
|---|---|
| Face encoding | 128-dimensional embeddings |
| Face detection | HOG-based detection |
| Maximum match distance | `0.50` |
| Minimum identity margin | `0.08` |
| Confirmation consistency | 3 processed frames |
| Registration samples | 5 webcam frames |
| Attendance storage | SQLite |
| Embedding storage | Per-student JSON files |

These are implementation settings, not guarantees of recognition accuracy. The system does not claim to provide liveness detection or protection against spoofing.

## Technology Stack

| Technology | Purpose |
|---|---|
| Python | Core application logic |
| Flask | Dashboard routes and application APIs |
| Jinja | Rendering dashboard templates |
| pywebview | Desktop application window |
| OpenCV | Camera capture and JPEG video streaming |
| face_recognition | Face detection and face encoding |
| dlib | Face-recognition model support |
| NumPy | Numerical operations |
| SQLite | Attendance data storage |
| SQLAlchemy | Database models and session management |
| PyInstaller | Windows desktop application packaging |

## Application Interface

The dashboard provides a central interface for student registration, attendance monitoring, record management, and reporting.

*Add screenshots of the registration screen, live recognition dashboard, and attendance reports here when available.*

## Privacy and Operational Notes

This application processes biometric information and student attendance data. Use it responsibly and only with appropriate authorization.

- Obtain informed consent and any required institutional approval before collecting facial data.
- Restrict access to stored face embeddings, student information, and attendance records.
- Protect local database files and embedding data against unauthorized access.
- Establish appropriate retention and deletion policies for biometric and attendance information.
- Validate the system under real operating conditions before relying on it for official attendance.
- Review incorrect matches and missed detections rather than treating automated decisions as infallible.
- Do not interpret the configured thresholds as proof of identity or liveness.

The application is designed for local operation. Its actual security depends on the deployment environment, access controls, and operational practices.

## Use Cases

- Student attendance management
- Classroom attendance automation
- Academic project demonstrations
- Computer vision and face-recognition experimentation
- Local attendance record management

## Future Improvements

Potential areas for further development include:

- Liveness detection and anti-spoofing safeguards
- Improved handling of lighting variations and camera conditions
- More comprehensive recognition evaluation and error analysis
- Role-based access control for operators
- Stronger protection for biometric data
- Automated backup and recovery for attendance records

These are potential enhancements, not claims about existing functionality.

## About the Project

This project demonstrates the application of computer vision, face recognition, database management, and desktop application development to an attendance-management workflow.

It combines a Python-based backend, webcam processing, face embeddings, a local relational database, and a dashboard interface into a single application.

## Repository

**[View the Face Recognition Attendance System on GitHub →](https://github.com/Shafyydev/face-recognition-attendance-system)**

---

**Developed by Muhammad Shafiullah N.**
