from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import datetime, timedelta
from pathlib import Path

from app.database import get_db
from app.models import Alert as AlertModel, Camera as CameraModel, User
from app.schemas import Alert, AlertWithCamera, DashboardStats
from app.auth import get_current_user

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("/", response_model=List[AlertWithCamera])
def get_alerts(
    camera_id: Optional[int] = Query(None),
    is_read: Optional[bool] = Query(None),
    limit: int = Query(50, le=500),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get alerts for user's cameras."""
    # Get user's camera IDs
    camera_ids = [c.id for c in db.query(CameraModel.id).filter(
        CameraModel.owner_id == current_user.id
    ).all()]
    
    query = db.query(AlertModel).filter(AlertModel.camera_id.in_(camera_ids))
    
    if camera_id is not None:
        if camera_id not in camera_ids:
            raise HTTPException(status_code=403, detail="No tienes acceso a esta cámara")
        query = query.filter(AlertModel.camera_id == camera_id)
    
    if is_read is not None:
        query = query.filter(AlertModel.is_read == is_read)
    
    alerts = query.order_by(AlertModel.created_at.desc()).offset(offset).limit(limit).all()
    
    # Get camera names
    cameras = {c.id: c.name for c in db.query(CameraModel).filter(
        CameraModel.id.in_(camera_ids)
    ).all()}
    
    result = []
    for alert in alerts:
        alert_dict = {
            "id": alert.id,
            "camera_id": alert.camera_id,
            "event_type": alert.event_type,
            "confidence": alert.confidence,
            "detail": alert.detail,
            "image_path": alert.image_path,
            "is_read": alert.is_read,
            "created_at": alert.created_at,
            "camera_name": cameras.get(alert.camera_id)
        }
        result.append(alert_dict)
    
    return result


@router.get("/stats", response_model=DashboardStats)
def get_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get dashboard statistics."""
    from app.services.detector import detection_manager
    
    # Camera stats
    cameras = db.query(CameraModel).filter(CameraModel.owner_id == current_user.id).all()
    total_cameras = len(cameras)
    active_cameras = sum(1 for c in cameras if c.is_active)
    running_cameras = sum(1 for c in cameras if detection_manager.is_running(c.id))
    
    # Alert stats
    camera_ids = [c.id for c in cameras]
    total_alerts = db.query(func.count(AlertModel.id)).filter(
        AlertModel.camera_id.in_(camera_ids)
    ).scalar() or 0
    
    unread_alerts = db.query(func.count(AlertModel.id)).filter(
        AlertModel.camera_id.in_(camera_ids),
        AlertModel.is_read == False
    ).scalar() or 0
    
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    alerts_today = db.query(func.count(AlertModel.id)).filter(
        AlertModel.camera_id.in_(camera_ids),
        AlertModel.created_at >= today_start
    ).scalar() or 0
    
    return DashboardStats(
        total_cameras=total_cameras,
        active_cameras=active_cameras,
        running_cameras=running_cameras,
        total_alerts=total_alerts,
        unread_alerts=unread_alerts,
        alerts_today=alerts_today
    )


@router.get("/{alert_id}", response_model=Alert)
def get_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific alert."""
    # Get user's camera IDs
    camera_ids = [c.id for c in db.query(CameraModel.id).filter(
        CameraModel.owner_id == current_user.id
    ).all()]
    
    alert = db.query(AlertModel).filter(
        AlertModel.id == alert_id,
        AlertModel.camera_id.in_(camera_ids)
    ).first()
    
    if not alert:
        raise HTTPException(status_code=404, detail="Alerta no encontrada")
    
    return alert


@router.put("/{alert_id}/read")
def mark_alert_read(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Mark an alert as read."""
    camera_ids = [c.id for c in db.query(CameraModel.id).filter(
        CameraModel.owner_id == current_user.id
    ).all()]
    
    alert = db.query(AlertModel).filter(
        AlertModel.id == alert_id,
        AlertModel.camera_id.in_(camera_ids)
    ).first()
    
    if not alert:
        raise HTTPException(status_code=404, detail="Alerta no encontrada")
    
    alert.is_read = True
    db.commit()
    return {"message": "Alerta marcada como leída"}


@router.put("/mark-all-read")
def mark_all_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Mark all alerts as read."""
    camera_ids = [c.id for c in db.query(CameraModel.id).filter(
        CameraModel.owner_id == current_user.id
    ).all()]
    
    db.query(AlertModel).filter(
        AlertModel.camera_id.in_(camera_ids),
        AlertModel.is_read == False
    ).update({AlertModel.is_read: True}, synchronize_session=False)
    
    db.commit()
    return {"message": "Todas las alertas marcadas como leídas"}


@router.delete("/{alert_id}")
def delete_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete an alert."""
    camera_ids = [c.id for c in db.query(CameraModel.id).filter(
        CameraModel.owner_id == current_user.id
    ).all()]
    
    alert = db.query(AlertModel).filter(
        AlertModel.id == alert_id,
        AlertModel.camera_id.in_(camera_ids)
    ).first()
    
    if not alert:
        raise HTTPException(status_code=404, detail="Alerta no encontrada")
    
    # Delete image file if exists
    if alert.image_path:
        try:
            Path(alert.image_path).unlink(missing_ok=True)
        except Exception:
            pass
    
    db.delete(alert)
    db.commit()
    return {"message": "Alerta eliminada"}


@router.get("/{alert_id}/image")
def get_alert_image(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get the image associated with an alert."""
    camera_ids = [c.id for c in db.query(CameraModel.id).filter(
        CameraModel.owner_id == current_user.id
    ).all()]
    
    alert = db.query(AlertModel).filter(
        AlertModel.id == alert_id,
        AlertModel.camera_id.in_(camera_ids)
    ).first()
    
    if not alert:
        raise HTTPException(status_code=404, detail="Alerta no encontrada")
    
    if not alert.image_path:
        raise HTTPException(status_code=404, detail="La alerta no tiene imagen")
    
    image_path = Path(alert.image_path)
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Imagen no encontrada")
    
    return FileResponse(image_path, media_type="image/jpeg")

