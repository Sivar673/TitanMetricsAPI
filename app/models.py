from sqlalchemy import JSON, Column, ForeignKey, Integer, String

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False)
    display_name = Column(String, nullable=False)
    role = Column(String, nullable=False)  # "coach" | "client"
    phase = Column(String, nullable=True)  # prep | off_season | peak_week | recovery
    weeks_out = Column(Integer, nullable=True)  # null when not in prep


class CheckIn(Base):
    __tablename__ = "check_ins"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    client_id = Column(String, ForeignKey("users.id"), nullable=False)
    week_start = Column(String, nullable=False)  # ISO date, Monday
    morning_weights_lbs = Column(JSON, nullable=False)  # 7 entries Mon-Sun, null = missed
    macro_adherent_days = Column(Integer, nullable=False)
    fatigue = Column(JSON, nullable=False)  # {marker: 1-5}
    notes = Column(String, nullable=True)


class WorkoutSession(Base):
    __tablename__ = "workout_sessions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    client_id = Column(String, ForeignKey("users.id"), nullable=False)
    performed_at = Column(String, nullable=False)  # ISO 8601 datetime
    split_day = Column(String, nullable=False)
    # Full exercise/set detail as posted by the app. JSON keeps the MVP
    # schema-flexible; promote to relational tables when queries need it.
    exercises = Column(JSON, nullable=False)
    session_notes = Column(String, nullable=True)
