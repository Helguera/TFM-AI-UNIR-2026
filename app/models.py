from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    cameras = relationship("Camera", back_populates="owner")
    telegram_config = relationship("TelegramConfig", back_populates="user", uselist=False)


class Camera(Base):
    __tablename__ = "cameras"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    rtsp_url = Column(String(500), nullable=False)
    location = Column(String(200), nullable=True)
    is_active = Column(Boolean, default=True)
    is_running = Column(Boolean, default=False)
    
    # Detection settings
    confidence_threshold = Column(Float, default=0.55)
    confirm_frames = Column(Integer, default=5)
    cooldown_seconds = Column(Integer, default=20)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    owner_id = Column(Integer, ForeignKey("users.id"))

    owner = relationship("User", back_populates="cameras")
    alerts = relationship("Alert", back_populates="camera", cascade="all, delete-orphan")


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    camera_id = Column(Integer, ForeignKey("cameras.id"), nullable=False)
    event_type = Column(String(50), nullable=False)  # INTRUSION, MOTION, etc.
    confidence = Column(Float, nullable=True)
    detail = Column(Text, nullable=True)
    image_path = Column(String(500), nullable=True)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    camera = relationship("Camera", back_populates="alerts")


class TelegramConfig(Base):
    __tablename__ = "telegram_configs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    bot_token = Column(String(100), nullable=False)
    chat_id = Column(String(50), nullable=False)
    is_enabled = Column(Boolean, default=True)
    notify_on_alert = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="telegram_config")

