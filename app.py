import sys
import os
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, render_template, Response, jsonify, request
from flask_cors import CORS
from database.models import get_session, Student, Attendance, ActivityLog, DB_PATH
import cv2
import numpy as np
from datetime import datetime, timedelta
from face_utils.attendance_marker import AttendanceMarker
from face_utils.cascade import load_face_cascade
import time
import threading
import multiprocessing
import csv
import io

# Resolve template folder for frozen exe
if getattr(sys, 'frozen', False):
    template_folder = os.path.join(sys._MEIPASS, 'templates')
else:
    template_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')

app = Flask(__name__, template_folder=template_folder)


CORS(app)

latest_attendance = []
def log_activity(event_type, title, detail="", student_id=None):
    """Persist one activity event in the daily activity log."""
    session = get_session()

    try:
        activity = ActivityLog(
            event_type=str(event_type),
            title=str(title),
            detail=str(detail or ""),
            student_id=(
                str(student_id)
                if student_id is not None
                else None
            ),
            created_at=datetime.now(),
        )

        session.add(activity)
        session.commit()

    except Exception as exc:
        print(f"Activity log error: {exc}")

    finally:
        session.close()


attendance_system = AttendanceMarker()
camera_lock = threading.Lock()
latest_jpeg = None
latest_raw_frame = None
camera_info = {'ok': False, 'message': 'Camera starting...'}
_camera_thread = None

# Separate OS process for face recognition.
_recognition_process = None
_recognition_input_queue = None
_recognition_output_queue = None
_recognition_command_queue = None
_recognition_stop_event = None

# Latest recognition result received by the camera thread.
_recognition_result_lock = threading.Lock()
_latest_recognition_results = []
_latest_recognition_frame_id = -1
_latest_recognition_time = 0.0


