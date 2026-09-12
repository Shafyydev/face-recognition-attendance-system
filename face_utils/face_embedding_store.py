import os
import sys
import json
import numpy as np


class FaceEmbeddingStore:
    """
    Persistent storage for 128-D face embeddings.

    Development storage:
        D:\codehub\attendance_system\data\face_embeddings

    Each student gets one JSON file containing:
        - student_id
        - name
        - embeddings
    """

    def __init__(self, storage_dir=None):

        if storage_dir is None:
            if getattr(sys, "frozen", False):
                app_dir = os.path.dirname(sys.executable)
            else:
                app_dir = os.path.dirname(
                    os.path.dirname(os.path.abspath(__file__))
                )

            storage_dir = os.path.join(
                app_dir,
                "data",
                "face_embeddings"
            )

        self.storage_dir = storage_dir

        os.makedirs(
            self.storage_dir,
            exist_ok=True
        )

    def _path(self, student_id):

        safe_id = str(student_id).strip()

        return os.path.join(
            self.storage_dir,
            f"{safe_id}.json"
        )

    def save_student(
        self,
        student_id,
        name,
        embeddings
    ):
        """
        Save all embeddings belonging to one student.
        """

        if not embeddings:
            raise ValueError(
                "Cannot save student without embeddings."
            )

        clean_embeddings = []

        for embedding in embeddings:

            array = np.asarray(
                embedding,
                dtype=np.float32
            ).reshape(-1)

            if array.shape != (128,):
                raise ValueError(
                    "Every face embedding must contain exactly 128 values."
                )

            clean_embeddings.append(
                array.tolist()
            )

        data = {
            "student_id": str(student_id).strip(),
            "name": str(name).strip(),
            "embedding_dimension": 128,
            "sample_count": len(clean_embeddings),
            "embeddings": clean_embeddings
        }

        path = self._path(student_id)

        temporary_path = path + ".tmp"

        with open(
            temporary_path,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                data,
                file,
                indent=2
            )

        # Atomic replacement.
        os.replace(
            temporary_path,
            path
        )

        return path

    def load_student(self, student_id):

        path = self._path(student_id)

        if not os.path.exists(path):
            return None

        with open(
            path,
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(file)

        embeddings = []

        for embedding in data.get(
            "embeddings",
            []
        ):

            array = np.asarray(
                embedding,
                dtype=np.float32
            ).reshape(-1)

            if array.shape != (128,):
                raise ValueError(
                    f"Invalid embedding in {path}"
                )

            embeddings.append(array)

        data["embeddings"] = embeddings

        return data

    def load_all(self):

        students = {}

        for filename in sorted(
            os.listdir(self.storage_dir)
        ):

            if not filename.lower().endswith(".json"):
                continue

            student_id = os.path.splitext(
                filename
            )[0]

            data = self.load_student(
                student_id
            )

            if data is not None:
                students[
                    data["student_id"]
                ] = data

        return students

    def delete_student(self, student_id):

        path = self._path(student_id)

        if os.path.exists(path):
            os.remove(path)
            return True

        return False

    def count_students(self):

        return len(
            self.load_all()
        )


# ------------------------------------------------------------------
# Direct test
# ------------------------------------------------------------------

if __name__ == "__main__":

    print("=" * 70)
    print("FACE EMBEDDING STORE TEST")
    print("=" * 70)
    print()

    store = FaceEmbeddingStore()

    print(
        f"Storage directory:\n{store.storage_dir}"
    )

    print()

    # Temporary synthetic embeddings.
    # These are NOT real faces and are used only to test storage.
    test_embeddings = [
        np.random.default_rng(i).random(
            128
        ).astype(np.float32)
        for i in range(5)
    ]

    print(
        "Creating temporary test student..."
    )

    path = store.save_student(
        "TEST001",
        "TEST STUDENT",
        test_embeddings
    )

    print(
        f"Saved: {path}"
    )

    print()

    print(
        "Loading test student..."
    )

    loaded = store.load_student(
        "TEST001"
    )

    if loaded is None:
        raise RuntimeError(
            "Failed to load test student."
        )

    print(
        f"Student ID: {loaded['student_id']}"
    )

    print(
        f"Name: {loaded['name']}"
    )

    print(
        f"Embedding dimension: "
        f"{loaded['embedding_dimension']}"
    )

    print(
        f"Sample count: "
        f"{len(loaded['embeddings'])}"
    )

    print()

    if all(
        embedding.shape == (128,)
        for embedding in loaded["embeddings"]
    ):

        print(
            "Embedding validation: PASSED"
        )

    else:

        raise RuntimeError(
            "Embedding validation failed."
        )

    print()

    print(
        "Testing load_all()..."
    )

    all_students = store.load_all()

    print(
        f"Students loaded: "
        f"{len(all_students)}"
    )

    print()

    print(
        "Removing temporary test student..."
    )

    deleted = store.delete_student(
        "TEST001"
    )

    if deleted:
        print(
            "Temporary test student removed."
        )
    else:
        raise RuntimeError(
            "Could not remove temporary test student."
        )

    print()
    print("=" * 70)
    print("FACE EMBEDDING STORE TEST PASSED")
    print("=" * 70)

