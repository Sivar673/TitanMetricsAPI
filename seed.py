"""Populate the dev database with a coach, six clients, and ten weeks of
check-ins and workouts. Idempotent: refuses to run against a non-empty DB.

    .venv/bin/python seed.py
"""

import math
from datetime import date, timedelta

from app.database import Base, SessionLocal, engine
from app.models import CheckIn, User, WorkoutSession

WEEKS = 10

CLIENTS = [
    # id, name, phase, weeks_out, start weight, lbs/week, bench start, squat start, macro base
    ("c_1", "Marcus T.", "prep", 8, 194.0, -1.3, 265, 335, 6),
    ("c_2", "Devon R.", "off_season", None, 198.0, 0.55, 245, 315, 5),
    ("c_3", "Andre K.", "prep", 4, 189.0, -1.8, 275, 350, 7),
    ("c_4", "Jalen W.", "off_season", None, 176.0, 0.4, 205, 275, 4),
    ("c_5", "Tommy V.", "recovery", None, 208.0, 1.1, 285, 365, 5),
    ("c_6", "Sam O.", "peak_week", 1, 172.0, -0.9, 255, 320, 7),
]

DAY_WOBBLE = [0.6, 0.2, -0.1, 0.3, -0.4, 0.1, -0.3]


def monday_weeks_ago(n: int) -> date:
    today = date.today()
    return today - timedelta(days=today.weekday()) - timedelta(weeks=n)


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(User).count() > 0:
            print("Database already has users — refusing to reseed. Delete titan_metrics.db first.")
            return

        db.add(
            User(id="coach_1", email="coach@titanmetrics.com", display_name="Coach Rithish", role="coach")
        )

        for cid, name, phase, weeks_out, start_w, slope, bench0, squat0, macro_base in CLIENTS:
            cutting = phase in ("prep", "peak_week")
            db.add(
                User(
                    id=cid,
                    email=f"{name.split()[0].lower()}@example.com",
                    display_name=name,
                    role="client",
                    phase=phase,
                    weeks_out=weeks_out,
                )
            )

            # Oldest week first: weeks_ago runs WEEKS..1, leaving the current
            # week open so a fresh check-in from the app doesn't 409.
            for i, weeks_ago in enumerate(range(WEEKS, 0, -1)):
                week = monday_weeks_ago(weeks_ago)
                base = start_w + slope * i + math.sin(i * 2.1) * 0.5

                weights = [round(base + wobble, 1) for wobble in DAY_WOBBLE]
                weights[(i + 3) % 7] = None  # everyone misses one weigh-in a week

                # Fatigue climbs late into a cut; easy elsewhere
                strain = min(2, i // 4) if cutting else 0
                fatigue = {
                    "sleep_quality": max(1, 4 - strain),
                    "muscle_soreness": min(5, 2 + strain),
                    "training_motivation": max(1, 4 - strain // 2),
                    "hunger": min(5, 2 + (2 * strain if cutting else 0)),
                    "stress": 2 + (i % 2),
                }

                db.add(
                    CheckIn(
                        client_id=cid,
                        week_start=week.isoformat(),
                        morning_weights_lbs=weights,
                        macro_adherent_days=min(7, macro_base + (i % 2)),
                        fatigue=fatigue,
                        notes=None,
                    )
                )

                # Two logged sessions a week: bench day and squat day
                bench_top = round(bench0 + 3.2 * i + math.sin(i * 1.7) * 2, 0)
                squat_top = round(squat0 + 4.1 * i + math.sin(i * 1.3) * 3, 0)
                for day_offset, split, lift, top in (
                    (1, "chest_back", "Bench Press", bench_top),
                    (3, "legs", "Back Squat", squat_top),
                ):
                    performed = week + timedelta(days=day_offset)
                    db.add(
                        WorkoutSession(
                            client_id=cid,
                            performed_at=f"{performed.isoformat()}T17:30:00+00:00",
                            split_day=split,
                            exercises=[
                                {
                                    "name": lift,
                                    "order": 1,
                                    "sets": [
                                        {"set_number": 1, "weight_lbs": top * 0.6, "reps": 8, "rpe": None, "is_working_set": False},
                                        {"set_number": 2, "weight_lbs": top, "reps": 5, "rpe": 8.5, "is_working_set": True},
                                        {"set_number": 3, "weight_lbs": top - 10, "reps": 6, "rpe": 8.0, "is_working_set": True},
                                        {"set_number": 4, "weight_lbs": top - 20, "reps": 8, "rpe": 8.0, "is_working_set": True},
                                    ],
                                }
                            ],
                            session_notes=None,
                        )
                    )

        db.commit()
        print(f"Seeded 1 coach, {len(CLIENTS)} clients, {WEEKS} weeks of history each.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
