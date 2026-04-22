from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional, List


# ============ Auth Schemas ============
class UserBase(BaseModel):
    username: str
    email: EmailStr


class UserCreate(UserBase):
    password: str


class UserLogin(BaseModel):
    username: str
    password: str


class User(UserBase):
    id: int
    is_active: bool
    is_admin: bool
    created_at: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None


# ============ Camera Schemas ============
class CameraBase(BaseModel):
    name: str
    rtsp_url: str
    location: Optional[str] = None


class CameraCreate(CameraBase):
    confidence_threshold: Optional[float] = 0.55
    confirm_frames: Optional[int] = 5
    cooldown_seconds: Optional[int] = 20


class CameraUpdate(BaseModel):
    name: Optional[str] = None
    rtsp_url: Optional[str] = None
    location: Optional[str] = None
    is_active: Optional[bool] = None
    confidence_threshold: Optional[float] = None
    confirm_frames: Optional[int] = None
    cooldown_seconds: Optional[int] = None


class Camera(CameraBase):
    id: int
    is_active: bool
    is_running: bool
    confidence_threshold: float
    confirm_frames: int
    cooldown_seconds: int
    created_at: datetime
    owner_id: int

    class Config:
        from_attributes = True


# ============ Alert Schemas ============
class AlertBase(BaseModel):
    event_type: str
    confidence: Optional[float] = None
    detail: Optional[str] = None
    image_path: Optional[str] = None


class AlertCreate(AlertBase):
    camera_id: int


class Alert(AlertBase):
    id: int
    camera_id: int
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True


class AlertWithCamera(Alert):
    camera_name: Optional[str] = None


# ============ Dashboard Stats ============
class DashboardStats(BaseModel):
    total_cameras: int
    active_cameras: int
    running_cameras: int
    total_alerts: int
    unread_alerts: int
    alerts_today: int


# ============ Telegram Schemas ============
class TelegramConfigBase(BaseModel):
    bot_token: str
    chat_id: str
    is_enabled: bool = True
    notify_on_alert: bool = True


class TelegramConfigCreate(TelegramConfigBase):
    pass


class TelegramConfigUpdate(BaseModel):
    bot_token: Optional[str] = None
    chat_id: Optional[str] = None
    is_enabled: Optional[bool] = None
    notify_on_alert: Optional[bool] = None


class TelegramConfig(TelegramConfigBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TelegramConfigPublic(BaseModel):
    """Public view without exposing full token"""
    id: int
    chat_id: str
    is_enabled: bool
    notify_on_alert: bool
    bot_token_masked: str  # Only show last 4 chars

    class Config:
        from_attributes = True


class TelegramTestResult(BaseModel):
    success: bool
    message: str

