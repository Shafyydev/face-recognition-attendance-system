import os
import cv2
import time
import json
import numpy as np
import face_recognition

from face_utils.face_embedding_store import FaceEmbeddingStore


STUDENT_ID = "A24AID06"
STUDENT_NAME = "MOHAMMED SHAFIULLAH"

OUTPUT_DIR = (
    r"D:\codehub\attendance_system\data"
    r"\face_embeddings"
)

os.makedirs(OUTPUT_DIR, exist_ok=True)

print("=" * 70)
print("REAL MULTI-SAMPLE ENROLLMENT STORAGE TEST")
print("=" * 70)
print()

print(f"Student ID:   {STUDENT_ID}")
print(f"Student Name: {STUDENT_NAME}")
print()

print("This test will:")
print("  1. Capture 5 natural face samples")
print("  2. Generate 128-D embeddings")
print("  3. Save them persistently")
print("  4. Reload them from disk")
print("  5. Validate the stored data")
print()

print("No database or production files will be changed.")
print()

store = FaceEmbeddingStore(
    storage_dir=OUTPUT_DIR
)

print(
    f"Embedding storage:\n{OUTPUT_DIR}"
)

print()

# ------------------------------------------------------------
# Remove only an existing TEST enrollment for this student.
# This affects only face_embeddings, never the database.
# ------------------------------------------------------------

existing_test_file = os.path.join(
    OUTPUT_DIR,
    f"{STUDENT_ID}.json"
)

if os.path.exists(existing_test_file):

    print(
        "Removing previous development test enrollment..."
    )

    os.remove(existing_test_file)

    print("Removed.")

print()

# ------------------------------------------------------------
# Camera setup
# ------------------------------------------------------------

print("=" * 70)
print("CAPTURE")
print("=" * 70)
print()

print("The camera will capture 5 samples automatically.")
print()
print("Positions:")
print("  1. STRAIGHT")
print("  2. SLIGHTLY LEFT")
print("  3. SLIGHTLY RIGHT")
print("  4. SLIGHTLY UP")
print("  5. SLIGHTLY DOWN")
print()
print("Keep your face clearly visible.")
print("Do not make extreme head movements.")
print()
print("Press Q to cancel.")
print()

cap = cv2.VideoCapture(0)

if not cap.isOpened():

    print("ERROR: Could not open camera.")
    raise SystemExit(1)

time.sleep(1)

sample_labels = [
    "STRAIGHT",
    "SLIGHTLY LEFT",
    "SLIGHTLY RIGHT",
    "SLIGHTLY UP",
    "SLIGHTLY DOWN"
]

embeddings = []

current_target = 0

stable_frames = 0
stable_frames_required = 5

capture_cooldown = 2.0
last_capture_time = 0

while current_target < 5:

    ret, frame = cap.read()

    if not ret:

        print(
            "ERROR: Could not read camera frame."
        )

        break

    # Normal non-mirrored preview.
    frame = cv2.flip(frame, 1)

    rgb = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2RGB
    )

    locations = face_recognition.face_locations(
        rgb,
        number_of_times_to_upsample=1,
        model="hog"
    )

    display = frame.copy()

    if not locations:

        stable_frames = 0

        cv2.putText(
            display,
            "NO FACE DETECTED",
            (20, 45),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 0, 255),
            2
        )

    else:

        # Largest face only.
        locations = sorted(
            locations,
            key=lambda box: (
                (box[2] - box[0]) *
                (box[3] - box[1])
            ),
            reverse=True
        )

        location = locations[0]

        top, right, bottom, left = location

        face_width = right - left
        face_height = bottom - top

        face_large_enough = (
            face_width >= 120 and
            face_height >= 120
        )

        if face_large_enough:

            stable_frames += 1

        else:

            stable_frames = 0

        cv2.rectangle(
            display,
            (left, top),
            (right, bottom),
            (0, 255, 0),
            2
        )

        label = sample_labels[current_target]

        cv2.putText(
            display,
            f"Sample {current_target + 1}/5: {label}",
            (20, 45),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.75,
            (255, 255, 255),
            2
        )

        if not face_large_enough:

            cv2.putText(
                display,
                "Move closer to camera",
                (20, 80),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (0, 0, 255),
                2
            )

        else:

            cv2.putText(
                display,
                f"Hold steady: "
                f"{stable_frames}/{stable_frames_required}",
                (20, 80),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (255, 255, 255),
                2
            )

            now = time.time()

            if (
                stable_frames >= stable_frames_required
                and
                now - last_capture_time >= capture_cooldown
            ):

                encodings = face_recognition.face_encodings(
                    rgb,
                    known_face_locations=[location],
                    num_jitters=1
                )

                if encodings:

                    embedding = np.asarray(
                        encodings[0],
                        dtype=np.float32
                    ).reshape(-1)

                    if embedding.shape == (128,):

                        embeddings.append(
                            embedding
                        )

                        print(
                            f"Captured "
                            f"{current_target + 1}/5: "
                            f"{label}"
                        )

                        current_target += 1
                        stable_frames = 0
                        last_capture_time = now

                        time.sleep(0.5)

                else:

                    stable_frames = 0

                    cv2.putText(
                        display,
                        "Encoding failed - try again",
                        (20, 115),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.60,
                        (0, 0, 255),
                        2
                    )

    cv2.putText(
        display,
        "Q = cancel",
        (20, display.shape[0] - 20),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.60,
        (255, 255, 255),
        2
    )

    cv2.imshow(
        "Real Enrollment Storage Test",
        display
    )

    key = cv2.waitKey(1) & 0xFF

    if key == ord("q"):

        print()
        print("Capture cancelled.")
        break


