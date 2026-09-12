import numpy as np


class RecognitionDecisionEngine:
    """
    Converts individual face-recognition matches into
    stable recognition decisions.

    States:
        UNKNOWN
        CANDIDATE
        CONFIRMED

    A student must satisfy both:
        - maximum acceptable distance
        - minimum identity margin

    and remain consistent across multiple observations.
    """

    def __init__(
        self,
        max_distance=0.50,
        min_margin=0.08,
        confirmation_frames=3,
        reset_after_misses=2
    ):

        self.max_distance = float(
            max_distance
        )

        self.min_margin = float(
            min_margin
        )

        self.confirmation_frames = int(
            confirmation_frames
        )

        self.reset_after_misses = int(
            reset_after_misses
        )

        self.candidate_id = None
        self.candidate_name = None
        self.consecutive_matches = 0
        self.misses = 0

        self.confirmed_id = None
        self.confirmed_name = None

    def reset(self):

        self.candidate_id = None
        self.candidate_name = None
        self.consecutive_matches = 0
        self.misses = 0

        self.confirmed_id = None
        self.confirmed_name = None

    def evaluate(self, match):

        if not match:

            self.misses += 1

            if self.misses >= self.reset_after_misses:

                self.candidate_id = None
                self.candidate_name = None
                self.consecutive_matches = 0

                self.confirmed_id = None
                self.confirmed_name = None

            return {
                "state": "UNKNOWN",
                "student_id": None,
                "name": None,
                "distance": None,
                "margin": None,
                "consecutive_matches": 0
            }

        student_id = match.get(
            "student_id"
        )

        name = match.get(
            "name"
        )

        distance = float(
            match.get(
                "distance",
                np.inf
            )
        )

        margin = float(
            match.get(
                "margin",
                -np.inf
            )
        )

        # ------------------------------------------------------
        # Basic identity validity
        # ------------------------------------------------------

        distance_ok = (
            distance <= self.max_distance
        )

        margin_ok = (
            margin >= self.min_margin
        )

        valid = (
            student_id is not None
            and
            distance_ok
            and
            margin_ok
        )

        if not valid:

            self.misses += 1

            if self.misses >= self.reset_after_misses:

                self.candidate_id = None
                self.candidate_name = None
                self.consecutive_matches = 0

                self.confirmed_id = None
                self.confirmed_name = None

            return {
                "state": "UNKNOWN",
                "student_id": None,
                "name": None,
                "distance": distance,
                "margin": margin,
                "consecutive_matches": 0
            }

        # ------------------------------------------------------
        # Valid candidate
        # ------------------------------------------------------

        self.misses = 0

        # New identity.
        if self.candidate_id != student_id:

            self.candidate_id = student_id
            self.candidate_name = name
            self.consecutive_matches = 1

            self.confirmed_id = None
            self.confirmed_name = None

            return {
                "state": "CANDIDATE",
                "student_id": student_id,
                "name": name,
                "distance": distance,
                "margin": margin,
                "consecutive_matches": 1
            }

        # Same identity again.
        self.consecutive_matches += 1

        if (
            self.consecutive_matches
            >= self.confirmation_frames
        ):

            self.confirmed_id = student_id
            self.confirmed_name = name

            return {
                "state": "CONFIRMED",
                "student_id": student_id,
                "name": name,
                "distance": distance,
                "margin": margin,
                "consecutive_matches": (
                    self.consecutive_matches
                )
            }

        return {
            "state": "CANDIDATE",
            "student_id": student_id,
            "name": name,
            "distance": distance,
            "margin": margin,
            "consecutive_matches": (
                self.consecutive_matches
            )
        }


# ============================================================
# TEST HELPERS
# ============================================================

def make_match(
    student_id,
    name,
    distance,
    margin
):

    return {
        "student_id": student_id,
        "name": name,
        "distance": distance,
        "margin": margin
    }


def run_sequence(
    title,
    sequence,
    expected_states
):

    print()
    print("-" * 70)
    print(title)
    print("-" * 70)

    engine = RecognitionDecisionEngine(
        max_distance=0.50,
        min_margin=0.08,
        confirmation_frames=3,
        reset_after_misses=2
    )

    actual_states = []

    for index, match in enumerate(
        sequence,
        start=1
    ):

        result = engine.evaluate(
            match
        )

        state = result["state"]

        actual_states.append(
            state
        )

        print(
            f"Observation {index}: "
            f"{state:<10} | "
            f"ID={result['student_id']} | "
            f"distance={result['distance']} | "
            f"margin={result['margin']} | "
            f"streak={result['consecutive_matches']}"
        )

    passed = (
        actual_states == expected_states
    )

    print()

    print(
        f"Expected: {expected_states}"
    )

    print(
        f"Actual:   {actual_states}"
    )

    print(
        f"RESULT:   {'PASS' if passed else 'FAIL'}"
    )

    return passed


# ============================================================
# TEST 1
# Three strong consecutive matches
# ============================================================

test1 = run_sequence(
    "TEST 1 - THREE CONSECUTIVE VALID MATCHES",

    [
        make_match(
            "A24AID07",
            "SHAMEER",
            0.30,
            0.25
        ),

        make_match(
            "A24AID07",
            "SHAMEER",
            0.28,
            0.30
        ),

        make_match(
            "A24AID07",
            "SHAMEER",
            0.25,
            0.35
        )
    ],

    [
        "CANDIDATE",
        "CANDIDATE",
        "CONFIRMED"
    ]
)


# ============================================================
# TEST 2
# Distance too high
# ============================================================

test2 = run_sequence(
    "TEST 2 - DISTANCE TOO HIGH",

    [
        make_match(
            "A24AID07",
            "SHAMEER",
            0.51,
            0.30
        ),

        make_match(
            "A24AID07",
            "SHAMEER",
            0.55,
            0.35
        )
    ],

    [
        "UNKNOWN",
        "UNKNOWN"
    ]
)


# ============================================================
# TEST 3
# Margin too small
# ============================================================

test3 = run_sequence(
    "TEST 3 - IDENTITY MARGIN TOO SMALL",

    [
        make_match(
            "A24AID07",
            "SHAMEER",
            0.35,
            0.07
        ),

        make_match(
            "A24AID07",
            "SHAMEER",
            0.30,
            0.04
        )
    ],

    [
        "UNKNOWN",
        "UNKNOWN"
    ]
)


# ============================================================
# TEST 4
# Unknown person
# ============================================================

test4 = run_sequence(
    "TEST 4 - UNKNOWN PERSON",

    [
        make_match(
            "A24AID03",
            "KODEESWARAN",
            0.56,
            0.02
        ),

        make_match(
            "A24AID06",
            "MOHAMMED SHAFIULLAH",
            0.57,
            0.01
        ),

        make_match(
            "A24AID07",
            "SHAMEER",
            0.58,
            0.01
        ),

        make_match(
            "A24AID03",
            "KODEESWARAN",
            0.55,
            0.03
        )
    ],

    [
        "UNKNOWN",
        "UNKNOWN",
        "UNKNOWN",
        "UNKNOWN"
    ]
)


# ============================================================
# TEST 5
# The actual Step 16 error:
# Shameer was briefly classified as Mohammed.
# ============================================================

test5 = run_sequence(
    "TEST 5 - SINGLE WRONG IDENTITY INTERRUPTION",

    [
        make_match(
            "A24AID07",
            "SHAMEER",
            0.30,
            0.25
        ),

        make_match(
            "A24AID07",
            "SHAMEER",
            0.28,
            0.30
        ),

        # The one wrong Step 16 observation.
        make_match(
            "A24AID06",
            "MOHAMMED SHAFIULLAH",
            0.3671,
            0.1794
        ),

        make_match(
            "A24AID07",
            "SHAMEER",
            0.27,
            0.32
        ),

        make_match(
            "A24AID07",
            "SHAMEER",
            0.25,
            0.35
        ),

        make_match(
            "A24AID07",
            "SHAMEER",
            0.24,
            0.37
        )
    ],

    [
        "CANDIDATE",
        "CANDIDATE",
        "CANDIDATE",
        "CANDIDATE",
        "CANDIDATE",
        "CONFIRMED"
    ]
)


# ============================================================
# TEST 6
# Identity must restart after a genuine switch.
# ============================================================

run6_engine = RecognitionDecisionEngine(
    max_distance=0.50,
    min_margin=0.08,
    confirmation_frames=3,
    reset_after_misses=2
)

print()
print("-" * 70)
print("TEST 6 - IDENTITY SWITCH")
print("-" * 70)

sequence6 = [
    make_match(
        "A24AID07",
        "SHAMEER",
        0.28,
        0.25
    ),

    make_match(
        "A24AID07",
        "SHAMEER",
        0.27,
        0.30
    ),

    make_match(
        "A24AID07",
        "SHAMEER",
        0.25,
        0.35
    ),

    make_match(
        "A24AID06",
        "MOHAMMED SHAFIULLAH",
        0.30,
        0.25
    ),

    make_match(
        "A24AID06",
        "MOHAMMED SHAFIULLAH",
        0.28,
        0.30
    ),

    make_match(
        "A24AID06",
        "MOHAMMED SHAFIULLAH",
        0.26,
        0.35
    )
]

actual6 = []

for index, match in enumerate(
    sequence6,
    start=1
):

    result = run6_engine.evaluate(
        match
    )

    actual6.append(
        result["state"]
    )

    print(
        f"Observation {index}: "
        f"{result['state']:<10} | "
        f"{result['name']} | "
        f"streak={result['consecutive_matches']}"
    )

expected6 = [
    "CANDIDATE",
    "CANDIDATE",
    "CONFIRMED",
    "CANDIDATE",
    "CANDIDATE",
    "CONFIRMED"
]

test6 = (
    actual6 == expected6
)

print()
print(
    f"Expected: {expected6}"
)

print(
    f"Actual:   {actual6}"
)

print(
    f"RESULT:   {'PASS' if test6 else 'FAIL'}"
)


# ============================================================
# FINAL RESULTS
# ============================================================

print()
print("=" * 70)
print("STEP 17 TEST RESULTS")
print("=" * 70)
print()

all_passed = all([
    test1,
    test2,
    test3,
    test4,
    test5,
    test6
])

print(
    f"Test 1 - Consecutive confirmation: "
    f"{'PASS' if test1 else 'FAIL'}"
)

print(
    f"Test 2 - Distance rejection:       "
    f"{'PASS' if test2 else 'FAIL'}"
)

print(
    f"Test 3 - Margin rejection:         "
    f"{'PASS' if test3 else 'FAIL'}"
)

print(
    f"Test 4 - Unknown rejection:        "
    f"{'PASS' if test4 else 'FAIL'}"
)

print(
    f"Test 5 - Wrong-frame protection:   "
    f"{'PASS' if test5 else 'FAIL'}"
)

print(
    f"Test 6 - Identity switching:       "
    f"{'PASS' if test6 else 'FAIL'}"
)

print()

if all_passed:

    print(
        "STEP 17: ALL TESTS PASSED"
    )

else:

    print(
        "STEP 17: ONE OR MORE TESTS FAILED"
    )

print("=" * 70)
