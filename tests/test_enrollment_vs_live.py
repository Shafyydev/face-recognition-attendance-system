import cv2
import face_recognition
import numpy as np
import glob
import os

KNOWN_DIR = r"data\known_faces"
REFERENCE = r"A24AID01_DHARMA RAJ.jpg"

print("============================================================")
print("  ENROLLED PHOTO vs LIVE CAMERA TEST")
print("============================================================")
print("")

# ------------------------------------------------------------
# Load Dharma Raj's enrolled embedding
# ------------------------------------------------------------

reference_path = os.path.join(KNOWN_DIR, REFERENCE)

if not os.path.exists(reference_path):
    print("ERROR: Reference image not found:")
    print(reference_path)
    input("Press Enter to exit...")
    raise SystemExit

reference_img = face_recognition.load_image_file(reference_path)
reference_locations = face_recognition.face_locations(
    reference_img,
    model="hog"
)

if not reference_locations:
    print("ERROR: No face found in reference image.")
    input("Press Enter to exit...")
    raise SystemExit

reference_encoding = face_recognition.face_encodings(
    reference_img,
    [reference_locations[0]]
)[0]

print("Reference student: DHARMA RAJ")
print("Reference image:", REFERENCE)
print("Reference embedding: OK")
print("")

# ------------------------------------------------------------
# Load embeddings for all enrolled students
# ------------------------------------------------------------

known_files = glob.glob(os.path.join(KNOWN_DIR, "*.jpg"))
known_embeddings = []

print("Loading enrolled embeddings...")

for path in known_files:
    try:
        img = face_recognition.load_image_file(path)
        locations = face_recognition.face_locations(img, model="hog")

        if not locations:
            print("  SKIPPED - no face:", os.path.basename(path))
            continue

        encoding = face_recognition.face_encodings(
            img,
            [locations[0]]
        )[0]

        known_embeddings.append(
            (os.path.basename(path), encoding)
        )

        print("  OK:", os.path.basename(path))

    except Exception as exc:
        print("  ERROR:", os.path.basename(path), exc)

print("")
print("Enrolled embeddings loaded:", len(known_embeddings))
print("")

# ------------------------------------------------------------
# Camera
# ------------------------------------------------------------

cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("ERROR: Could not open webcam.")
    input("Press Enter to exit...")
    raise SystemExit

print("Camera opened successfully.")
print("")
print("Controls:")
print("  SPACE = capture")
print("  ESC   = exit")
print("")
print("Capture your face in these conditions:")
print("  1. Straight")
print("  2. Slightly LEFT")
print("  3. Slightly RIGHT")
print("  4. Slightly UP")
print("  5. Slightly DOWN")
print("")
print("Take your time. There is NO timeout.")
print("")

poses = [
    "1/5 - Look STRAIGHT at the camera",
    "2/5 - Turn your head slightly LEFT",
    "3/5 - Turn your head slightly RIGHT",
    "4/5 - Look slightly UP",
    "5/5 - Look slightly DOWN"
]

live_embeddings = []

for instruction in poses:

    print(instruction)

    while True:
        ret, frame = cap.read()

        if not ret:
            continue

        # Mirrored preview only.
        display = cv2.flip(frame, 1)

        cv2.putText(
            display,
            instruction,
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.72,
            (0, 255, 0),
            2
        )

        cv2.putText(
            display,
            "SPACE = Capture    ESC = Exit",
            (20, 75),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.62,
            (255, 255, 255),
            2
        )

        cv2.imshow("Enrollment vs Live Camera Test", display)

        key = cv2.waitKey(1) & 0xFF

        if key == 32:

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            locations = face_recognition.face_locations(
                rgb,
                model="hog"
            )

            if not locations:
                print("  No face detected. Try again.")
                continue

            # Select the largest face.
            locations = sorted(
                locations,
                key=lambda box: (box[2] - box[0]) * (box[1] - box[3]),
                reverse=True
            )

            encodings = face_recognition.face_encodings(
                rgb,
                [locations[0]]
            )

            if not encodings:
                print("  Face found but embedding failed. Try again.")
                continue

            live_embeddings.append(encodings[0])

            print("  Captured successfully.")
            print("")
            break

        elif key == 27:

            cap.release()
            cv2.destroyAllWindows()

            print("Test cancelled.")
            raise SystemExit

cap.release()
cv2.destroyAllWindows()

# ------------------------------------------------------------
# Results
# ------------------------------------------------------------

print("")
print("============================================================")
print("  LIVE CAMERA RECOGNITION RESULTS")
print("============================================================")
print("")

for i, live in enumerate(live_embeddings):

    print(f"POSE {i + 1}")
    print("-" * 60)

    # Distance from Dharma's enrollment image.
    dharma_distance = np.linalg.norm(
        reference_encoding - live
    )

    print(
        f"Distance to DHARMA RAJ enrolled image: "
        f"{dharma_distance:.4f}"
    )

    # Compare against every enrolled student.
    results = []

    for filename, encoding in known_embeddings:
        distance = np.linalg.norm(live - encoding)
        results.append((filename, distance))

    results.sort(key=lambda x: x[1])

    print("")
    print("Closest enrolled faces:")

    for filename, distance in results[:5]:
        print(f"  {filename}: {distance:.4f}")

    best_name, best_distance = results[0]

    print("")
    print("BEST MATCH:")
    print(f"  {best_name}")
    print(f"  Distance: {best_distance:.4f}")
    print("")

print("============================================================")
print("Test complete.")
print("============================================================")

input("Press Enter to exit...")
