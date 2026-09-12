import os
import sys
import numpy as np
import cv2
import face_recognition


class EmbeddingEncoder:
    """
    Face embedding engine for pose-tolerant recognition.

    Each student can have multiple face samples.
    A live face is compared against every sample belonging
    to each student, and the student's best distance is used.
    """

    EMBEDDING_SIZE = 128

    def __init__(self, known_faces_dir=None):
        if known_faces_dir is None:
            if getattr(sys, "frozen", False):
                app_dir = os.path.dirname(sys.executable)
            else:
                app_dir = os.path.dirname(
                    os.path.dirname(os.path.abspath(__file__))
                )

            known_faces_dir = os.path.join(
                app_dir,
                "data",
                "known_faces"
            )

        self.known_faces_dir = known_faces_dir
        self.known_embeddings = {}

    @staticmethod
    def parse_student_info(filename):
        """
        Extract student ID and name from:

            A24AID01_DHARMA RAJ.jpg
        """

        base = os.path.splitext(
            os.path.basename(filename)
        )[0]

        if "_" not in base:
            return None, None

        student_id, name = base.split("_", 1)

        if not student_id or not name:
            return None, None

        return student_id, name

    @staticmethod
    def _largest_face(locations):
        """
        Return the largest detected face.
        """

        if not locations:
            return None

        return max(
            locations,
            key=lambda box: (
                (box[2] - box[0]) *
                (box[1] - box[3])
            )
        )

    def encode_image(self, image_path):
        """
        Generate a 128-D face embedding from an image.

        Returns:
            numpy.ndarray
            or None if no usable face is found.
        """

        image = face_recognition.load_image_file(
            image_path
        )

        locations = face_recognition.face_locations(
            image,
            number_of_times_to_upsample=1,
            model="hog"
        )

        location = self._largest_face(locations)

        if location is None:
            return None

        encodings = face_recognition.face_encodings(
            image,
            known_face_locations=[location],
            num_jitters=1
        )

        if not encodings:
            return None

        embedding = np.asarray(
            encodings[0],
            dtype=np.float32
        )

        if embedding.shape != (
            self.EMBEDDING_SIZE,
        ):
            return None

        if not np.isfinite(embedding).all():
            return None

        return embedding

    def encode_frame(self, frame):
        """
        Generate a 128-D face embedding directly from an OpenCV frame.

        The input frame is expected to be a BGR NumPy array, as produced
        by cv2.VideoCapture().
        
        Returns:
            numpy.ndarray
            or None if no usable face is found.
        """

        if frame is None:
            return None

        if not isinstance(frame, np.ndarray):
            return None

        if frame.size == 0:
            return None

        # OpenCV uses BGR; face_recognition expects RGB.
        rgb_frame = cv2.cvtColor(
            frame,
            cv2.COLOR_BGR2RGB
        )

        locations = face_recognition.face_locations(
            rgb_frame,
            number_of_times_to_upsample=1,
            model="hog"
        )

        location = self._largest_face(locations)

        if location is None:
            return None

        encodings = face_recognition.face_encodings(
            rgb_frame,
            known_face_locations=[location],
            num_jitters=1
        )

        if not encodings:
            return None

        embedding = np.asarray(
            encodings[0],
            dtype=np.float32
        )

        if embedding.shape != (
            self.EMBEDDING_SIZE,
        ):
            return None

        if not np.isfinite(embedding).all():
            return None

        return embedding
    def add_embedding(
        self,
        student_id,
        name,
        embedding
    ):
        """
        Add an embedding to a student's sample set.
        """

        embedding = np.asarray(
            embedding,
            dtype=np.float32
        )

        if embedding.shape != (
            self.EMBEDDING_SIZE,
        ):
            raise ValueError(
                "Invalid embedding shape"
            )

        if not np.isfinite(embedding).all():
            raise ValueError(
                "Embedding contains invalid values"
            )

        if student_id not in self.known_embeddings:
            self.known_embeddings[student_id] = {
                "student_id": student_id,
                "name": name,
                "embeddings": []
            }

        self.known_embeddings[
            student_id
        ]["embeddings"].append(
            embedding
        )

    def load_known_faces(self):
        """
        Load all enrolled face images.

        Multiple files with the same student ID are treated
        as multiple samples belonging to the same student.
        """

        self.known_embeddings.clear()

        if not os.path.isdir(
            self.known_faces_dir
        ):
            return 0

        loaded = 0

        for filename in sorted(
            os.listdir(
                self.known_faces_dir
            )
        ):

            if not filename.lower().endswith(
                (".jpg", ".jpeg", ".png")
            ):
                continue

            student_id, name = (
                self.parse_student_info(filename)
            )

            if not student_id:
                continue

            image_path = os.path.join(
                self.known_faces_dir,
                filename
            )

            try:

                embedding = self.encode_image(
                    image_path
                )

                if embedding is None:
                    print(
                        f"WARNING: "
                        f"No usable face: {filename}"
                    )
                    continue

                self.add_embedding(
                    student_id,
                    name,
                    embedding
                )

                loaded += 1

                print(
                    f"Loaded embedding: {filename}"
                )

            except Exception as exc:

                print(
                    f"ERROR processing "
                    f"{filename}: {exc}"
                )

        return loaded

    def load_sample_directory(
        self,
        student_id,
        name,
        directory
    ):
        """
        Load every supported image in a directory
        as samples belonging to one student.

        This is used for multi-sample enrollment testing
        and later for the real registration system.
        """

        if not os.path.isdir(directory):
            return 0

        loaded = 0

        for filename in sorted(
            os.listdir(directory)
        ):

            if not filename.lower().endswith(
                (".jpg", ".jpeg", ".png")
            ):
                continue

            image_path = os.path.join(
                directory,
                filename
            )

            embedding = self.encode_image(
                image_path
            )

            if embedding is None:
                print(
                    f"WARNING: "
                    f"No usable face: {filename}"
                )
                continue

            self.add_embedding(
                student_id,
                name,
                embedding
            )

            loaded += 1

        return loaded

    def compare_embedding_to_student(
        self,
        embedding,
        student_id
    ):
        """
        Compare one live embedding against every
        enrolled sample belonging to one student.

        Returns the student's BEST distance.
        """

        person = self.known_embeddings.get(
            student_id
        )

        if person is None:
            return None

        embedding = np.asarray(
            embedding,
            dtype=np.float32
        )

        if embedding.shape != (
            self.EMBEDDING_SIZE,
        ):
            return None

        distances = []

        for known_embedding in person[
            "embeddings"
        ]:

            distance = float(
                np.linalg.norm(
                    known_embedding -
                    embedding
                )
            )

            distances.append(
                distance
            )

        if not distances:
            return None

        return min(distances)

    def find_best_match(self, embedding):
        """
        Find the best identity.

        IMPORTANT:
        Multiple samples belonging to the same student
        are grouped together.

        The student's best sample distance is used.

        Returns:

            {
                "student_id": ...,
                "name": ...,
                "distance": ...,
                "second_best_distance": ...,
                "margin": ...
            }

        or None if no enrolled identities exist.
        """

        if not self.known_embeddings:
            return None

        candidates = []

        for student_id, person in (
            self.known_embeddings.items()
        ):

            distance = (
                self.compare_embedding_to_student(
                    embedding,
                    student_id
                )
            )

            if distance is None:
                continue

            candidates.append(
                {
                    "student_id": student_id,
                    "name": person["name"],
                    "distance": distance
                }
            )

        if not candidates:
            return None

        candidates.sort(
            key=lambda item: item["distance"]
        )

        best = candidates[0]

        if len(candidates) > 1:

            second_best_distance = (
                candidates[1]["distance"]
            )

            margin = (
                second_best_distance -
                best["distance"]
            )

        else:

            second_best_distance = float(
                "inf"
            )

            margin = float("inf")

        return {
            "student_id": best["student_id"],
            "name": best["name"],
            "distance": best["distance"],
            "second_best_distance": (
                second_best_distance
            ),
            "margin": margin
        }


