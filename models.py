from sqlalchemy import Column, String, Integer, DateTime, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from database import Base
import uuid


class User(Base):
    __tablename__ = 'userDetails'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Feedback(Base):

    __tablename__ = 'feedback'
    __table_args__ = (
        UniqueConstraint("user_id", "mal_id", name="uq_user_mal_feedback"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('userDetails.id'), nullable=False, index=True)

    mal_id = Column(Integer, nullable=False)
    feedback = Column(Integer, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())