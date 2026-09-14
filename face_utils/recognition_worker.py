import time


def recognition_process_worker(
    input_queue,
    output_queue,
    command_queue,
    stop_event
):
    """
    Completely isolated face-recognition worker.

    This module intentionally does NOT import app.py.
    That prevents Windows multiprocessing from creating
    a second Flask application/camera system in the child.
    """

    from face_utils.attendance_marker import AttendanceMarker

    recognition_system = AttendanceMarker()
    print('Recognition worker: initialized', flush=True)

    last_frame_id = -1

    while not stop_event.is_set():

        # ----------------------------------------------------
        # Handle control commands.
        # ----------------------------------------------------
        while True:
            try:
                command = command_queue.get_nowait()
            except Exception:
                break

            if command == 'stop':
                stop_event.set()
                break

            if command == 'reload':
                try:
                    recognition_system.reload_embeddings()
                    print('Recognition worker: embeddings reloaded')
                except Exception as exc:
                    print(f'Recognition worker reload error: {exc}')

            elif command == 'reset':
                try:
                    recognition_system.reset()
                    print('Recognition worker: state reset')
                except Exception as exc:
                    print(f'Recognition worker reset error: {exc}')

            elif command == 'release':
                try:
                    recognition_system.release_hold(grace_seconds=3)
                except Exception as exc:
                    print(f'Recognition worker release error: {exc}')

            elif command == 'hold':
                try:
                    recognition_system.hold()
                except Exception as exc:
                    print(f'Recognition worker hold error: {exc}')

        if stop_event.is_set():
            break

        # ----------------------------------------------------
        # Process only the newest available frame.
        # ----------------------------------------------------
        try:
            frame_id, frame = input_queue.get(timeout=0.1)
        except Exception:
            continue

        if frame_id == last_frame_id:
            continue

        last_frame_id = frame_id

        print(
            f'Recognition worker: received frame {frame_id} '
            f'shape={getattr(frame, "shape", None)}',
            flush=True
        )

        try:
            processed, results = recognition_system.process_frame(frame)

            print(
                f'Recognition worker: processed frame {frame_id} '
                f'results={results}',
                flush=True
            )

            output_queue.put_nowait(
                (frame_id, results)
            )

            print(
                f'Recognition worker: returned frame {frame_id}',
                flush=True
            )

        except Exception as exc:
            print(
                f'Recognition worker ERROR on frame {frame_id}: '
                f'{type(exc).__name__}: {exc}',
                flush=True
            )

        time.sleep(0.001)

