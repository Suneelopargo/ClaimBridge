from datetime import datetime, timedelta, timezone
from sqlalchemy import Column, DateTime, Integer, String
from app.models.base import Base


def ist_now() -> datetime:
    # Persist IST wall-clock time as a naive datetime for compatibility with existing schema.
    ist_timezone = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(timezone.utc).astimezone(ist_timezone).replace(tzinfo=None)


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), index=True, nullable=True)
    action_type = Column(String(100), index=True, nullable=False)
    target = Column(String(200), index=True, nullable=False)
    details = Column(String(1000), nullable=True)
    ip_address = Column(String(50), nullable=True)
    timestamp = Column(
        DateTime,
        default=ist_now,
        index=True,
        nullable=False,
    )
