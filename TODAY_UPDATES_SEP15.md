# Summary of Updates — September 15, 2026

All changes made to the **Face Recognition Attendance System** on September 15, 2026.

---

## Files Changed Today

| File | Changes |
| :--- | :--- |
| `app.py` | Late count in stats, 3→2 column width adjustment, 12-hr time format |
| `face_utils/attendance_marker.py` | Late arrival tracking (8:30 AM cutoff), async notification trigger |
| `face_utils/face_encoder.py` | Restored `import sys` + raw string prefix |
| `templates/dashboard.html` | Late Entry section, 12-hr clock, late status badge, ID column fix |
| `patch.py` | New helper script for Late Entry UI changes |

---

## Changes by Feature

### 1. Late Arrival Tracking (8:30 AM Cutoff)

| Aspect | Before | After |
|---|---|---|
| `mark_attendance()` status | Hardcoded `"present"` | `"late"` if after 8:30 AM, else `"on_time"` |
| `LATE_AFTER` | did not exist | `time(8, 30)` — Chennai local time cutoff |
| DB migration | n/a | One-time SQL update: `status="late" WHERE time(date) > '08:30:00'` |
| Backward compat | n/a | `/api/stats` counts `on_time + late + present` as present |

**Files**: `face_utils/attendance_marker.py`, `app.py`

```
Before: status="present"
After:  status="late" or "on_time" based on datetime.now().time() > time(8, 30)
```

### 2. Stats Endpoint Enhancement

`/api/stats` response:
```json
// Before
{"total": 15, "present": 10, "absent": 5, "percent": 66.7}

// After
{"total": 15, "present": 10, "late": 8, "absent": 5, "percent": 66.7}
```

- `present` now counts `status IN ('on_time', 'late', 'present')` (backward compatible)
- `late` counts records where `status == 'late'`

**File**: `app.py`

### 3. 12-Hour Time Format

| Location | Before | After |
|---|---|---|
| Activity log time | `%H:%M:%S` | `%I:%M:%S %p` (e.g., `08:47:16 PM`) |
| Attendance table time | `%H:%M:%S` | `%I:%M:%S %p` |
| CSV export time | `%H:%M:%S` | `%I:%M:%S %p` |
| Dashboard clock | `toLocaleTimeString()` | `toLocaleTimeString('en-IN', { hour12: true })` |
| "Updated:" timestamp | `toLocaleTimeString()` | `toLocaleString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: true })` |

**Files**: `app.py`, `templates/dashboard.html`

### 4. Late Entry Dashboard Section

New **Late Entry** card added to the bottom-grid (3-column layout):

```
[By department] [Late Entry] [Recent activity]
```

| Feature | Details |
|---|---|
| **Chips** | `#late-chips` — shows departments with late-student counts (e.g., `CSE — 3`) |
| **Total badge** | `#late-total-badge` — shows total late students (e.g., `8`) in card header |
| **Table** | Collapsible: ID + Status columns, `id-chip` styling, status badges |
| **Toggle** | Click chip to expand, click again to collapse, click another to switch |
| **Polling** | `renderLateChips()` called every 2 seconds via `refreshData()` |
| **Guard** | `lastLateKey` key-guard prevents unnecessary re-renders (same pattern as `renderDepts`) |
| **Empty state** | "No late arrivals yet" chip when no late students |
| **Independent** | Separate chips, table, and toggle state from the Department table |
| **Reset** | `clearToday()` and date-filter changes reset late state |

**File**: `templates/dashboard.html`

### 5. Late Status Badge

```css
.status-tag.late {
    background: rgba(245,158,11,0.22);
    color: #fbbf24;
    box-shadow: 0 0 8px rgba(245,158,11,0.3);
}
```

- **"On Time"** → green badge (`.status-tag.present`)
- **"Late"** → amber badge with glow (`.status-tag.late`)
- **"Already"** → amber badge (`.status-tag.already`)
- Legacy `"present"` status displays as "On Time" (backward compatible)

### 6. Late Today Stat Card

New stat card in `.stats-grid` (now 4-column instead of 3):
```
[Attendance rate] [Total] [Present] [Late today] [Absent]
```

### 7. Department Table Column Change

| Column | Before | After |
|---|---|---|
| Col 1 | ID | ID |
| Col 2 | Status | Name |
| Col 3 | Time | — (removed) |
| Col 4 | Year | — (removed) |
| Col 5 | Status | — (removed) |

The Department table now shows **ID + Name** (was ID + 4 other columns).
The **Late Entry** table keeps **ID + Status** columns.

**Column widths**:
- Department table: ID 35%, Name 65%
- Late Entry table: ID 50%, Status 50%

### 8. Live Attendance Table Fixes

| Issue | Fix |
|---|---|
| Student ID truncated to 2 chars ("A2") | Increased ID column from 14% to 18%, disabled `overflow-x: hidden` (changed to `auto`) |
| Uneven content spacing | Both columns 50%/50%, `id-chip` set to `display: inline-block` |

### 9. FaceEncoder Bug Fixes

| Issue | Fix |
|---|---|
| `NameError: name 'sys' is not defined` | Restored `import sys` in `face_utils/face_encoder.py` |
| Path escape sequence bug | Restored `r"..."` raw-string prefix on `known_faces_dir` |

### 10. Bottom-Grid Layout

Changed from 2-column to 3-column grid:
```css
.bottom-grid { grid-template-columns: 1fr 1fr 1fr; }
```

Responsive breakpoints:
- Desktop (≥1101px): 3 columns
- Tablet (1100-721px): 2 columns
- Mobile (≤720px): 1 column (stacked)

---

## Commit History (Today)

| Commit | Message |
| :--- | :--- |
| `a178ed0` | fix: restore raw string prefix in FaceEncoder path |
| `7e90e09` | Late entry ui fixed |
| `096a7fe` | feat: change Department table to show ID + Name (was ID + Status) |
| `a578804` | fix: prevent student ID truncation in live attendance table |
| `f5fe683` | fix: center content evenly in dept/late tables |
| `be3736f` | fix: center-align ID column content in collapsible dept/late tables |
| `0852926` | feat: align By Department, Late Comers, and Recent Activity horizontally |
| `4a8d656` | feat: Late Comers as separate full-width card between main-grid and bottom-grid |
| `ce3dbfa` | feat: move Late Comers into Department card (reverted) |
| `02411e1` | feat: add independent Late Comers section with dept chips |
| `111f79b` | feat: split dept table into dept + late comers (reverted) |
| `3ce0235` | feat: add late arrival tracking, 12-hr time format, simplify dept table |

*Note: `ce3dbfa`, `111f79b`, `4a8d656` were intermediate iterations that were superseded by the final 3-column bottom-grid layout.*

---

## Architecture Summary

```
┌─────────────────────────────────────┐
│  Header (live clock, nav)          │
├─────────────────────────────────────┤
│  Stats (4 cols)                     │
│  [Rate] [Total] [Present] [Late] [Absent]  │
├─────────────────────────────────────┤
│  Main Grid (2-col)                  │
│  [Live Camera] [Live Attendance]    │
├─────────────────────────────────────┤
│  Bottom Grid (3-col)                │
│  [By Department] [Late Entry] [Recent Activity] │
└─────────────────────────────────────┘
```

**Key data flow**:
```
recognition_worker.py
  → process_frame()
    → _start_attendance_mark()
      → _mark_attendance_background()
        → mark_attendance()  ← sets status="late"/"on_time", commits to DB
        → (NEW) triggers SMS alert for late students after commit
```

*Generated on September 15, 2026.*
