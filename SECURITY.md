# Security Policy

## Reporting Security Issues

We take the security and privacy of this project seriously, especially given that it handles biometric data (face embeddings) and student attendance records.

If you discover a security vulnerability or privacy concern within this repository:

1. **Do not open a public GitHub issue.**
2. Send an email to the repository owner at **`shafyy.officials25@gmail.com`** with:
   - A description of the issue and potential impact
   - Step-by-step instructions or proof-of-concept to reproduce the behavior
   - Affected files and components
3. You will receive an initial response within 48 hours acknowledging receipt.

---

## Biometric Data & Privacy Principles

### 1. Vector Embeddings
- The system computes 128-dimensional mathematical feature vectors using `dlib` / `face_recognition`.
- Embeddings are stored as structured JSON arrays rather than raw face images.
- Feature vectors are irreversible mathematical projections and cannot be reverse-engineered into original face photographs.

### 2. Local-Only Processing
- All face recognition inference, embedding storage, and database persistence occur entirely on the local host machine.
- No facial images or embedding vectors are uploaded to external cloud services or remote third-party APIs.

### 3. SMS Gateway Security
- SMS alerts transmit student attendance status notifications (late, absent, correction) without attaching facial images or biometric information.
- Environment variables (`SMS_API_KEY`, `TWILIO_AUTH_TOKEN`, etc.) must be stored in `.env` and kept strictly confidential. Never commit `.env` files to source control.

---

## Operational Recommendations

For production or campus deployment:
- **File System Permissions**: Restrict read/write permissions on `attendance.db` and `data/` to the application operator account.
- **Physical Security**: Position webcam hardware to capture only intentional student check-ins and prevent unauthorized angles.
- **Database Backups**: Use the provided `python tools/backup_db.py` to create periodic snapshots and store backups on encrypted, access-controlled storage.
