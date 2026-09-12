import os
import cv2
import numpy as np
import face_recognition

from face_utils.face_embedding_store import FaceEmbeddingStore
from face_utils.embedding_encoder import EmbeddingEncoder


STORAGE_DIR = (
    r"D:\codehub\attendance_system\data"
    r"\face_embeddings"
)

STUDENT_ID = "A24AID06"
STUDENT_NAME = "MOHAMMED SHAFIULLAH"


print("=" * 70)
print("PERSISTENT EMBEDDING RECOGNITION TEST")
print("=" * 70)
print()

store = FaceEmbeddingStore(
    storage_dir=STORAGE_DIR
)

encoder = EmbeddingEncoder()

# ------------------------------------------------------------
# Load every student from persistent JSON storage.
# ------------------------------------------------------------

print("Loading persistent embeddings...")
print()

students = store.load_all()

if not students:

    print("ERROR: No persistent embeddings found.")
    raise SystemExit(1)

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
print(
    f"Persistent students loaded: "
    f"{len(students)}"
)

print()

# ------------------------------------------------------------
# Verify Mohammed specifically.
# ------------------------------------------------------------

if STUDENT_ID not in students:

    print(
        f"ERROR: {STUDENT_ID}.json was not loaded."
    )

    raise SystemExit(1)

print(
    f"Verified persistent enrollment for "
    f"{STUDENT_NAME}."
)

print()

print("=" * 70)
print("LIVE RECOGNITION TEST")
print("=" * 70)
print()

print(
    "Have Mohammed stand in front of the camera."
)

print(
    "Move naturally for around 30 seconds."
)

print(
    "Try straight, left, right, up, down, "
    "and different expressions."
)

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

                results.append(match)

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

                now = __import__("time").time()

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
        "Q = quit",
        (20, display.shape[0] - 20),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (255, 255, 255),
        2
    )

    cv2.imshow(
        "Persistent Embedding Recognition Test",
        display
    )

    frame_count += 1

    key = cv2.waitKey(1) & 0xFF

    if key == ord("q"):
        break


cap.release()
cv2.destroyAllWindows()

print()
print("=" * 70)
print("PERSISTENT RECOGNITION SUMMARY")
print("=" * 70)

if not results:

    print(
        "No recognition samples collected."
    )

else:

    distances = [
        result["distance"]
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
        f"Correct Mohammed matches: "
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

    print("MATCH DISTRIBUTION:")

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
print("TEST COMPLETE")
print("=" * 70)
