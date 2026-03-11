from sqlalchemy import create_engine, String, Integer, DateTime
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Mapped, mapped_column
from datetime import datetime, timedelta
import os

class Base(DeclarativeBase):
    pass

# Store user mood and interaction timestamp
class UserMood(Base):
    __tablename__ = "user_moods"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    mood: Mapped[str] = mapped_column(String, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

# Init DB connection
DATABASE_URL = "sqlite:///data/fluxy.db"
engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)


# Save or update a user's mood
def save_user_mood(user_id: int, mood: str):
    session = SessionLocal()
    entry = session.query(UserMood).filter_by(user_id=str(user_id)).first()

    if entry:
        entry.mood = mood
        entry.timestamp = datetime.utcnow()
    else:
        entry = UserMood(user_id=str(user_id), mood=mood)
        session.add(entry)

    session.commit()
    session.close()

# Get the latest mood
def get_user_mood(user_id: int, default: str = "friendly") -> str:
    session = SessionLocal()
    entry = session.query(UserMood).filter_by(user_id=str(user_id)).first()
    session.close()
    return str(entry.mood) if entry else default

# Delete moods older than 2 weeks
def purge_old_data():
    session = SessionLocal()
    threshold = datetime.utcnow() - timedelta(weeks=2)
    session.query(UserMood).filter(UserMood.timestamp < threshold).delete()
    session.commit()
    session.close()
