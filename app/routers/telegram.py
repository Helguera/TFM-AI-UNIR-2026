from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import asyncio

from app.database import get_db
from app.models import TelegramConfig as TelegramConfigModel, User
from app.schemas import (
    TelegramConfigCreate, TelegramConfigUpdate, 
    TelegramConfigPublic, TelegramTestResult
)
from app.auth import get_current_user
from app.services.telegram_bot import telegram_manager, test_connection

router = APIRouter(prefix="/api/telegram", tags=["telegram"])


def mask_token(token: str) -> str:
    """Mask bot token showing only last 4 characters."""
    if len(token) <= 4:
        return "****"
    return "*" * (len(token) - 4) + token[-4:]


@router.get("/config", response_model=TelegramConfigPublic)
def get_telegram_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get current Telegram configuration."""
    config = db.query(TelegramConfigModel).filter(
        TelegramConfigModel.user_id == current_user.id
    ).first()
    
    if not config:
        raise HTTPException(status_code=404, detail="Telegram no configurado")
    
    return TelegramConfigPublic(
        id=config.id,
        chat_id=config.chat_id,
        is_enabled=config.is_enabled,
        notify_on_alert=config.notify_on_alert,
        bot_token_masked=mask_token(config.bot_token)
    )


@router.post("/config", response_model=TelegramConfigPublic)
def create_telegram_config(
    config_data: TelegramConfigCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create or update Telegram configuration."""
    # Check if config already exists
    existing = db.query(TelegramConfigModel).filter(
        TelegramConfigModel.user_id == current_user.id
    ).first()
    
    if existing:
        # Update existing
        existing.bot_token = config_data.bot_token
        existing.chat_id = config_data.chat_id
        existing.is_enabled = config_data.is_enabled
        existing.notify_on_alert = config_data.notify_on_alert
        db.commit()
        db.refresh(existing)
        config = existing
    else:
        # Create new
        config = TelegramConfigModel(
            user_id=current_user.id,
            bot_token=config_data.bot_token,
            chat_id=config_data.chat_id,
            is_enabled=config_data.is_enabled,
            notify_on_alert=config_data.notify_on_alert
        )
        db.add(config)
        db.commit()
        db.refresh(config)
    
    # Configure the telegram manager
    if config.is_enabled:
        telegram_manager.configure(
            token=config.bot_token,
            chat_id=config.chat_id,
            enabled=True
        )
    
    return TelegramConfigPublic(
        id=config.id,
        chat_id=config.chat_id,
        is_enabled=config.is_enabled,
        notify_on_alert=config.notify_on_alert,
        bot_token_masked=mask_token(config.bot_token)
    )


@router.put("/config", response_model=TelegramConfigPublic)
def update_telegram_config(
    config_data: TelegramConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update Telegram configuration."""
    config = db.query(TelegramConfigModel).filter(
        TelegramConfigModel.user_id == current_user.id
    ).first()
    
    if not config:
        raise HTTPException(status_code=404, detail="Telegram no configurado")
    
    # Update fields
    update_data = config_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(config, field, value)
    
    db.commit()
    db.refresh(config)
    
    # Reconfigure telegram manager
    if config.is_enabled:
        telegram_manager.configure(
            token=config.bot_token,
            chat_id=config.chat_id,
            enabled=True
        )
    else:
        telegram_manager.stop()
    
    return TelegramConfigPublic(
        id=config.id,
        chat_id=config.chat_id,
        is_enabled=config.is_enabled,
        notify_on_alert=config.notify_on_alert,
        bot_token_masked=mask_token(config.bot_token)
    )


@router.delete("/config")
def delete_telegram_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete Telegram configuration."""
    config = db.query(TelegramConfigModel).filter(
        TelegramConfigModel.user_id == current_user.id
    ).first()
    
    if not config:
        raise HTTPException(status_code=404, detail="Telegram no configurado")
    
    # Stop the bot
    telegram_manager.stop()
    
    db.delete(config)
    db.commit()
    
    return {"message": "Configuración de Telegram eliminada"}


@router.post("/test", response_model=TelegramTestResult)
async def test_telegram_connection(
    config_data: TelegramConfigCreate,
    current_user: User = Depends(get_current_user)
):
    """Test Telegram connection with provided credentials."""
    result = await test_connection(config_data.bot_token, config_data.chat_id)
    return TelegramTestResult(**result)


@router.get("/status")
def get_telegram_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get Telegram bot status."""
    config = db.query(TelegramConfigModel).filter(
        TelegramConfigModel.user_id == current_user.id
    ).first()
    
    return {
        "configured": config is not None,
        "enabled": config.is_enabled if config else False,
        "notify_on_alert": config.notify_on_alert if config else False,
        "bot_running": telegram_manager.is_configured() and telegram_manager.is_enabled()
    }

