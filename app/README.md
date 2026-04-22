# SurveillanceHQ - Video Surveillance System

Real-time video surveillance system with automatic person detection via RTSP streams, built with FastAPI.

## Features

- **Authentication**: Login with username/password and JWT tokens
- **RTSP camera management**: Add, edit, delete and control cameras
- **Person detection**: MobileNet SSD for real-time detection
- **Alert system**: Automatic intrusion logging with image captures
- **Interactive dashboard**: Live view and statistics
- **MJPEG streaming**: Camera feed in the browser

## Requirements

- Python 3.9+
- OpenCV with FFMPEG/GStreamer support
- MobileNet SSD model (included in `models/`)

## Installation

1. **Create virtual environment**:
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows
```

2. **Install dependencies**:
```bash
pip install -r app/requirements.txt
```

3. **Run the application**:
```bash
# From the project root directory
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

4. **Access the dashboard**:
   - Open http://localhost:8000
   - Register a new user
   - Log in

## Project Structure

```
TFM-AI-UNIR-2026/
├── app/
│   ├── main.py              # Main FastAPI application
│   ├── config.py            # Configuration
│   ├── database.py          # SQLAlchemy setup
│   ├── models.py            # Database models
│   ├── schemas.py           # Pydantic schemas
│   ├── auth.py              # JWT authentication
│   ├── routers/
│   │   ├── auth.py          # Authentication endpoints
│   │   ├── cameras.py       # Camera endpoints
│   │   └── alerts.py        # Alert endpoints
│   ├── services/
│   │   └── detector.py      # Detection service
│   ├── static/
│   │   └── css/style.css    # Styles
│   └── templates/
│       ├── base.html        # Base template
│       ├── login.html       # Login page
│       ├── register.html    # Registration page
│       ├── dashboard.html   # Main dashboard
│       ├── cameras.html     # Camera management
│       └── alerts.html      # Alert log
├── models/
│   ├── MobileNetSSD_deploy.prototxt
│   └── MobileNetSSD_deploy.caffemodel
└── evidences/               # Alert captures (auto-generated)
```

## API Endpoints

### Authentication
- `POST /api/auth/register` - Register user
- `POST /api/auth/login` - Log in
- `POST /api/auth/logout` - Log out
- `GET /api/auth/me` - Current user

### Cameras
- `GET /api/cameras/` - List cameras
- `POST /api/cameras/` - Add camera
- `GET /api/cameras/{id}` - Get camera
- `PUT /api/cameras/{id}` - Update camera
- `DELETE /api/cameras/{id}` - Delete camera
- `POST /api/cameras/{id}/start` - Start detection
- `POST /api/cameras/{id}/stop` - Stop detection
- `GET /api/cameras/{id}/stream` - MJPEG stream
- `GET /api/cameras/{id}/status` - Detection status

### Alerts
- `GET /api/alerts/` - List alerts
- `GET /api/alerts/stats` - Statistics
- `GET /api/alerts/{id}` - Get alert
- `PUT /api/alerts/{id}/read` - Mark as read
- `PUT /api/alerts/mark-all-read` - Mark all as read
- `DELETE /api/alerts/{id}` - Delete alert
- `GET /api/alerts/{id}/image` - Alert image

## Camera Configuration

Each camera can be configured with the following parameters:

| Parameter | Description | Default |
|-----------|-------------|---------|
| `confidence_threshold` | Minimum confidence for detection | 0.55 |
| `confirm_frames` | Consecutive frames to confirm detection | 5 |
| `cooldown_seconds` | Time between alerts | 20s |

### RTSP URL examples

```
# Generic IP camera
rtsp://user:password@192.168.1.100:554/stream1

# Hikvision camera
rtsp://admin:password@192.168.1.100:554/Streaming/Channels/101

# Dahua camera
rtsp://admin:password@192.168.1.100:554/cam/realmonitor?channel=1&subtype=0

# Local test stream (with MediaMTX)
rtsp://127.0.0.1:8554/webcam
```

## Environment Variables

```bash
# Optional - change in production
SECRET_KEY=your-secret-key
```
