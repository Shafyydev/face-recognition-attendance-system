import os
import sys
import cv2
import numpy as np
from face_utils.cascade import load_face_cascade


class FaceEncoder:

    FACE_SIZE = (200, 200)

    def __init__(self, known_faces_dir=None):

        if known_faces_dir is None:
            if getattr(sys, 'frozen', False):
                known_faces_dir = os.path.join(
                    os.path.dirname(sys.executable),
                    "data",
                    "known_faces"
                )
            else:
                known_faces_dir = "D:\codehub\attendance_system\data\known_faces"

        self.known_faces_dir = known_faces_dir

        self.known_face_names = []
        self.known_face_ids = []

        self.face_cascade = load_face_cascade()

        self.recognizer = cv2.face.LBPHFaceRecognizer_create(
            radius=2,
            neighbors=12,
            grid_x=8,
            grid_y=8
        )

        self._trained = False


    @staticmethod
    def _preprocess(face_gray):

        clahe = cv2.createCLAHE(
            clipLimit=2.0,
            tileGridSize=(8, 8)
        )

        equalized = clahe.apply(face_gray)

        return cv2.resize(
            equalized,
            FaceEncoder.FACE_SIZE
        )


    @staticmethod
    def _augment(face):

        augmented = [face]

        augmented.append(
            cv2.convertScaleAbs(
                face,
                alpha=1.2,
                beta=20
            )
        )

        augmented.append(
            cv2.convertScaleAbs(
                face,
                alpha=0.8,
                beta=-20
            )
        )

        augmented.append(
            cv2.convertScaleAbs(
                face,
                alpha=1.1,
                beta=10
            )
        )

        augmented.append(
            cv2.convertScaleAbs(
                face,
                alpha=0.9,
                beta=-10
            )
        )

        augmented.append(cv2.flip(face, 1))

        augmented.append(
            cv2.GaussianBlur(
                face,
                (3, 3),
                0
            )
        )

        h, w = face.shape[:2]
        center = (w // 2, h // 2)

        for angle in [-5, 5]:

            M = cv2.getRotationMatrix2D(
                center,
                angle,
                1.0
            )

            rotated = cv2.warpAffine(
                face,
                M,
                (w, h),
                borderMode=cv2.BORDER_REFLECT
            )

            augmented.append(rotated)

        return augmented


    def load_known_faces(self):

        self.known_face_names = []
        self.known_face_ids = []

        faces = []
        labels = []

        if not os.path.exists(self.known_faces_dir):

            print(
                f"Directory {self.known_faces_dir} not found!"
            )

            return

        label_index = 0

        for filename in sorted(
            os.listdir(self.known_faces_dir)
        ):

            if filename.endswith(
                ('.jpg', '.jpeg', '.png')
            ):

                try:

                    parts = filename.split('_')

                    student_id = parts[0]

                    name = '_'.join(
                        parts[1:]
                    ).split('.')[0]

                    image_path = os.path.join(
                        self.known_faces_dir,
                        filename
                    )

                    image = cv2.imread(image_path)

                    if image is None:
                        print(
                            f"Could not read {filename}"
                        )
                        continue

                    gray = cv2.cvtColor(
                        image,
                        cv2.COLOR_BGR2GRAY
                    )

                    if self.face_cascade.empty():

                        print(
                            f"Cascade missing, cannot detect face in {filename}"
                        )

                        continue

                    detected = self.face_cascade.detectMultiScale(
                        gray,
                        1.1,
                        5
                    )

                    if len(detected) > 0:

                        (x, y, w, h) = detected[0]

                        face_roi = gray[
                            y:y+h,
                            x:x+w
                        ]

                        face_processed = self._preprocess(
                            face_roi
                        )

                        for aug_face in self._augment(
                            face_processed
                        ):

                            faces.append(aug_face)
                            labels.append(label_index)

                        self.known_face_names.append(name)
                        self.known_face_ids.append(student_id)

                        print(
                            f"Loaded: {name} ({student_id})"
                        )

                        label_index += 1

                    else:

                        print(
                            f"No face detected in {filename}"
                        )

                except Exception as e:

                    print(
                        f"Error loading {filename}: {e}"
                    )

        if len(faces) > 0:

            self.recognizer.train(
                faces,
                np.array(labels)
            )

            self._trained = True

        print(
            f"\nLoaded {label_index} faces "
            f"({len(faces)} training samples)"
        )


    def register_face(self, student_id, name, image):

        os.makedirs(
            self.known_faces_dir,
            exist_ok=True
        )

        filename = f"{student_id}_{name}.jpg"

        filepath = os.path.join(
            self.known_faces_dir,
            filename
        )

        cv2.imwrite(
            filepath,
            image
        )

        gray = cv2.cvtColor(
            image,
            cv2.COLOR_BGR2GRAY
        )

        detected = self.face_cascade.detectMultiScale(
            gray,
            1.1,
            5
        )

        if len(detected) == 0:

            return False, "No face detected!"

        self.load_known_faces()

        return True, "Face registered successfully!"


    def predict(self, face_gray):

        if not self._trained:

            return -1, 999.0

        face_processed = self._preprocess(
            face_gray
        )

        label, confidence = self.recognizer.predict(
            face_processed
        )

        return label, confidence

