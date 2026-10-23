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

        self.current_student_id = None
        self.current_name = None
        self.streak = 0
        self.misses = 0
        self.confirmed_student_id = None
        self.confirmed_name = None

    def reset(self):
        """Clear all recognition state."""

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
        Process one recognition observation.

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

        self.misses = 0

        # Identity changed.
        if (
            self.current_student_id is not None
            and
            self.current_student_id != student_id
        ):
            self.current_student_id = student_id
            self.current_name = name
            self.streak = 1

            # A new identity must earn confirmation again.
            self.confirmed_student_id = None
            self.confirmed_name = None

            return {
                "status": self.CANDIDATE,
                "student_id": student_id,
                "name": name,
                "streak": self.streak
            }

        # Same identity continues.
        if self.current_student_id == student_id:
            self.streak += 1
        else:
            self.current_student_id = student_id
            self.current_name = name
            self.streak = 1

        if self.streak >= self.confirmation_frames:
            self.confirmed_student_id = student_id
            self.confirmed_name = name

            return {
                "status": self.CONFIRMED,
                "student_id": student_id,
                "name": name,
                "streak": self.streak
            }

        return {
            "status": self.CANDIDATE,
            "student_id": student_id,
            "name": name,
            "streak": self.streak
        }


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
