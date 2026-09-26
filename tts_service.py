"""
Text-to-Speech Background Service

Runs pyttsx3 in a dedicated daemon thread so that voice
announcements never block the camera feed or Flask server.
"""

import threading
import queue


class TTSService:
    """Asynchronous text-to-speech service using pyttsx3."""

    def __init__(self):
        self._queue = queue.Queue()
        self._running = True
        self._engine = None

        # Start the worker as a daemon thread so it dies
        # automatically when the main process exits.
        self._thread = threading.Thread(
            target=self._worker,
            daemon=True,
            name="tts-worker"
        )
        self._thread.start()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def speak(self, text):
        """Queue a message to be spoken aloud.

        Non-blocking — returns immediately.
        """
        if self._running:
            self._queue.put(text)

    def stop(self):
        """Signal the worker to shut down."""
        self._running = False
        self._queue.put(None)  # sentinel to unblock .get()

    # ------------------------------------------------------------------
    # Internal worker
    # ------------------------------------------------------------------

    def _worker(self):
        """Consume the queue and speak each message sequentially."""
        try:
            import pyttsx3
            self._engine = pyttsx3.init()

            # Slightly slower rate for clarity
            self._engine.setProperty('rate', 150)

            # Use a clear, natural-sounding voice if available
            voices = self._engine.getProperty('voices')
            if voices:
                # Prefer a female English voice (usually index 1 on Windows)
                for v in voices:
                    if 'zira' in v.name.lower() or 'female' in v.name.lower():
                        self._engine.setProperty('voice', v.id)
                        break

            print("TTS service: initialized", flush=True)

        except Exception as exc:
            print(f"TTS service: init failed — {exc}", flush=True)
            return

        while self._running:
            try:
                text = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue

            if text is None:
                break

            try:
                self._engine.say(text)
                self._engine.runAndWait()
            except Exception as exc:
                print(f"TTS service: speak error — {exc}", flush=True)

        # Clean up the engine on shutdown
        try:
            if self._engine:
                self._engine.stop()
        except Exception:
            pass

        print("TTS service: stopped", flush=True)


# ------------------------------------------------------------------
# Module-level singleton
# ------------------------------------------------------------------
# Import this instance from anywhere to speak:
#   from tts_service import tts
#   tts.speak("Hello!")
# ------------------------------------------------------------------

tts = TTSService()
