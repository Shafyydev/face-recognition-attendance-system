# -*- mode: python ; coding: utf-8 -*-
# AttendanceSystem.spec - current PyInstaller build configuration

import os
import cv2
import face_recognition_models

# Find OpenCV's bundled data directory.
cv2_data_dir = os.path.dirname(cv2.__file__)

# Find face_recognition's required dlib model files.
face_recognition_models_dir = os.path.dirname(face_recognition_models.__file__)

a = Analysis(
    ['launcher.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        # Flask templates
        ('templates', 'templates'),

        # Required application packages
        ('database', 'database'),
        ('face_utils', 'face_utils'),

        # Required Haar cascade
        ('data/models/haarcascade_frontalface_default.xml', 'data/models'),

        # OpenCV data
        (os.path.join(cv2_data_dir, 'data'), 'cv2/data'),

        # face_recognition model files
        (face_recognition_models_dir, 'face_recognition_models'),
    ],
    hiddenimports=[
        # Flask
        'flask',
        'flask_cors',
        'jinja2',
        'markupsafe',
        'werkzeug',
        'click',
        'itsdangerous',
        'blinker',

        # SQLAlchemy
        'sqlalchemy',
        'sqlalchemy.dialects.sqlite',
        'sqlalchemy.ext.declarative',
        'sqlalchemy.orm',

        # OpenCV
        'cv2',
        'cv2.face',

        # NumPy
        'numpy',

        # face-recognition / dlib
        'face_recognition',
        'dlib',

        # Application
        'app',
        'database',
        'database.models',

        # Current face-recognition architecture
        'face_utils',
        'face_utils.attendance_marker',
        'face_utils.cascade',
        'face_utils.decision_engine',
        'face_utils.embedding_encoder',
        'face_utils.face_embedding_store',
        'face_utils.face_encoder',
        'face_utils.recognition_worker',

        # Desktop WebView
        'webview',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Heavy packages not used by the application
        'tensorflow',
        'keras',
        'torch',
        'torchvision',
        'matplotlib',
        'plotly',
        'pandas',
        'scipy',
        'IPython',
        'notebook',
        'jupyter',
        'tkinter',
        'PyQt5',
        'PyQt6',
        'PySide2',
        'PySide6',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AttendanceSystem',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AttendanceSystem',
)
