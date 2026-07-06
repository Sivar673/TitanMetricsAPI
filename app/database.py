from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

SQLALCHEMY_DATABASE_URL = "sqlite:///./titan_metrics.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    # SQLite defaults to one-thread-per-connection; FastAPI serves
    # requests from a threadpool, so this must be off.
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
