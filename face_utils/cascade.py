import os
import sys
import cv2


def haar_cascade_path():
    if getattr(sys, 'frozen', False):
        root = sys._MEIPASS
    else:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    bundled = os.path.join(root, 'data', 'models', 'haarcascade_frontalface_default.xml')
    candidates = [bundled]
    haarcascades = getattr(cv2, 'data', None)
    if haarcascades is not None:
        candidates.append(os.path.join(cv2.data.haarcascades, 'haarcascade_frontalface_default.xml'))
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return bundled


def load_face_cascade():
    path = haar_cascade_path()
    cascade = cv2.CascadeClassifier(path)
    if cascade.empty():
        print(f"Failed to load Haar cascade from {path}")
    else:
        print(f"Loaded Haar cascade: {path}")
    return cascade
