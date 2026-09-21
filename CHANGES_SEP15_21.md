# CHANGELOG: September 15–21, 2026

This document summarizes all code changes, features, fixes, and removals
made between September 15 and September 21, 2026.

---

## Sept 15 — Late Arrival Tracking & UI Refinement

### Commit `1ca2ace` — "modified"
- **File**: `face_utils/face_encoder.py`
- Minor modification (details not specified in commit message).

### Commit `3ce0235` — "feat: add late arrival tracking, 12-hr time format, and simplify dept table"
**Core late-arrival logic:**
- `face_utils/attendance_marker.py`:
  - Added `LATE_AFTER` constant set to `08:30` (8:30 AM).
  - `mark_attendance()` now marks students as `"late"` (if check-in time is past `LATE_AFTER`) or `"on_time"` instead of hardcoded `"present"`.
- `app.py`:
  - `GET /api/stats`: Counts `on_time` + `late` statuses as "present" (backward compatible with legacy `"present"` records). Added a `late` count field to the stats response.
- `face_utils/face_encoder.py`:
  - Restored `import sys` needed for frozen-mode (executable) path detection.

**12-hour time format:**
- `app.py`: All `strftime` time displays changed to 12-hour format (`%I:%M:%S %p`).
- `templates/dashboard.html`: Clock and "Updated" timestamps converted to 12-hour format using `en-IN` locale.

**Dashboard layout:**
- `templates/dashboard.html`: Simplified department table to show only Student ID and Status columns.
- Added a new "Late today" stat card with amber badge styling.

### Commit `7e90e09` — "Late entry ui fixed"
- **Files**: `patch.py`, `templates/dashboard.html`
- Added `patch.py` — a temporary utility script (32 lines) for UI adjustments.
- Dashboard UI fixes for late entry display.

### Commit `096a7fe` — "feat: change Department table to show ID + Name (was ID + Status)"
- **File**: `templates/dashboard.html`
- Department table now shows Student ID (35% width) and Name (65% width).
- Late Comers table retains ID + Status (50%/50% split).
- Both tables remain independent with their own dept chips.

### Commits `02411e1` → `4a8d656` — Late Comers table layout refinement chain
Five iterative commits refining the Late Comers dashboard section:

1. **`111f79b`**: Split dept table into Dept + Late Comers side-by-side tables.
2. **`02411e1`**: Added independent Late Comers section with department chips.
3. **`ce3dbfa`**: Moved Late Comers into the Department card as a split-table layout.
4. **`4a8d656`**: Moved Late Comers to a separate full-width card positioned between `main-grid` and `bottom-grid`.
5. **`0852926`**: Aligned By Department, Late Comers, and Recent Activity horizontally.

### Commits `be3736f` → `a578804` — Table rendering fixes
1. **`be3736f`**: Center-aligned ID column content in collapsible dept/late tables.
2. **`f5fe683`**: Centered content evenly in dept/late tables (equal 50% columns, inline-block id-chip).
3. **`a578804`**: Prevented student ID truncation in the live attendance table.

### Commit `a178ed0` — "fix: restore raw string prefix in FaceEncoder path"
- **File**: `face_utils/face_encoder.py`
- Restored `r'...'` prefix that was accidentally removed, fixing escape sequence issues (e.g., `\a` became bell character).

### Commit `4f83312` — "docs: add September 15 changelog"
- **File**: `TODAY_UPDATES_SEP15.md` (new, 202 lines)
- Comprehensive changelog documenting the late arrival feature and all UI changes.

---

## Sept 17 — SMS Alerting Feature (Added then Reverted)

### Commit `efb63d1` — "Late SMS aleart added"
**Major feature: SMS alerts for late arrivals.**

**New files (6 files, ~900 lines added):**
- `face_utils/notification_service.py` — Standalone notification service module (~350 lines).
  - Provider-agnostic HTTP-based SMS abstraction (no specific API hard-coded).
  - Reads config from environment variables: `SMS_API_URL`, `SMS_API_KEY`, `SMS_SENDER_ID`.
  - Sends SMS to both student and parent mobile numbers when a late arrival is detected.
  - Indian mobile number validation (10 digits, starts with 6-9).
  - Asynchronous background thread for SMS sends (non-blocking).
  - Activity log integration for "Late alert sent" events.
  - Does NOT import Flask — safe for the separate OS recognition worker process.
- `database/models.py`:
  - Added `student_mobile` (String(15)) and `parent_mobile` (String(15)) columns to `Student` model.
  - Added `ensure_mobile_columns()` migration function that uses `PRAGMA table_info` to safely add columns to existing databases.
- `app.py`:
  - `POST /api/register`: Extracts and stores `student_mobile` and `parent_mobile` from registration form data.
  - `PUT /api/students/<id>`: Updates mobile fields and logs changes in activity log.
  - `GET /api/students` and dashboard index route: Includes mobile fields in JSON responses.
- `templates/register.html`:
  - Added "Student Mobile" and "Parent Mobile" input fields with client-side validation.
- `templates/dashboard.html`:
  - Student edit modal: Added mobile number input fields.
  - Student manager table: Added "Student Mobile" and "Parent Mobile" columns (7 total columns).
  - CSV export and print report: Include mobile columns.
