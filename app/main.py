"""
Surveillance System - FastAPI Application
Real-time person detection from RTSP streams with alerting and dashboard.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from pathlib import Path

from app.database import init_db, get_db, SessionLocal
from app.models import User, Alert, Camera, TelegramConfig
from app.auth import get_current_user, get_current_user_optional
from app.routers import auth, cameras, alerts, telegram
from app.services.detector import detection_manager
from app.services.telegram_bot import telegram_manager
from app.config import EVIDENCES_DIR


def create_alert_callback():
    """Create callback function for detection alerts that saves to database and sends Telegram notification."""
    def save_alert(camera_id: int, event_type: str, confidence: float, detail: str, image_path: str):
        db = SessionLocal()
        try:
            # Save alert to database
            alert = Alert(
                camera_id=camera_id,
                event_type=event_type,
                confidence=confidence,
                detail=detail,
                image_path=image_path
            )
            db.add(alert)
            db.commit()
            
            # Get camera info for Telegram notification
            camera = db.query(Camera).filter(Camera.id == camera_id).first()
            camera_name = camera.name if camera else f"Camera {camera_id}"
            
            # Check if user has Telegram notifications enabled
            if camera and camera.owner_id:
                tg_config = db.query(TelegramConfig).filter(
                    TelegramConfig.user_id == camera.owner_id,
                    TelegramConfig.is_enabled == True,
                    TelegramConfig.notify_on_alert == True
                ).first()
                
                if tg_config:
                    # Send Telegram notification
                    telegram_manager.send_alert(
                        camera_name=camera_name,
                        event_type=event_type,
                        confidence=confidence,
                        image_path=image_path,
                        detail=detail
                    )
            
        except Exception as e:
            print(f"Error saving alert: {e}")
            db.rollback()
        finally:
            db.close()
    return save_alert


def get_cameras_status_for_telegram():
    """Get cameras status for Telegram bot commands."""
    db = SessionLocal()
    try:
        cameras_list = db.query(Camera).filter(Camera.is_active == True).all()
        result = []
        for cam in cameras_list:
            status = detection_manager.get_camera_status(cam.id)
            result.append({
                "id": cam.id,
                "name": cam.name,
                "location": cam.location,
                "is_running": detection_manager.is_running(cam.id),
                "fps": status.get("fps", 0) if status else 0
            })
        return result
    finally:
        db.close()


def init_telegram_from_db():
    """Initialize Telegram bot from database configuration."""
    db = SessionLocal()
    try:
        # Get first active Telegram config (for simplicity)
        config = db.query(TelegramConfig).filter(
            TelegramConfig.is_enabled == True
        ).first()
        
        if config:
            telegram_manager.configure(
                token=config.bot_token,
                chat_id=config.chat_id,
                enabled=True
            )
            print("✅ Telegram bot configured")
        else:
            print("ℹ️ No Telegram configuration found")
    except Exception as e:
        print(f"⚠️ Error initializing Telegram: {e}")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown events."""
    # Startup
    print("🚀 Starting Surveillance System...")
    init_db()
    EVIDENCES_DIR.mkdir(parents=True, exist_ok=True)
    
    # Set up detection alert callback
    detection_manager.set_alert_callback(create_alert_callback())
    
    # Set up Telegram cameras status callback
    telegram_manager.set_cameras_status_callback(get_cameras_status_for_telegram)
    
    # Initialize Telegram from saved config
    init_telegram_from_db()
    
    print("✅ Database initialized")
    print("✅ Detection manager ready")
    print("📹 Surveillance System is running!")
    
    yield
    
    # Shutdown
    print("🛑 Shutting down...")
    detection_manager.stop_all()
    telegram_manager.stop()
    print("✅ All cameras stopped")
    print("✅ Telegram bot stopped")


# Create FastAPI app
app = FastAPI(
    title="Surveillance System",
    description="Real-time person detection from RTSP streams",
    version="1.0.0",
    lifespan=lifespan
)

# Mount static files
static_path = Path(__file__).parent / "static"
templates_path = Path(__file__).parent / "templates"

app.mount("/static", StaticFiles(directory=static_path), name="static")
templates = Jinja2Templates(directory=templates_path)

# Include routers
app.include_router(auth.router)
app.include_router(cameras.router)
app.include_router(alerts.router)
app.include_router(telegram.router)


# ============ Page Routes ============

@app.get("/")
async def root(request: Request, user: User = Depends(get_current_user_optional)):
    """Root - redirect to dashboard or login."""
    if user:
        return RedirectResponse(url="/dashboard", status_code=302)
    return RedirectResponse(url="/login", status_code=302)


@app.get("/login")
async def login_page(request: Request, user: User = Depends(get_current_user_optional)):
    """Login page."""
    if user:
        return RedirectResponse(url="/dashboard", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/register")
async def register_page(request: Request, user: User = Depends(get_current_user_optional)):
    """Register page."""
    if user:
        return RedirectResponse(url="/dashboard", status_code=302)
    return templates.TemplateResponse("register.html", {"request": request})


@app.get("/dashboard")
async def dashboard_page(request: Request, user: User = Depends(get_current_user)):
    """Dashboard page - requires authentication."""
    return templates.TemplateResponse("dashboard.html", {"request": request, "user": user})


@app.get("/cameras")
async def cameras_page(request: Request, user: User = Depends(get_current_user)):
    """Cameras management page - requires authentication."""
    return templates.TemplateResponse("cameras.html", {"request": request, "user": user})


@app.get("/alerts")
async def alerts_page(request: Request, user: User = Depends(get_current_user)):
    """Alerts page - requires authentication."""
    return templates.TemplateResponse("alerts.html", {"request": request, "user": user})


@app.get("/settings")
async def settings_page(request: Request, user: User = Depends(get_current_user)):
    """Settings page - requires authentication."""
    return templates.TemplateResponse("settings.html", {"request": request, "user": user})


# ============ Health Check ============

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "detection_service": "active"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )

