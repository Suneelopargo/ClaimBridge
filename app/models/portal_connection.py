from sqlalchemy import Boolean, Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from app.models.base import Base


class PortalConnection(Base):
    __tablename__ = "portal_connection"

    id = Column(Integer, primary_key=True, index=True)

    portal_id = Column(Integer, ForeignKey("portal.id"), nullable=False)

    connection_name = Column(String(150), nullable=False)

    hospital_name = Column(String(150), nullable=False)

    environment = Column(String(30), default="PROD")

    username = Column(String(255), nullable=False)

    encrypted_password = Column(String(1000), nullable=True)

    graph_mailbox = Column(String(255), nullable=True)

    auth_type = Column(String(50), default="USERNAME_PASSWORD_OTP")

    active = Column(Boolean, default=True)

    portal = relationship("Portal", back_populates="connections")

    claim_summaries = relationship(
        "ClaimSummary",
        back_populates="portal_connection",
        cascade="all, delete-orphan",
    )