- `tests/test_late_sms.py` — Comprehensive test suite (~340 lines).
- `.env.example` — Environment variable template for SMS configuration.
- `.gitignore` — Added `.env` and `.env.local` entries.

### Commit `bc08bc3` — "Recognition issue fixed"
- **Files**: `app.py`, `face_utils/attendance_marker.py`, `templates/dashboard.html`
- Fixed recognition issue (likely related to the SMS alerting changes).

### Commit `f020e16` — "Students and parents nnumbers moved inside students page"
- **Files**: `app.py`, `templates/dashboard.html`
- Mobile number fields moved/displayed within the student management page.

### Commit `8d44b1c` — "Real-time late arrival SMS added through SMSGate"
- **Files**: `notification_service.py`, `templates/dashboard.html`, `templates/register.html`, `tests/test_late_sms.py`
- Enhanced the SMS notification service with real-time capabilities.

### ⚠️ Revert (Sep 16, after user request)
- All SMS alerting changes were **reverted**:
  - Modified files restored via `git checkout`
  - New files deleted: `.env.example`, `notification_service.py`
- The working tree was returned to a clean state.

---

## Sept 17 — College Branding Updates

### Commit `91a8264` — "Header and logo changed to college details"
- **Files**: `static/college_logo.jpg`, `templates/dashboard.html`, `templates/register.html`
- Added college logo image.
- Updated header and logo in both dashboard and registration pages.

---

## Sept 21 — SMSGate Cloud API Integration & Documentation

### Commit `b9de9a9` — "SMS: switch to smsgate cloud API - reliable background delivery"
- **File**: `notification_service.py`
- Complete rewrite of notification service to use SMSGate Cloud API.
- Improved background delivery with retry mechanism.
- Enhanced SMS message formatting with timestamps.
- (~399 lines added, ~25 lines removed)

### Commit `ba7a4f4` — "docs: add changelog for Sep 15-21; delete .env.example; fix variable name typo in app.py"
- **New file**: `CHANGES_SEP15_21.md` — This comprehensive changelog.
- **Deleted**: `.env.example`
- **Fixed**: `app.py` variable name typo (`global _recognition_frame` → `global recognition_frame`).
- **Enhanced**: `notification_service.py` with real-time `.env` reloading (`load_dotenv(override=True)`) and time in SMS messages.

---

## Current State (as of Sep 21)

### Uncommitted changes:
- `app.py`: `global _recognition_frame` → `global recognition_frame` (minor variable name fix)
- `.env.example`: deleted

### Key files present on disk:
| File | Status |
|---|---|
| `app.py` | Modified (uncommitted variable rename fix) |
| `templates/dashboard.html` | Latest state (college branding) |
| `templates/register.html` | Latest state |
| `face_utils/attendance_marker.py` | Latest state (late tracking active) |
| `database/models.py` | Latest state (no mobile columns — reverted) |
| `face_utils/face_encoder.py` | Latest state (raw string prefix fixed) |
| `notification_service.py` | Present in root (untracked copy) |
| `tests/test_late_sms.py` | Present (untracked copy) |
| `static/college_logo.jpg` | Present (committed) |
| `.gitignore` | Latest state (clean, no `.env` entry) |
| `TODAY_UPDATES.md` | Present |
| `TODAY_UPDATES_SEP15.md` | Present (committed) |
| `patch.py` | Present (committed) |

### Branch status:
- 2 commits ahead of remote (`b9de9a9` and `ba7a4f4`)
- Both commits are pushed to GitHub

---

## Summary Table

| Date | Commit | Feature/Fix | Files Changed |
|---|---|---|---|
| Sep 15 | `1ca2ace` | Face encoder modification | 1 file |
| Sep 15 | `3ce0235` | Late arrival tracking, 12-hr format, dept table | 4 files |
| Sep 15 | `7e90e09` | Late entry UI fix | 2 files |
| Sep 15 | `096a7fe` | Dept table shows ID+Name | 1 file |
| Sep 15 | `02411e1`→`4a8d656` | Late Comers layout refinement (5 commits) | 1 file |
| Sep 15 | `be3736f`→`a578804` | Table rendering fixes (3 commits) | 1 file |
| Sep 15 | `a178ed0` | Raw string prefix restore | 1 file |
| Sep 15 | `4f83312` | Sep 15 changelog docs | 1 file |
| Sep 17 | `efb63d1` | SMS alerting feature (added) | 9 files |
| Sep 17 | `bc08bc3` | Recognition issue fix | 3 files |
| Sep 17 | `f020e16` | Mobile numbers in students page | 2 files |
| Sep 17 | `8d44b1c` | Real-time SMS through SMSGate | 4 files |
| Sep 16 | *(revert)* | SMS alerting feature reverted | 9 files reverted |
| Sep 17 | `91a8264` | College branding (logo) | 3 files |
| Sep 21 | `b9de9a9` | SMSGate Cloud API integration — background delivery | 1 file |
| Sep 21 | `ba7a4f4` | Changelog, .env.example deletion, app.py fix, notification_service.py enhancement | 4 files |
