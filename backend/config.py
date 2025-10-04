"""Configuration settings for the proctoring backend."""
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    # --- Server Configuration ---
    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 5002
    # CORS Origins: Restrict to specific origins in production for security
    # Development: Use ["*"] for testing
    # Production: Use specific origins like ["http://localhost:3000", "chrome-extension://*"]
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "chrome-extension://*",
        "moz-extension://*",
        "https://meet.google.com",
        "https://zoom.us",
        "https://*.zoom.us"
    ]
    # Set to True to allow all origins (development only)
    ALLOW_ALL_ORIGINS: bool = False

    # --- AI Model Configuration ---
    # The name of the YOLOv5 model to use. 'yolov5s' is small and fast.
    YOLO_MODEL_NAME: str = 'yolov5s'
    # List of object classes YOLO should focus on.
    # 0: person, 67: cell phone, 73: book
    YOLO_CLASSES: List[int] = [0, 67, 73]
    
    # The name of the local image captioning model from Hugging Face.
    # 'microsoft/git-base-coco' is a small and efficient model.
    LOCAL_CAPTION_MODEL: str = "microsoft/git-base-coco"

    # --- MediaPipe Configuration ---
    FACE_MESH_MAX_NUM_FACES: int = 1
    FACE_MESH_REFINE_LANDMARKS: bool = True
    FACE_MESH_MIN_DETECTION_CONFIDENCE: float = 0.5
    FACE_MESH_MIN_TRACKING_CONFIDENCE: float = 0.5

    # --- Proctoring Thresholds & Cooldowns ---
    # How far (in pixels) the candidate's nose can deviate horizontally before triggering a gaze check.
    HEAD_YAW_THRESHOLD: int = 60 
    # How far down (in pixels) the candidate can look before triggering a gaze check.
    HEAD_PITCH_THRESHOLD: int = 40
    
    # How long (in seconds) the candidate's gaze must be off-screen to trigger an alert.
    GAZE_ALERT_DELAY: float = 2.0
    # How long (in seconds) the candidate's face can be missing to trigger an alert.
    FACE_MISSING_ALERT_DELAY: float = 3.0
    
    # Cooldown periods (in seconds) to prevent alert spam.
    YOLO_COOLDOWN: float = 10.0
    LOCAL_ANALYSIS_COOLDOWN: float = 15.0
    
    # --- Enhanced Detection Settings ---
    # Enable iris/eye tracking for more precise gaze detection
    ENABLE_EYE_TRACKING: bool = True
    # Minimum confidence for YOLO detections (0.0 to 1.0)
    YOLO_CONFIDENCE_THRESHOLD: float = 0.5
    # Enable behavioral pattern analysis
    ENABLE_BEHAVIOR_ANALYSIS: bool = True
    # Suspicion score threshold to trigger high-priority alert (0-100)
    SUSPICION_SCORE_THRESHOLD: int = 70
    # Track alert history for pattern detection
    ALERT_HISTORY_SIZE: int = 50
    # Time window (seconds) for behavioral pattern analysis
    BEHAVIOR_ANALYSIS_WINDOW: float = 60.0
    # Enable multiple face detection warning
    ENABLE_MULTIPLE_FACE_DETECTION: bool = True

# Initialize settings
settings = Settings()
