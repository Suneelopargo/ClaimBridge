from sqlalchemy import Boolean, Column, Integer, String
from sqlalchemy.orm import relationship

from app.models.base import Base


class Portal(Base):
    __tablename__ = "portal"

    id = Column(Integer, primary_key=True, index=True)

    code = Column(String(20), unique=True, nullable=False)

    name = Column(String(100), nullable=False)

    description = Column(String(500))

    base_url = Column(String(500), nullable=False)

    active = Column(Boolean, default=True)

    connections = relationship(
        "PortalConnection",
        back_populates="portal",
        cascade="all, delete-orphan",
    )