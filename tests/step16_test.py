import os
import cv2
import time
import numpy as np
import face_recognition

from face_utils.face_embedding_store import FaceEmbeddingStore
from face_utils.embedding_encoder import EmbeddingEncoder


# ============================================================
# CONFIGURATION
# ============================================================

STORAGE_DIR = (
    r"D:\codehub\attendance_system\data"
    r"\face_embeddings"
)

STUDENT_ID = "A24AID07"
STUDENT_NAME = "SHAMEER"

MOHAMMED_ID = "A24AID06"


# ============================================================
# INITIALIZE STORAGE
# ============================================================

print("=" * 70)
print("STEP 16 - TWO-STUDENT PERSISTENT RECOGNITION TEST")
print("=" * 70)
print()

store = FaceEmbeddingStore(
    storage_dir=STORAGE_DIR
)

encoder = EmbeddingEncoder()


# ============================================================
# VERIFY MOHAMMED PERSISTENT ENROLLMENT
# ============================================================

print("Checking Mohammed's persistent enrollment...")

mohammed = store.load_student(
    MOHAMMED_ID
)

if mohammed is None:

    print()
    print(
        "ERROR: Mohammed's persistent enrollment was not found."
    )

    print(
        f"Expected file: "
        f"{os.path.join(STORAGE_DIR, MOHAMMED_ID + '.json')}"
    )

    raise SystemExit(1)

print(
    f"Found: {mohammed['student_id']} | "
    f"{mohammed['name']} | "
    f"samples={len(mohammed['embeddings'])}"
)

if len(mohammed["embeddings"]) != 5:

    print()
    print(
        "ERROR: Mohammed should have exactly 5 test embeddings."
    )

    raise SystemExit(1)

print(
    "Mohammed persistent enrollment: VERIFIED"
)

print()


# ============================================================
# REMOVE ONLY SHAMEER'S PREVIOUS TEST ENROLLMENT
# ============================================================

shameer_path = os.path.join(
    STORAGE_DIR,
    f"{STUDENT_ID}.json"
)

if os.path.exists(shameer_path):

    print(
        "Removing previous Shameer development test enrollment..."
    )

    os.remove(
        shameer_path
    )

    print("Removed.")

print()


# ============================================================
# CAPTURE SHAMEER
# ============================================================

print("=" * 70)
print("SHAMEER - 5 SAMPLE ENROLLMENT")
print("=" * 70)
print()

print(
    f"Student ID:   {STUDENT_ID}"
)

print(
    f"Student Name: {STUDENT_NAME}"
)

print()

print("The camera will capture 5 natural samples.")
print()

print("Positions:")
print("  1. STRAIGHT")
print("  2. SLIGHTLY LEFT")
print("  3. SLIGHTLY RIGHT")
print("  4. SLIGHTLY UP")
print("  5. SLIGHTLY DOWN")
print()

print("Keep the face clearly visible.")
print("Do not make extreme head movements.")
print()
print("Press Q to cancel.")
print()


cap = cv2.VideoCapture(0)

if not cap.isOpened():

    print(
        "ERROR: Could not open camera."
    )

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
    frame = cv2.flip(
        frame,
        1
    )

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

        # Select largest detected face.
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
        "Step 16 - Shameer Enrollment",
        display
    )

    key = cv2.waitKey(1) & 0xFF

    if key == ord("q"):

        print()
        print(
            "Capture cancelled."
        )

        break


cap.release()
cv2.destroyAllWindows()


# ============================================================
# CAPTURE VALIDATION
# ============================================================

print()

if len(embeddings) != 5:

    print("=" * 70)
    print("STEP 16 FAILED")
    print("=" * 70)
    print()

    print(
        f"Only {len(embeddings)}/5 samples were captured."
    )

    raise SystemExit(1)


print("=" * 70)
print("SAVING SHAMEER")
print("=" * 70)
print()


# ============================================================
# SAVE SHAMEER
# ============================================================

saved_path = store.save_student(
    STUDENT_ID,
    STUDENT_NAME,
    embeddings
)

print(
    "Saved successfully:"
)

print(
    saved_path
)

print()


# ============================================================
# RELOAD BOTH STUDENTS
# ============================================================

print("=" * 70)
print("LOADING BOTH STUDENTS FROM DISK")
print("=" * 70)
print()

students = store.load_all()

for student_id, data in students.items():

    print(
        f"Loaded: {student_id} | "
        f"{data['name']} | "
        f"samples={len(data['embeddings'])}"
    )

    for embedding in data["embeddings"]:

        encoder.add_embedding(
            student_id,
            data["name"],
            embedding
        )

print()

if MOHAMMED_ID not in students:

    print(
        "ERROR: Mohammed was not loaded."
    )

    raise SystemExit(1)

if STUDENT_ID not in students:

    print(
        "ERROR: Shameer was not loaded."
    )

    raise SystemExit(1)

print(
    "Both persistent enrollments loaded successfully."
)

print()


