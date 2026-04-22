import os
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
MODELS_DIR = Path(os.getenv("MODELS_DIR", str(PROJECT_ROOT / "models")))
EVIDENCES_DIR = Path(os.getenv("EVIDENCES_DIR", str(PROJECT_ROOT / "evidences")))
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR)))

# Database
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR}/surveillance.db")

# JWT Auth
SECRET_KEY = os.getenv("SECRET_KEY", "tfm-surveillance-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

# Detection model
PROTOTXT_PATH = str(MODELS_DIR / "MobileNetSSD_deploy.prototxt")
CAFFEMODEL_PATH = str(MODELS_DIR / "MobileNetSSD_deploy.caffemodel")

# Detection settings
DEFAULT_CONFIDENCE_THRESHOLD = 0.55
DEFAULT_CONFIRM_FRAMES = 5
DEFAULT_COOLDOWN_SECONDS = 20
DEFAULT_TARGET_WIDTH = 800