def placeholder_frame(message):
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    frame[:] = (12, 8, 18)
    cv2.putText(frame, message, (40, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    return frame


def encode_jpeg(frame):
    ok, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return buffer.tobytes() if ok else None


def open_camera():
    backends = []
    if os.name == 'nt':
        backends = [
            ('DirectShow', cv2.CAP_DSHOW),
            ('MSMF', cv2.CAP_MSMF),
            ('ANY', cv2.CAP_ANY),
        ]
    else:
        backends = [('ANY', cv2.CAP_ANY)]

    for index in range(3):
        for name, backend in backends:
            cap = cv2.VideoCapture(index, backend)
            if not cap.isOpened():
                cap.release()
                continue
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            ok = False
            frame = None
            for _ in range(12):
                ok, frame = cap.read()
                if ok and frame is not None and getattr(frame, 'size', 0) > 0:
                    print(f"Camera opened ({name}, index {index})")
                    return cap
                time.sleep(0.05)
            print(f"Opened but no frames ({name}, index {index})")
            cap.release()
    return None


def recognition_loop():
    """
    Compatibility placeholder.

    Face recognition is now handled by the isolated
    recognition_process_worker in face_utils.recognition_worker.
    """
    return


def start_recognition_process():
    global _recognition_process
    global _recognition_input_queue
    global _recognition_output_queue
    global _recognition_command_queue
    global _recognition_stop_event

    from face_utils.recognition_worker import recognition_process_worker

    if (
        _recognition_process is not None
        and _recognition_process.is_alive()
    ):
        return

    _recognition_input_queue = multiprocessing.Queue(maxsize=1)
    _recognition_output_queue = multiprocessing.Queue(maxsize=4)
    _recognition_command_queue = multiprocessing.Queue(maxsize=8)
    _recognition_stop_event = multiprocessing.Event()

    _recognition_process = multiprocessing.Process(
        target=recognition_process_worker,
        args=(
            _recognition_input_queue,
            _recognition_output_queue,
            _recognition_command_queue,
            _recognition_stop_event
        ),
        daemon=True,
        name='RecognitionProcess'
    )

    _recognition_process.start()

    print('Recognition process started')

def camera_loop():
    global latest_jpeg
    global latest_raw_frame
    global _recognition_frame
    global _latest_recognition_results
    global _latest_recognition_frame_id
    global _latest_recognition_time

    fail_streak = 0
    cap = None
    frame_id = 0

    while True:

        if cap is None:
            camera_info['ok'] = False
            camera_info['message'] = 'Looking for camera...'

            jpeg = encode_jpeg(
                placeholder_frame('Looking for camera...')
            )

            with camera_lock:
                latest_jpeg = jpeg

            cap = open_camera()

            if cap is None:
                camera_info['message'] = (
                    'Camera not found. Close other apps using it, '
                    'then retry.'
                )

                jpeg = encode_jpeg(
                    placeholder_frame('Camera not found')
                )

                with camera_lock:
                    latest_jpeg = jpeg

                time.sleep(2)
                continue

            fail_streak = 0
            camera_info['ok'] = True
            camera_info['message'] = 'Live'

            print('Camera connected')

        # ----------------------------------------------------
        # FAST CAMERA CAPTURE
        # ----------------------------------------------------

        ok, frame = cap.read()

        if not ok or frame is None:
            fail_streak += 1

            if fail_streak >= 15:
                print('Camera read failed, reconnecting...')
                cap.release()
                cap = None

            time.sleep(0.005)
            continue

        fail_streak = 0

        # Preserve normal, non-mirrored preview.
        frame = cv2.flip(frame, 1)

        frame_id += 1

        # Keep the newest raw frame for registration.
        latest_raw_frame = frame.copy()

        # ----------------------------------------------------
        # ISOLATED RECOGNITION HANDOFF
        # ----------------------------------------------------
        # Camera/display remains independent.
        # Recognition receives only the newest small frame.
        # Queue size is one, so old frames are discarded.
        recognition_interval = 0.25

        current_time = time.perf_counter()

        if (
            _recognition_input_queue is not None
            and (
                not hasattr(camera_loop, '_last_recognition_submit')
                or current_time - camera_loop._last_recognition_submit >= recognition_interval
            )
        ):
            camera_loop._last_recognition_submit = current_time

            recognition_frame = cv2.resize(
                frame,
                (320, 240),
                interpolation=cv2.INTER_AREA
            )

            try:
                while True:
                    _recognition_input_queue.get_nowait()
            except Exception:
                pass

            try:
                _recognition_input_queue.put_nowait(
                    (frame_id, recognition_frame)
                )
            except Exception:
                pass

        # ----------------------------------------------------
        # RECEIVE LATEST RECOGNITION RESULT
        # ----------------------------------------------------
        if _recognition_output_queue is not None:

            while True:
                try:
                    result_frame_id, results = (
                        _recognition_output_queue.get_nowait()
                    )
                except Exception:
                    break

                with _recognition_result_lock:
                    # Keep the last valid recognition result.
                    # AttendanceMarker intentionally returns [] on frames
                    # that are skipped by its processing interval.
                    _latest_recognition_frame_id = result_frame_id

                    if results:
                        _latest_recognition_results = results
                        _latest_recognition_time = time.perf_counter()

                        for result in results:
                            if result.get('status') == 'marked':
                                log_activity(
                                    'attendance_marked',
                                    'Attendance marked',
                                    f"{result.get('name', 'Unknown')} ({result.get('student_id', '')})",
                                    result.get('student_id')
                                )

        # ----------------------------------------------------
        # RECOGNITION OVERLAY
        # ----------------------------------------------------
        # Recognition runs at low resolution in the separate
        # process. Its latest result is scaled back onto the
        # full-resolution camera frame.
        #
        # The camera never waits for recognition.
        # The latest result is retained briefly so the box
        # remains visually stable between recognition frames.

        overlay_results = []
        overlay_age = 0.0

        with _recognition_result_lock:
            if _latest_recognition_results:
                overlay_results = list(_latest_recognition_results)
                overlay_age = (
                    time.perf_counter() - _latest_recognition_time
                )

        if overlay_results and overlay_age <= 0.75:

            for result in overlay_results:

                box = result.get('box')

                if not box or len(box) != 4:
                    continue

                left, top, right, bottom = box

                # Recognition frame is 320x240.
                # Camera/display frame is 640x480.
                left = int(left * 2)
                top = int(top * 2)
                right = int(right * 2)
                bottom = int(bottom * 2)

                left = max(0, min(frame.shape[1] - 1, left))
                right = max(0, min(frame.shape[1] - 1, right))
                top = max(0, min(frame.shape[0] - 1, top))
                bottom = max(0, min(frame.shape[0] - 1, bottom))

                status = result.get('status', '')
                name = result.get('name', 'Unknown')

                cv2.rectangle(
                    frame,
                    (left, top),
                    (right, bottom),
                    (0, 255, 0),
                    2
                )

                label = name

                if status == 'confirming':
                    label = f'{name} - Confirming'
                elif status == 'marked':
                    label = f'{name} - Present'

                cv2.putText(
                    frame,
                    label,
                    (left, max(25, top - 10)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.65,
                    (0, 255, 0),
                    2,
                    cv2.LINE_AA
                )

        # ----------------------------------------------------
        # FAST PREVIEW
        # ----------------------------------------------------

        jpeg = encode_jpeg(frame)

        if jpeg:
            with camera_lock:
                latest_jpeg = jpeg

        # No 30 FPS artificial delay.
        # The camera/backend is allowed to run at its maximum rate.
        time.sleep(0.001)


def ensure_camera_thread():
    global _camera_thread

    start_recognition_process()

    if (
        _camera_thread is None
        or not _camera_thread.is_alive()
    ):
        _camera_thread = threading.Thread(
            target=camera_loop,
            daemon=True,
            name='CameraWorker'
        )
        _camera_thread.start()

@app.route('/')
def index():
    ensure_camera_thread()

    # Tell the recognition worker the dashboard is now active.
    # It will wait 3 seconds before marking any student present,
    # so a newly registered student has time to leave the register
    # page and stand in front of the camera naturally.
    if _recognition_command_queue is not None:
        try:
            _recognition_command_queue.put_nowait('release')
        except Exception:
            pass

    session = get_session()

    try:
        students = session.query(Student).order_by(
            Student.student_id.asc()
        ).all()

        student_data = [{
            'student_id': student.student_id,
            'name': student.name,
            'department': student.department or 'N/A',
            'year': student.year or 'N/A',
            'student_mobile': student.student_mobile or '',
            'parent_mobile': student.parent_mobile or '',
            'is_active': student.is_active,
        } for student in students]

    finally:
        session.close()

    return render_template(
        'dashboard.html',
        initial_students=student_data
    )



@app.route('/api/status')
def get_status():
    ensure_camera_thread()
    return jsonify({
        'status': 'online',
        'camera': camera_info.get('ok', False),
        'camera_message': camera_info.get('message', ''),
    })

@app.route('/api/recognition_status')
def recognition_status():
    """Return the latest confirmed recognition results for the dashboard."""
    with _recognition_result_lock:
        results = list(_latest_recognition_results)
        result_time = _latest_recognition_time

    age = (
        time.perf_counter() - result_time
        if result_time > 0
        else 999.0
    )

    # Do not expose stale recognition results.
    if age > 3.0:
        results = []

    already_present = [
        {
            'student_id': result.get('student_id'),
            'name': result.get('name'),
            'status': result.get('status'),
        }
        for result in results
        if result.get('status') == 'already_present'
    ]

    return jsonify({
        'already_present': already_present
    })

@app.route('/api/activity')
def get_activity():
    """Return today's persistent activity history."""
    session = get_session()

    try:
        today = datetime.now().date()
        start = datetime.combine(today, datetime.min.time())
        end = start + timedelta(days=1)

        records = session.query(ActivityLog).filter(
            ActivityLog.created_at >= start,
            ActivityLog.created_at < end
        ).order_by(
            ActivityLog.created_at.desc(),
            ActivityLog.id.desc()
        ).all()

        return jsonify([
            {
                'id': record.id,
                'event_type': record.event_type,
                'title': record.title,
                'detail': record.detail or '',
                'student_id': record.student_id,
                'time': record.created_at.strftime('%I:%M:%S %p'),
            }
            for record in records
        ])

    finally:
        session.close()

@app.route('/api/attendance')
def get_attendance():
    session = get_session()
    date_str = request.args.get('date')
    if date_str:
        try:
            today = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            today = datetime.now().date()
    else:
        today = datetime.now().date()
    start = datetime.combine(today, datetime.min.time())
    end = start + timedelta(days=1)
    records = session.query(Attendance).filter(Attendance.date >= start, Attendance.date < end).order_by(Attendance.id.asc()).all()
    attendance_list = []
    for att in records:
        student = session.query(Student).filter(Student.student_id == att.student_id).first()
        attendance_list.append({
            'student_id': att.student_id,
            'name': att.name,
            'department': student.department if student else 'N/A',
            'year': student.year if student else 'N/A',
            'status': att.status,
            'time': att.date.strftime('%I:%M:%S %p')
        })
    session.close()
    return jsonify(attendance_list)

@app.route('/api/stats')
def get_stats():
    session = get_session()
    date_str = request.args.get('date')
    if date_str:
        try:
            today = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            today = datetime.now().date()
    else:
        today = datetime.now().date()
    start = datetime.combine(today, datetime.min.time())
    end = start + timedelta(days=1)
    total = session.query(Student).filter(Student.is_active == True).count()
    present = session.query(Attendance).filter(Attendance.date >= start, Attendance.date < end, Attendance.status.in_(['on_time', 'late', 'present'])).count()
    late = session.query(Attendance).filter(Attendance.date >= start, Attendance.date < end, Attendance.status == 'late').count()
    absent = max(0, total - present)
    percent = (present / total * 100) if total > 0 else 0
    session.close()
    return jsonify({'total': total, 'present': present, 'late': late, 'absent': absent, 'percent': percent})

@app.route('/api/clear_today', methods=['POST'])
def clear_today():
    global latest_attendance

    # Read the date currently selected in the dashboard.
    data = request.get_json(silent=True) or {}
    date_str = data.get('date')

    if date_str:
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            target_date = datetime.now().date()
    else:
        target_date = datetime.now().date()

    # Reset live recognition state so new attendance can be marked immediately
    attendance_system.reset()

    # Clear cached recognition results so stale 'already_present' status drops immediately
    with _recognition_result_lock:
        _latest_recognition_results = []
        _latest_recognition_time = 0.0

    # Reset and unfreeze the separate recognition process
    if _recognition_command_queue is not None:
        try:
            _recognition_command_queue.put_nowait("reset")
            _recognition_command_queue.put_nowait("release")
            print("Recognition process reset & release command sent")
        except Exception as exc:
            print(f"Recognition process reset command failed: {exc}")

    # Drain any stale recognition output from the queue
    if _recognition_output_queue is not None:
        try:
            while True:
                _recognition_output_queue.get_nowait()
        except Exception:
            pass

    session = get_session()
    start = datetime.combine(target_date, datetime.min.time())
    end = start + timedelta(days=1)

    deleted = session.query(Attendance).filter(
        Attendance.date >= start,
        Attendance.date < end
    ).delete()

    session.commit()
    session.close()

    latest_attendance.clear()

    log_activity(
        'attendance_cleared',
        'Attendance records cleared',
        f"{deleted} attendance record(s) were cleared"
    )

    print(f"Cleared {deleted} records for {target_date} and reset memory")
    return jsonify({'message': f'Cleared {deleted} records'})

@app.route('/api/attendance/export')
def export_attendance_csv():
    date_str = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except:
        target_date = datetime.now().date()
    
    session = get_session()
    records = session.query(Attendance).filter(Attendance.date >= target_date).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Student ID', 'Name', 'Department', 'Year', 'Status', 'Date', 'Time'])
    for att in records:
        student = session.query(Student).filter(Student.student_id == att.student_id).first()
        writer.writerow([att.student_id, att.name, student.department if student else 'N/A', 
                        student.year if student else 'N/A', att.status, 
                        att.date.strftime('%Y-%m-%d'), att.date.strftime('%I:%M:%S %p')])
    session.close()
    output.seek(0)
    return Response(output.getvalue(), mimetype='text/csv',
                   headers={'Content-Disposition': f'attachment; filename=attendance_{date_str}.csv'})

def generate_frames():
    ensure_camera_thread()
    offline = encode_jpeg(placeholder_frame('Starting camera...'))
    while True:
        with camera_lock:
            jpeg = latest_jpeg or offline
        yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + jpeg + b'\r\n')
        time.sleep(0.0167)  # ~30fps

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

def generate_registration_frames():
    """
    Clean registration camera feed.

    Shows the live camera with only a green face-positioning
    rectangle. It deliberately does NOT display recognition
    names, statuses, or attendance information.
    """
    ensure_camera_thread()

    cascade = load_face_cascade()
    last_box = None
    last_detection_time = 0.0

    while True:
        with camera_lock:
            frame = (
                latest_raw_frame.copy()
                if latest_raw_frame is not None
                else None
            )

        if frame is None:
            time.sleep(0.02)
            continue

        current_time = time.perf_counter()

        # Face detection is lightweight and independent of the
        # recognition worker.
        if current_time - last_detection_time >= 0.10:
            last_detection_time = current_time

            try:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

                faces = cascade.detectMultiScale(
                    gray,
                    scaleFactor=1.1,
                    minNeighbors=5,
                    minSize=(60, 60)
                )

                if len(faces) > 0:
                    # Use the largest detected face.
                    x, y, w, h = max(
                        faces,
                        key=lambda box: box[2] * box[3]
                    )
                    last_box = (x, y, w, h)
                else:
                    last_box = None

            except Exception:
                last_box = None

        if last_box is not None:
            x, y, w, h = last_box

            cv2.rectangle(
                frame,
                (x, y),
                (x + w, y + h),
                (0, 255, 0),
                2
            )

        jpeg = encode_jpeg(frame)

        if jpeg:
            yield (
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n'
                + jpeg
                + b'\r\n'
            )

        time.sleep(0.01)


@app.route('/registration_feed')
def registration_feed():
    return Response(
        generate_registration_frames(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )

@app.route('/api/capture_frame')
def capture_frame():
    """Capture the current camera frame and return as JPEG for registration preview."""
    with camera_lock:
        jpeg = latest_jpeg
    if jpeg:
        return Response(jpeg, mimetype='image/jpeg')
    return jsonify({'error': 'No frame available'}), 503

@app.route('/api/students')
def get_students():
    """Return list of all registered students."""
    session = get_session()
    students = session.query(Student).order_by(Student.student_id.asc()).all()
    result = [{
        'student_id': s.student_id,
        'name': s.name,
        'department': s.department or 'N/A',
        'year': s.year or 'N/A',
        'student_mobile': s.student_mobile or '',
        'parent_mobile': s.parent_mobile or '',
        'is_active': s.is_active,
    } for s in students]
    session.close()
    return jsonify(result)

@app.route('/api/students/<student_id>', methods=['DELETE'])
def delete_student(student_id):
    """Permanently delete a student and all associated data."""
    student_id = str(student_id or '').strip()

    if not student_id:
        return jsonify({
            'error': 'Student ID is required'
        }), 400

    session = get_session()

    try:
        # Make the current attendance generation obsolete.
        # This cancels any pending background attendance write
        # created before the deletion started.
        attendance_system.reset()

        student = session.query(Student).filter(
            Student.student_id == student_id
        ).first()

        if student is None:
            return jsonify({
                'error': f'Student {student_id} not found'
            }), 404

        # ----------------------------------------------------------
        # 1. Delete every attendance record belonging to this ID.
        # ----------------------------------------------------------
        attendance_deleted = session.query(Attendance).filter(
            Attendance.student_id == student_id
        ).delete(synchronize_session=False)

        # ----------------------------------------------------------
        # 2. Delete the Student database record.
        # ----------------------------------------------------------
        session.delete(student)
        session.commit()

        log_activity(
            'student_deleted',
            'Student deleted',
            f"{student_id} and all associated data",
            student_id
        )

        # ----------------------------------------------------------
        # 3. Delete persistent face embeddings.
        # ----------------------------------------------------------
        embedding_deleted = False

        try:
            embedding_deleted = (
                attendance_system.embedding_store.delete_student(
                    student_id
                )
            )
        except Exception as exc:
            print(
                f"Warning: could not delete embedding file "
                f"for {student_id}: {exc}"
            )

        # ----------------------------------------------------------
        # 4. Remove every known-face image belonging to this ID.
        # ----------------------------------------------------------
        known_faces_deleted = 0

        known_faces_dir = (
            attendance_system.embedding_encoder.known_faces_dir
        )

        if os.path.isdir(known_faces_dir):
            prefix = f"{student_id}_"

            for filename in os.listdir(known_faces_dir):
                if not filename.startswith(prefix):
                    continue

                file_path = os.path.join(
                    known_faces_dir,
                    filename
                )

                if os.path.isfile(file_path):
                    try:
                        os.remove(file_path)
                        known_faces_deleted += 1
                    except Exception as exc:
                        print(
                            f"Warning: could not delete known face "
                            f"{file_path}: {exc}"
                        )

        # ----------------------------------------------------------
        # 5. Remove the student from the live recognition encoder.
        # ----------------------------------------------------------
        attendance_system.embedding_encoder.known_embeddings.pop(
            student_id,
            None
        )

        # Keep legacy encoder state clean if it contains this ID.
        if hasattr(attendance_system, 'face_encoder'):
            try:
                attendance_system.face_encoder.load_known_faces()
            except Exception:
                pass

        # ----------------------------------------------------------
        # 6. Tell the separate recognition process to reload.
        # ----------------------------------------------------------
        if _recognition_command_queue is not None:
            try:
                _recognition_command_queue.put_nowait("reload")
                print(
                    "Recognition process reload command sent "
                    f"after deleting {student_id}"
                )
            except Exception as exc:
                print(
                    f"Recognition process reload command failed: {exc}"
                )

        print(
            f"Deleted student completely: {student_id} | "
            f"attendance={attendance_deleted} | "
            f"embedding={embedding_deleted} | "
            f"known_faces={known_faces_deleted}"
        )

        return jsonify({
            'success': True,
            'student_id': student_id,
            'attendance_deleted': attendance_deleted,
            'embedding_deleted': embedding_deleted,
            'known_faces_deleted': known_faces_deleted
        })

    except Exception as exc:
        session.rollback()

        print(
            f"Student deletion failed for {student_id}: {exc}"
        )

        return jsonify({
            'error': f'Could not delete student: {str(exc)}'
        }), 500

    finally:
        session.close()

@app.route('/api/students/<student_id>', methods=['PUT'])
def update_student(student_id):
    """Update student information and synchronize all student identifiers."""
    old_student_id = str(student_id or '').strip()

    if not old_student_id:
        return jsonify({
            'error': 'Student ID is required'
        }), 400

    data = request.get_json(silent=True) or {}

    new_student_id = str(
        data.get('student_id', old_student_id)
    ).strip()

    name = str(
        data.get('name', '')
    ).strip()

    department = str(
        data.get('department', '')
    ).strip()

    year = str(
        data.get('year', '')
    ).strip()

    if not new_student_id or not name:
        return jsonify({
            'error': 'Student ID and Name are required'
        }), 400

    if len(new_student_id) > 20:
        return jsonify({
            'error': 'Student ID must be 20 characters or fewer'
        }), 400

    if len(name) > 100:
        return jsonify({
            'error': 'Name must be 100 characters or fewer'
        }), 400

    if len(department) > 50:
        return jsonify({
            'error': 'Department must be 50 characters or fewer'
        }), 400

    if len(year) > 10:
        return jsonify({
            'error': 'Year must be 10 characters or fewer'
        }), 400

    session = get_session()

    try:
        student = session.query(Student).filter(
            Student.student_id == old_student_id
        ).first()

        if student is None:
            return jsonify({
                'error': f'Student {old_student_id} not found'
            }), 404

        if new_student_id != old_student_id:
            duplicate = session.query(Student).filter(
                Student.student_id == new_student_id
            ).first()

            if duplicate is not None:
                return jsonify({
                    'error': f'Student ID {new_student_id} is already in use'
                }), 409

        # Stop any pending attendance operation from using
        # the old student identity while the update is performed.
        attendance_system.reset()

        old_embedding_path = os.path.join(
            attendance_system.embedding_store.storage_dir,
            f'{old_student_id}.json'
        )

        new_embedding_path = os.path.join(
            attendance_system.embedding_store.storage_dir,
            f'{new_student_id}.json'
        )

        old_known_faces_dir = (
            attendance_system.embedding_encoder.known_faces_dir
        )

        known_face_files = []

        if os.path.isdir(old_known_faces_dir):
            prefix = f'{old_student_id}_'

            for filename in os.listdir(old_known_faces_dir):
                if filename.startswith(prefix):
                    file_path = os.path.join(
                        old_known_faces_dir,
                        filename
                    )

                    if os.path.isfile(file_path):
                        known_face_files.append(file_path)

        # If the ID changes, make sure the target embedding path
        # does not already exist outside the database.
        if (
            new_student_id != old_student_id
            and os.path.exists(new_embedding_path)
        ):
            return jsonify({
                'error': (
                    f'Face embedding data for {new_student_id} '
                    f'already exists'
                )
            }), 409

        # Capture old values before overwriting for the activity log.
        old_name = student.name or ''
        old_department = student.department or ''
        old_year = student.year or ''
        old_student_mobile = student.student_mobile or ''
        old_parent_mobile = student.parent_mobile or ''

        # Mobile validation and update
        from notification_service import normalize_indian_mobile

        student_mobile_raw = data.get('student_mobile')
        if student_mobile_raw is not None and str(student_mobile_raw).strip():
            is_valid, num = normalize_indian_mobile(str(student_mobile_raw))
            if not is_valid:
                return jsonify({'error': 'Student mobile must be a valid 10-digit Indian number'}), 400
            student.student_mobile = num
        elif student_mobile_raw is not None and not str(student_mobile_raw).strip():
            student.student_mobile = None

        parent_mobile_raw = data.get('parent_mobile')
        if parent_mobile_raw is not None and str(parent_mobile_raw).strip():
            is_valid, num = normalize_indian_mobile(str(parent_mobile_raw))
            if not is_valid:
                return jsonify({'error': 'Parent mobile must be a valid 10-digit Indian number'}), 400
            student.parent_mobile = num
        elif parent_mobile_raw is not None and not str(parent_mobile_raw).strip():
            student.parent_mobile = None

        # Update the Student row.
        student.student_id = new_student_id
        student.name = name
        student.department = department or None
        student.year = year or None

        # Keep every historical attendance record synchronized.
        if new_student_id != old_student_id:
            session.query(Attendance).filter(
                Attendance.student_id == old_student_id
            ).update(
                {
                    Attendance.student_id: new_student_id,
                    Attendance.name: name,
                },
                synchronize_session=False
            )
        else:
            session.query(Attendance).filter(
                Attendance.student_id == old_student_id
            ).update(
                {
                    Attendance.name: name,
                },
                synchronize_session=False
            )

        session.commit()

        # Build a human-readable summary of what actually changed.
        changes = []
        if new_student_id != old_student_id:
            changes.append(f"ID: {old_student_id} \u2192 {new_student_id}")
        if name != old_name:
            changes.append(f"Name: {old_name} \u2192 {name}")
        if (department or '') != old_department:
            changes.append(f"Department: {old_department or 'N/A'} \u2192 {department or 'N/A'}")
        if (year or '') != old_year:
            changes.append(f"Year: {old_year or 'N/A'} \u2192 {year or 'N/A'}")
        if (student.student_mobile or '') != old_student_mobile:
            changes.append(f"Student Mobile: {old_student_mobile or 'N/A'} \u2192 {student.student_mobile or 'N/A'}")
        if (student.parent_mobile or '') != old_parent_mobile:
            changes.append(f"Parent Mobile: {old_parent_mobile or 'N/A'} \u2192 {student.parent_mobile or 'N/A'}")

        detail = ' | '.join(changes) if changes else 'No changes'

        log_activity(
            'student_edited',
            'Student information edited',
            detail,
            new_student_id
        )

        # Rename/update the persistent face embedding data.
        embedding_updated = False

        if os.path.exists(old_embedding_path):
            with open(
                old_embedding_path,
                'r',
                encoding='utf-8'
            ) as file:
                embedding_data = json.load(file)

            embedding_data['student_id'] = new_student_id
            embedding_data['name'] = name

            temporary_embedding_path = new_embedding_path + '.tmp'

            with open(
                temporary_embedding_path,
                'w',
                encoding='utf-8'
            ) as file:
                json.dump(
                    embedding_data,
                    file,
                    indent=2
                )

            os.replace(
                temporary_embedding_path,
                new_embedding_path
            )

            if new_embedding_path != old_embedding_path:
                os.remove(old_embedding_path)

            embedding_updated = True

        # Rename known-face files so recognition continues using
        # the new Student ID and current name.
        known_faces_updated = 0

        safe_name = (
            name
            .replace('/', '_')
            .replace('\\', '_')
        )

        for old_file_path in known_face_files:
            new_file_path = os.path.join(
                old_known_faces_dir,
                f'{new_student_id}_{safe_name}.jpg'
            )

            if os.path.abspath(old_file_path) == os.path.abspath(new_file_path):
                known_faces_updated += 1
                continue

            if os.path.exists(new_file_path):
                raise RuntimeError(
                    f'Known-face target already exists: {new_file_path}'
                )

            os.replace(
                old_file_path,
                new_file_path
            )

            known_faces_updated += 1

        # Reload the persistent embedding cache.
        attendance_system.embedding_encoder.known_embeddings = (
            attendance_system.embedding_store.load_all()
        )

        if _recognition_command_queue is not None:
            try:
                _recognition_command_queue.put_nowait('reload')
                print(
                    'Recognition process reload command sent '
                    f'after updating {old_student_id} -> {new_student_id}'
                )
            except Exception as exc:
                print(
                    f'Recognition process reload command failed: {exc}'
                )

        print(
            f'Updated student: {old_student_id} -> {new_student_id} | '
            f'name={name} | '
            f'embedding={embedding_updated} | '
            f'known_faces={known_faces_updated}'
        )

        return jsonify({
            'success': True,
            'old_student_id': old_student_id,
            'student_id': new_student_id,
            'name': name,
            'department': department,
            'year': year,
            'student_mobile': student.student_mobile or '',
            'parent_mobile': student.parent_mobile or '',
            'embedding_updated': embedding_updated,
            'known_faces_updated': known_faces_updated
        })

    except Exception as exc:
        session.rollback()

        print(
            f'Student update failed for {old_student_id}: {exc}'
        )

        return jsonify({
            'error': f'Could not update student: {str(exc)}'
        }), 500

    finally:
        session.close()

@app.route('/api/register', methods=['POST'])
def register_student():
    """Register a new student using five camera samples and face embeddings."""
    import base64

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    student_id = data.get('student_id', '').strip()
    name = data.get('name', '').strip()
    department = data.get('department', '').strip()
    year = data.get('year', '').strip()
    student_mobile_raw = data.get('student_mobile', '').strip()
    parent_mobile_raw = data.get('parent_mobile', '').strip()
    frames_data = data.get('frames')

    if not student_id or not name:
        return jsonify({'error': 'Student ID and Name are required'}), 400

    from notification_service import normalize_indian_mobile

    normalized_student_mobile = None
    if student_mobile_raw:
        is_valid, num = normalize_indian_mobile(student_mobile_raw)
        if not is_valid:
            return jsonify({'error': 'Invalid Student Mobile Number. Please enter a valid 10-digit Indian mobile number.'}), 400
        normalized_student_mobile = num

    normalized_parent_mobile = None
    if parent_mobile_raw:
        is_valid, num = normalize_indian_mobile(parent_mobile_raw)
        if not is_valid:
            return jsonify({'error': 'Invalid Parent Mobile Number. Please enter a valid 10-digit Indian mobile number.'}), 400
        normalized_parent_mobile = num

    if not isinstance(frames_data, list) or len(frames_data) != 5:
        return jsonify({'error': 'Exactly 5 face samples are required'}), 400

    # Check if student already exists.
    session = get_session()
    existing = session.query(Student).filter(
        Student.student_id == student_id
    ).first()

    if existing:
        session.close()
        return jsonify({
            'error': f'Student {student_id} already registered'
        }), 409

    embeddings = []
    decoded_frames = []

    try:
        # Decode and validate every submitted frame first.
        for index, frame_data in enumerate(frames_data, start=1):
            if not isinstance(frame_data, str) or not frame_data:
                raise ValueError(
                    f'Sample {index}: invalid frame data'
                )

            try:
                encoded = (
                    frame_data.split(',', 1)[1]
                    if ',' in frame_data
                    else frame_data
                )

                img_bytes = base64.b64decode(
                    encoded,
                    validate=True
                )

                nparr = np.frombuffer(
                    img_bytes,
                    np.uint8
                )

                frame = cv2.imdecode(
                    nparr,
                    cv2.IMREAD_COLOR
                )

            except Exception:
                raise ValueError(
                    f'Sample {index}: could not decode image'
                )

            if frame is None:
                raise ValueError(
                    f'Sample {index}: could not decode image'
                )

            embedding = attendance_system.embedding_encoder.encode_frame(
                frame
            )

            if embedding is None:
                raise ValueError(
                    f'Sample {index}: no usable face detected'
                )

            embeddings.append(embedding)
            decoded_frames.append(frame)

        # All five samples are valid at this point.
        # Save persistent embeddings only after validation succeeds.
        attendance_system.embedding_store.save_student(
            student_id,
            name,
            embeddings
        )

        # Keep one representative image for compatibility,
        # backup/visual reference, and legacy known-face migration.
        known_faces_dir = attendance_system.embedding_encoder.known_faces_dir
        os.makedirs(known_faces_dir, exist_ok=True)

        safe_name = name.replace('/', '_').replace('\\', '_')
        representative_path = os.path.join(
            known_faces_dir,
            f'{student_id}_{safe_name}.jpg'
        )

        if not cv2.imwrite(
            representative_path,
            decoded_frames[0]
        ):
            raise RuntimeError(
                'Could not save representative face image'
            )

        # Add all five embeddings to the live recognition engine
        # so recognition works immediately without restarting.
        for embedding in embeddings:
            attendance_system.embedding_encoder.add_embedding(
                student_id,
                name,
                embedding
            )

        # Only create the database record after all face data
        # has been successfully prepared.
        student = Student(
            student_id=student_id,
            name=name,
            department=department,
            year=year,
            student_mobile=normalized_student_mobile,
            parent_mobile=normalized_parent_mobile,
        )

        session.add(student)
        session.commit()

        log_activity(
            'student_registered',
            'Student registered',
            f"{name} ({student_id})",
            student_id
        )

        # The face embeddings are now saved and added to the
        # parent process. Tell the separate recognition process
        # to reload its embedding database immediately.
        if _recognition_command_queue is not None:
            try:
                _recognition_command_queue.put_nowait("reload")
                print("Recognition process reload command sent after registration")
            except Exception as exc:
                print(f"Recognition process reload command failed: {exc}")

    except ValueError as exc:
        session.rollback()

        # Remove any embedding file that may have been created.
        try:
            attendance_system.embedding_store.delete_student(
                student_id
            )
        except Exception:
            pass

        return jsonify({'error': str(exc)}), 400

    except Exception as exc:
        session.rollback()

        # Clean up newly created persistent face data.
        try:
            attendance_system.embedding_store.delete_student(
                student_id
            )
        except Exception:
            pass

        try:
            if os.path.exists(representative_path):
                os.remove(representative_path)
        except Exception:
            pass

        return jsonify({
            'error': f'Registration failed: {str(exc)}'
        }), 500

    finally:
        session.close()

    print(
        f'Registered: {name} ({student_id}) - '
        f'{department}, Year {year} - 5 embedding samples'
    )

    return jsonify({
        'message': f'{name} registered successfully with 5 face samples!',
        'student_id': student_id,
        'samples': 5
    })

@app.route('/register')
def register_page():
    # Freeze attendance marking while on the registration page.
    # Marking resumes when the user returns to the dashboard (/).
    if _recognition_command_queue is not None:
        try:
            _recognition_command_queue.put_nowait('hold')
        except Exception:
            pass
    return render_template('register.html')

if __name__ == '__main__':
    print("=" * 60)
    print("ÃƒÂ°Ã…Â¸Ã…Â½Ã¢â‚¬Å“ ATTENDANCE SYSTEM")
    print("=" * 60)
    print("\nÃƒÂ°Ã…Â¸Ã…Â¡Ã¢â€šÂ¬ Starting server at http://localhost:5000")
    print("Press CTRL+C to stop\n")
    ensure_camera_thread()
    app.run(debug=False, host='0.0.0.0', port=5000, threaded=True)



