# ============================================================
# TWO-STUDENT LIVE TEST
# ============================================================

print("=" * 70)
print("TWO-STUDENT LIVE RECOGNITION TEST")
print("=" * 70)
print()

print(
    "SHAMEER should remain in front of the camera."
)

print()

print(
    "Move naturally for around 30 seconds."
)

print(
    "Try straight, left, right, up, down,"
)

print(
    "and different expressions."
)

print()

print("The system will compare Shameer against:")
print("  - MOHAMMED SHAFIULLAH")
print("  - SHAMEER")
print()

print("Press Q to stop.")
print()


cap = cv2.VideoCapture(0)

if not cap.isOpened():

    print(
        "ERROR: Could not open camera."
    )

    raise SystemExit(1)


frame_count = 0

results = []

last_print = 0


while True:

    ret, frame = cap.read()

    if not ret:

        print(
            "ERROR: Could not read camera frame."
        )

        break

    # Normal non-mirrored preview.
    frame = cv2.flip(
        frame,
        1
    )

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

    if locations:

        locations = sorted(
            locations,
            key=lambda box: (
                (box[2] - box[0]) *
                (box[3] - box[1])
            ),
            reverse=True
        )

        location = locations[0]

        encodings = face_recognition.face_encodings(
            rgb,
            known_face_locations=[location],
            num_jitters=1
        )

        if encodings:

            live_embedding = np.asarray(
                encodings[0],
                dtype=np.float32
            )

            match = encoder.find_best_match(
                live_embedding
            )

            if match:

                results.append(
                    match
                )

                top, right, bottom, left = location

                cv2.rectangle(
                    display,
                    (left, top),
                    (right, bottom),
                    (0, 255, 0),
                    2
                )

                cv2.putText(
                    display,
                    match["name"],
                    (left, max(30, top - 40)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.65,
                    (0, 255, 0),
                    2
                )

                cv2.putText(
                    display,
                    f"Distance: {match['distance']:.3f}",
                    (left, max(55, top - 15)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (255, 255, 255),
                    2
                )

                cv2.putText(
                    display,
                    f"Margin: {match['margin']:.3f}",
                    (left, bottom + 25),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (255, 255, 255),
                    2
                )

                now = time.time()

                if now - last_print >= 1.0:

                    print(
                        f"Frame {frame_count:04d} | "
                        f"Match: "
                        f"{match['name']:<25} | "
                        f"Distance: "
                        f"{match['distance']:.4f} | "
                        f"Second: "
                        f"{match['second_best_distance']:.4f} | "
                        f"Margin: "
                        f"{match['margin']:.4f}"
                    )

                    last_print = now

    else:

        cv2.putText(
            display,
            "NO FACE DETECTED",
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 0, 255),
            2
        )

    cv2.putText(
        display,
        "SHAMEER TEST - Q = quit",
        (20, display.shape[0] - 20),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.60,
        (255, 255, 255),
        2
    )

    cv2.imshow(
        "Step 16 - Two Student Recognition",
        display
    )

    frame_count += 1

    key = cv2.waitKey(1) & 0xFF

    if key == ord("q"):

        break


cap.release()
cv2.destroyAllWindows()


# ============================================================
# SUMMARY
# ============================================================

print()
print("=" * 70)
print("STEP 16 SUMMARY")
print("=" * 70)
print()

if not results:

    print(
        "No recognition samples collected."
    )

else:

    distances = [
        result["distance"]
        for result in results
    ]

    second_distances = [
        result["second_best_distance"]
        for result in results
    ]

    margins = [
        result["margin"]
        for result in results
    ]

    correct = sum(
        1
        for result in results
        if result["student_id"] == STUDENT_ID
    )

    print(
        f"Recognition samples: "
        f"{len(results)}"
    )

    print(
        f"Correct Shameer matches: "
        f"{correct}/{len(results)} "
        f"({correct / len(results) * 100:.1f}%)"
    )

    print()

    print(
        f"Best distance:       "
        f"{min(distances):.4f}"
    )

    print(
        f"Worst distance:      "
        f"{max(distances):.4f}"
    )

    print(
        f"Average distance:    "
        f"{np.mean(distances):.4f}"
    )

    print()

    print(
        f"Closest second-best: "
        f"{min(second_distances):.4f}"
    )

    print(
        f"Minimum margin:      "
        f"{min(margins):.4f}"
    )

    print(
        f"Maximum margin:      "
        f"{max(margins):.4f}"
    )

    print(
        f"Average margin:      "
        f"{np.mean(margins):.4f}"
    )

    print()

    distribution = {}

    for result in results:

        name = result["name"]

        distribution[name] = (
            distribution.get(name, 0) + 1
        )

    print(
        "MATCH DISTRIBUTION:"
    )

    for name, count in sorted(
        distribution.items(),
        key=lambda item: item[1],
        reverse=True
    ):

        print(
            f"  {name}: {count}"
        )

print()
print("=" * 70)
print("STEP 16 COMPLETE")
print("=" * 70)
