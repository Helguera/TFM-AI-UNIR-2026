from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List
import time

from app.database import get_db
from app.models import Camera as CameraModel, User
from app.schemas import Camera, CameraCreate, CameraUpdate
from app.auth import get_current_user
from app.services.detector import detection_manager

router = APIRouter(prefix="/api/cameras", tags=["cameras"])


@router.get("/", response_model=List[Camera])
def get_cameras(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all cameras for current user."""
    cameras = db.query(CameraModel).filter(CameraModel.owner_id == current_user.id).all()
    # Update is_running status based on detection manager
    for cam in cameras:
        cam.is_running = detection_manager.is_running(cam.id)
    return cameras


@router.get("/{camera_id}", response_model=Camera)
def get_camera(
    camera_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific camera."""
    camera = db.query(CameraModel).filter(
        CameraModel.id == camera_id,
        CameraModel.owner_id == current_user.id
    ).first()
    
    if not camera:
        raise HTTPException(status_code=404, detail="Cámara no encontrada")
    
    camera.is_running = detection_manager.is_running(camera.id)
    return camera


@router.post("/", response_model=Camera)
def create_camera(
    camera_data: CameraCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new camera."""
    camera = CameraModel(
        name=camera_data.name,
        rtsp_url=camera_data.rtsp_url,
        location=camera_data.location,
        confidence_threshold=camera_data.confidence_threshold,
        confirm_frames=camera_data.confirm_frames,
        cooldown_seconds=camera_data.cooldown_seconds,
        owner_id=current_user.id
    )
    db.add(camera)
    db.commit()
    db.refresh(camera)
    return camera


@router.put("/{camera_id}", response_model=Camera)
def update_camera(
    camera_id: int,
    camera_data: CameraUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a camera."""
    camera = db.query(CameraModel).filter(
        CameraModel.id == camera_id,
        CameraModel.owner_id == current_user.id
    ).first()
    
    if not camera:
        raise HTTPException(status_code=404, detail="Cámara no encontrada")
    
    # Stop camera if running and URL changed
    was_running = detection_manager.is_running(camera_id)
    if was_running and camera_data.rtsp_url and camera_data.rtsp_url != camera.rtsp_url:
        detection_manager.stop_camera(camera_id)
    
    # Update fields
    update_data = camera_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(camera, field, value)
    
    db.commit()
    db.refresh(camera)
    
    # Restart if was running
    if was_running and camera.is_active:
        detection_manager.start_camera(
            camera_id=camera.id,
            camera_name=camera.name,
            rtsp_url=camera.rtsp_url,
            conf_thresh=camera.confidence_threshold,
            confirm_frames=camera.confirm_frames,
            cooldown_s=camera.cooldown_seconds
        )
    
    camera.is_running = detection_manager.is_running(camera.id)
    return camera


@router.delete("/{camera_id}")
def delete_camera(
    camera_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a camera."""
    camera = db.query(CameraModel).filter(
        CameraModel.id == camera_id,
        CameraModel.owner_id == current_user.id
    ).first()
    
    if not camera:
        raise HTTPException(status_code=404, detail="Cámara no encontrada")
    
    # Stop if running
    detection_manager.stop_camera(camera_id)
    
    db.delete(camera)
    db.commit()
    return {"message": "Cámara eliminada correctamente"}


@router.post("/{camera_id}/start")
def start_camera(
    camera_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Start detection on a camera."""
    camera = db.query(CameraModel).filter(
        CameraModel.id == camera_id,
        CameraModel.owner_id == current_user.id
    ).first()
    
    if not camera:
        raise HTTPException(status_code=404, detail="Cámara no encontrada")
    
    if not camera.is_active:
        raise HTTPException(status_code=400, detail="La cámara está desactivada")
    
    success = detection_manager.start_camera(
        camera_id=camera.id,
        camera_name=camera.name,
        rtsp_url=camera.rtsp_url,
        conf_thresh=camera.confidence_threshold,
        confirm_frames=camera.confirm_frames,
        cooldown_s=camera.cooldown_seconds
    )
    
    if not success:
        raise HTTPException(status_code=500, detail="Error al iniciar la cámara")
    
    return {"message": "Cámara iniciada", "is_running": True}


@router.post("/{camera_id}/stop")
def stop_camera(
    camera_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Stop detection on a camera."""
    camera = db.query(CameraModel).filter(
        CameraModel.id == camera_id,
        CameraModel.owner_id == current_user.id
    ).first()
    
    if not camera:
        raise HTTPException(status_code=404, detail="Cámara no encontrada")
    
    detection_manager.stop_camera(camera_id)
    return {"message": "Cámara detenida", "is_running": False}


@router.get("/{camera_id}/status")
def get_camera_status(
    camera_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get detection status for a camera."""
    camera = db.query(CameraModel).filter(
        CameraModel.id == camera_id,
        CameraModel.owner_id == current_user.id
    ).first()
    
    if not camera:
        raise HTTPException(status_code=404, detail="Cámara no encontrada")
    
    status = detection_manager.get_camera_status(camera_id)
    if status:
        return status
    return {
        "camera_id": camera_id,
        "camera_name": camera.name,
        "status": "STOPPED",
        "fps": 0,
        "backend": "-",
        "error": None
    }


@router.get("/{camera_id}/stream")
def stream_camera(
    camera_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Stream camera video as MJPEG."""
    camera = db.query(CameraModel).filter(
        CameraModel.id == camera_id,
        CameraModel.owner_id == current_user.id
    ).first()
    
    if not camera:
        raise HTTPException(status_code=404, detail="Cámara no encontrada")
    
    if not detection_manager.is_running(camera_id):
        raise HTTPException(status_code=400, detail="La cámara no está activa")
    
    def generate():
        while True:
            frame = detection_manager.get_frame(camera_id)
            if frame:
                yield (
                    b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n'
                )
            time.sleep(0.033)  # ~30 FPS max
    
    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