cap.release()
cv2.destroyAllWindows()

print()

# ------------------------------------------------------------
# Verify capture
# ------------------------------------------------------------

if len(embeddings) != 5:

    print("=" * 70)
    print("CAPTURE TEST FAILED")
    print("=" * 70)
    print()
    print(
        f"Only {len(embeddings)}/5 embeddings were captured."
    )
    raise SystemExit(1)

print("=" * 70)
print("PERSISTENT STORAGE")
print("=" * 70)
print()

# ------------------------------------------------------------
# Save embeddings
# ------------------------------------------------------------

saved_path = store.save_student(
    STUDENT_ID,
    STUDENT_NAME,
    embeddings
)

print(
    f"Saved successfully:"
)

print(
    saved_path
)

print()

# ------------------------------------------------------------
# Reload from disk
# ------------------------------------------------------------

print("Reloading from disk...")

loaded = store.load_student(
    STUDENT_ID
)

if loaded is None:

    print(
        "ERROR: Could not reload student."
    )

    raise SystemExit(1)

print(
    f"Student ID: "
    f"{loaded['student_id']}"
)

print(
    f"Name: "
    f"{loaded['name']}"
)

print(
    f"Embedding dimension: "
    f"{loaded['embedding_dimension']}"
)

print(
    f"Stored samples: "
    f"{len(loaded['embeddings'])}"
)

print()

# ------------------------------------------------------------
# Validate
# ------------------------------------------------------------

validation_passed = True

if loaded["student_id"] != STUDENT_ID:
    validation_passed = False

if loaded["name"] != STUDENT_NAME:
    validation_passed = False

if loaded["embedding_dimension"] != 128:
    validation_passed = False

if len(loaded["embeddings"]) != 5:
    validation_passed = False

for index, embedding in enumerate(
    loaded["embeddings"],
    start=1
):

    if embedding.shape != (128,):

        print(
            f"FAIL | Sample {index} | "
            f"shape={embedding.shape}"
        )

        validation_passed = False

    else:

        print(
            f"PASS | Sample {index} | "
            f"shape={embedding.shape}"
        )

print()

# ------------------------------------------------------------
# Pairwise distance check
# ------------------------------------------------------------

print("=" * 70)
print("CAPTURED EMBEDDING DISTANCES")
print("=" * 70)
print()

distances = []

for i in range(len(loaded["embeddings"])):

    for j in range(i + 1, len(loaded["embeddings"])):

        distance = float(
            face_recognition.face_distance(
                [loaded["embeddings"][i]],
                loaded["embeddings"][j]
            )[0]
        )

        distances.append(distance)

        print(
            f"Sample {i + 1} <-> Sample {j + 1}: "
            f"{distance:.4f}"
        )

print()

if distances:

    print(
        f"Minimum distance: "
        f"{min(distances):.4f}"
    )

    print(
        f"Maximum distance: "
        f"{max(distances):.4f}"
    )

    print(
        f"Average distance: "
        f"{np.mean(distances):.4f}"
    )

print()

# ------------------------------------------------------------
# Final result
# ------------------------------------------------------------

print("=" * 70)

if validation_passed:

    print(
        "PERSISTENT ENROLLMENT TEST: PASSED"
    )

    print()
    print(
        "5 real face embeddings were captured,"
    )
    print(
        "saved to disk, reloaded successfully,"
    )
    print(
        "and validated as 128-D embeddings."
    )

else:

    print(
        "PERSISTENT ENROLLMENT TEST: FAILED"
    )

print("=" * 70)
