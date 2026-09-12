import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cv2
from face_utils.face_encoder import FaceEncoder
from database.models import get_session, Student

def register_student():
    print("=" * 50)
    print("STUDENT REGISTRATION")
    print("=" * 50)
    
    student_id = input("Student ID: ")
    name = input("Full Name: ")
    department = input("Department: ")
    year = input("Year: ")
    
    cap = cv2.VideoCapture(0)
    print("\n📸 Press SPACE to capture, ESC to cancel")
    print("💡 Make sure you have good lighting and look straight at the camera")
    
    while True:
        ret, frame = cap.read()
        if not ret:
            print("❌ Cannot access camera!")
            break
        
        # FLIP THE FRAME HORIZONTALLY (mirror)
        frame = cv2.flip(frame, 1)
        
        cv2.putText(frame, f"Register: {name}", (10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.putText(frame, "Press SPACE to capture, ESC to cancel", (10, 60), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        # Draw a face frame guide
        h, w = frame.shape[:2]
        cv2.rectangle(frame, (w//4, h//4), (3*w//4, 3*h//4), (255, 255, 0), 2)
        cv2.putText(frame, "Place face here", (w//4, h//4 - 10), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
        
        cv2.imshow("Register Face", frame)
        
        key = cv2.waitKey(1) & 0xFF
        if key == 27:  # ESC
            print("❌ Registration cancelled")
            break
        elif key == 32:  # SPACE
            encoder = FaceEncoder()
            success, msg = encoder.register_face(student_id, name, frame)
            if success:
                session = get_session()
                student = Student(
                    student_id=student_id, 
                    name=name, 
                    department=department, 
                    year=year
                )
                session.add(student)
                session.commit()
                session.close()
                print(f"✅ {name} registered successfully!")
                break
            else:
                print(f"❌ {msg}")
                print("💡 Try again with better lighting and look straight at camera")
    
    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    register_student()
