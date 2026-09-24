"""
Attendance System Desktop Launcher
Runs the existing Flask dashboard inside a desktop application window.
"""

import sys
import os
import threading
import time
import multiprocessing

if getattr(sys, 'frozen', False):
    sys.path.insert(0, sys._MEIPASS)
    app_dir = os.path.dirname(sys.executable)
else:
    app_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, app_dir)

os.makedirs(os.path.join(app_dir, 'data', 'known_faces'), exist_ok=True)
os.makedirs(os.path.join(app_dir, 'data', 'models'), exist_ok=True)


def start_server():
    log_path = os.path.join(app_dir, "server_startup_error.log")

    try:
        with open(log_path, "w", encoding="utf-8") as log:
            log.write("Starting Flask server...\\n")

        from app import app, ensure_camera_thread, log_activity

        with open(log_path, "a", encoding="utf-8") as log:
            log.write("app imported successfully.\\n")

        ensure_camera_thread()

        log_activity(
            'system_started',
            'System started',
            'Attendance System is ready'
        )

        with open(log_path, "a", encoding="utf-8") as log:
            log.write("Camera thread started successfully.\\n")

        app.run(
            debug=False,
            host='127.0.0.1',
            port=5000,
            threaded=True,
            use_reloader=False
        )

    except Exception:
        import traceback
        with open(log_path, "a", encoding="utf-8") as log:
            log.write("\\n=== SERVER STARTUP ERROR ===\\n")
            traceback.print_exc(file=log)


def main():
    import webview

    server_thread = threading.Thread(
        target=start_server,
        daemon=True
    )
    server_thread.start()

    time.sleep(2)

    class DesktopAPI:
        def save_file(self, filename, content):
            import webview

            window = webview.active_window()

            if window is None:
                return {'success': False, 'message': 'Application window is unavailable.'}

            try:
                result = window.create_file_dialog(
                    webview.FileDialog.SAVE,
                    save_filename=filename,
                    file_types=('CSV files (*.csv)', 'All files (*.*)')
                )

                if not result:
                    return {'success': False, 'cancelled': True}

                filepath = result[0] if isinstance(result, (tuple, list)) else result

                with open(filepath, 'w', encoding='utf-8-sig', newline='') as file:
                    file.write(content)

                return {
                    'success': True,
                    'path': filepath
                }

            except Exception as exc:
                return {
                    'success': False,
                    'message': str(exc)
                }

    webview.settings['ALLOW_DOWNLOADS'] = True
    window = webview.create_window(
        'Attendance System',
        'http://127.0.0.1:5000',
        js_api=DesktopAPI(),
        width=1280,
        height=800,
        min_size=(1000, 700),
        maximized=True,
        resizable=True
    )

    window.events.loaded += lambda: window.run_js("document.documentElement.style.zoom = '90%';")

    def shutdown():
        try:
            window.hide()
        except Exception:
            pass
        try:
            from app import _recognition_process, _recognition_stop_event
            if _recognition_stop_event is not None:
                _recognition_stop_event.set()
            if _recognition_process is not None and _recognition_process.is_alive():
                _recognition_process.terminate()
        except Exception:
            pass
        os._exit(0)

    window.events.closing += shutdown
    window.events.closed += shutdown
    webview.start()

    shutdown()


if __name__ == '__main__':
    multiprocessing.freeze_support()
    main()
