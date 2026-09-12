import cv2
import face_recognition
import numpy as np
import time

print("Starting camera...")
print("")

cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("ERROR: Could not open webcam.")
    input("Press Enter to exit...")
    raise SystemExit

print("Camera opened successfully.")
print("")
print("Controls:")
print("  SPACE = capture current pose")
print("  ESC   = cancel")
print("")
print("There is NO timeout. Take your time.")
print("")

captures = []

instructions = [
    "1/5 - Look STRAIGHT at the camera",
    "2/5 - Turn your head slightly LEFT",
    "3/5 - Turn your head slightly RIGHT",
    "4/5 - Look slightly UP",
    "5/5 - Look slightly DOWN"
]

for instruction in instructions:

    print(instruction)

    while True:
        ret, frame = cap.read()

        if not ret:
            print("  Camera frame could not be read.")
            continue

        # Mirror the preview like a normal selfie camera.
        display = cv2.flip(frame, 1)

        cv2.putText(
            display,
            instruction,
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.75,
            (0, 255, 0),
            2
        )

        cv2.putText(
            display,
            "SPACE = Capture    ESC = Cancel",
            (20, 75),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (255, 255, 255),
            2
        )

        cv2.imshow("Face Embedding Test", display)

        key = cv2.waitKey(1) & 0xFF

        if key == 32:  # SPACE

            # Use the ORIGINAL camera frame for recognition.
            # The mirrored image is only for display.
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            locations = face_recognition.face_locations(
                rgb,
                model="hog"
            )

            if not locations:
                print("  No face detected. Adjust your position and try again.")
                continue

            # Use the largest detected face.
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
                print("  Face found, but embedding failed. Try again.")
                continue

            captures.append(encodings[0])

            print("  Captured successfully.")
            print("")

            break

        elif key == 27:  # ESC

            cap.release()
            cv2.destroyAllWindows()

            print("Test cancelled.")
            raise SystemExit

    time.sleep(0.7)

cap.release()
cv2.destroyAllWindows()

print("")
print("============================================================")
print("EMBEDDING ROBUSTNESS RESULTS")
print("============================================================")

base = captures[0]

for i, embedding in enumerate(captures):
    distance = np.linalg.norm(base - embedding)
    print(f"Pose {i + 1} vs straight: {distance:.4f}")

print("")
print("Pairwise distances:")

for i in range(len(captures)):
    for j in range(i + 1, len(captures)):
        distance = np.linalg.norm(
            captures[i] - captures[j]
        )
        print(f"Pose {i + 1} vs Pose {j + 1}: {distance:.4f}")

print("")
print("Test complete.")
input("Press Enter to exit...")
