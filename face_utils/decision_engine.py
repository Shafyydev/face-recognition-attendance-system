class RecognitionDecisionEngine:
    """
    Multi-frame recognition decision engine.

    A match must satisfy both:
        - maximum embedding distance
        - minimum identity margin

    A valid identity must then appear for several consecutive
    processed frames before it is confirmed.
    """

    UNKNOWN = "UNKNOWN"
    CANDIDATE = "CANDIDATE"
    CONFIRMED = "CONFIRMED"

    def __init__(
        self,
        max_distance=0.50,
        min_margin=0.08,
        confirmation_frames=3,
        reset_after_misses=2
    ):
        self.max_distance = float(max_distance)
        self.min_margin = float(min_margin)
        self.confirmation_frames = int(
            confirmation_frames
        )
        self.reset_after_misses = int(
            reset_after_misses
        )

        self.identities = {}
        self.current_student_id = None
        self.current_name = None
        self.streak = 0
        self.misses = 0
        self.confirmed_student_id = None
        self.confirmed_name = None

    def reset(self):
        """Clear all recognition state."""

        self.identities.clear()
        self.current_student_id = None
        self.current_name = None
        self.streak = 0
        self.misses = 0
        self.confirmed_student_id = None
        self.confirmed_name = None

    def _is_valid_match(self, match):
        """Check distance and identity margin."""

        if not match:
            return False

        student_id = match.get("student_id")

        if not student_id:
            return False

        distance = match.get("distance")

        if distance is None:
            return False

        margin = match.get("margin")

        if margin is None:
            return False

        return (
            float(distance) <= self.max_distance
            and
            float(margin) >= self.min_margin
        )

    def update(self, match):
        """
        Process one recognition observation. Supports concurrent multi-identity
        tracking so multiple faces in a frame do not cancel each other's streak.

        Returns:
            {
                "status": UNKNOWN/CANDIDATE/CONFIRMED,
                "student_id": ...,
                "name": ...,
                "streak": ...
            }
        """

        if not self._is_valid_match(match):
            self.misses += 1

            if self.misses >= self.reset_after_misses:
                self.current_student_id = None
                self.current_name = None
                self.streak = 0

                if self.confirmed_student_id is None:
                    self.confirmed_name = None

            return {
                "status": self.UNKNOWN,
                "student_id": None,
                "name": None,
                "streak": 0
            }

        student_id = match["student_id"]
        name = match["name"]

        # Track per-identity streak and misses
        rec = self.identities.setdefault(student_id, {"streak": 0, "misses": 0, "name": name})
        rec["streak"] += 1
        rec["misses"] = 0
        rec["name"] = name
        streak = rec["streak"]

        self.current_student_id = student_id
        self.current_name = name
        self.streak = streak
        self.misses = 0

        if streak >= self.confirmation_frames:
            self.confirmed_student_id = student_id
            self.confirmed_name = name

            return {
                "status": self.CONFIRMED,
                "student_id": student_id,
                "name": name,
                "streak": streak
            }

        return {
            "status": self.CANDIDATE,
            "student_id": student_id,
            "name": name,
            "streak": streak
        }

    def decay_unseen(self, seen_student_ids):
        """Decay streak for identities not seen in the current frame."""
        seen = set(seen_student_ids or [])
        to_delete = []
        for sid, rec in self.identities.items():
            if sid not in seen:
                rec["misses"] += 1
                if rec["misses"] >= self.reset_after_misses:
                    to_delete.append(sid)
        for sid in to_delete:
            del self.identities[sid]


if __name__ == "__main__":
    print("=" * 60)
    print("RECOGNITION DECISION ENGINE TEST")
    print("=" * 60)

    engine = RecognitionDecisionEngine(
        max_distance=0.50,
        min_margin=0.08,
        confirmation_frames=3,
        reset_after_misses=2
    )

    valid_shameer = {
        "student_id": "A24AID07",
        "name": "SHAMEER",
        "distance": 0.25,
        "second_best_distance": 0.55,
        "margin": 0.30
    }

    for _ in range(3):
        result = engine.update(valid_shameer)

    assert result["status"] == "CONFIRMED"

    engine.reset()

    high_distance = {
        "student_id": "A24AID07",
        "name": "SHAMEER",
        "distance": 0.60,
        "second_best_distance": 0.70,
        "margin": 0.10
    }

    result = engine.update(high_distance)
    assert result["status"] == "UNKNOWN"

    engine.reset()

    low_margin = {
        "student_id": "A24AID07",
        "name": "SHAMEER",
        "distance": 0.30,
        "second_best_distance": 0.32,
        "margin": 0.02
    }

    result = engine.update(low_margin)
    assert result["status"] == "UNKNOWN"

    print("DECISION ENGINE TEST: PASSED")
