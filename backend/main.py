import asyncio
import base64
import cv2
import mediapipe as mp
import numpy as np
import torch
import uvicorn
import socketio
import logging
import time
from fastapi import FastAPI
from PIL import Image
from transformers import GitForCausalLM, GitProcessor

# Import configuration from config.py
from config import settings

# --- Logging Setup ---
# Provides continuous feedback in the terminal where the script is running
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger(__name__)

# --- AI Model Initialization ---
logger.info("--- Initializing AI Proctor Backend Server ---")
device = "cuda" if torch.cuda.is_available() else "cpu"
logger.info(f"Using device: {device}")

# --- Image Captioning Model (Microsoft GIT) ---
captioning_processor = None
captioning_model = None
try:
    logger.info(f"Loading image captioning model: '{settings.LOCAL_CAPTION_MODEL}'")
    captioning_processor = GitProcessor.from_pretrained(settings.LOCAL_CAPTION_MODEL, use_fast=True)
    captioning_model = GitForCausalLM.from_pretrained(settings.LOCAL_CAPTION_MODEL).to(device)
    logger.info("Image captioning model loaded successfully.")
except Exception as e:
    logger.error(f"Could not load captioning model: {e}. Contextual analysis will be disabled.")

# --- MediaPipe Face Mesh ---
try:
    mp_face_mesh = mp.solutions.face_mesh
    face_mesh = mp_face_mesh.FaceMesh(
        max_num_faces=settings.FACE_MESH_MAX_NUM_FACES,
        refine_landmarks=settings.FACE_MESH_REFINE_LANDMARKS,
        min_detection_confidence=settings.FACE_MESH_MIN_DETECTION_CONFIDENCE,
        min_tracking_confidence=settings.FACE_MESH_MIN_TRACKING_CONFIDENCE
    )
    logger.info("MediaPipe Face Mesh model loaded.")
except Exception as e:
    logger.critical(f"Failed to load MediaPipe model: {e}")
    exit()

# --- YOLOv5 Object Detection ---
yolo_model = None
try:
    logger.info(f"Loading YOLOv5 model: '{settings.YOLO_MODEL_NAME}'.")
    yolo_model = torch.hub.load('ultralytics/yolov5', settings.YOLO_MODEL_NAME, pretrained=True)
    yolo_model.classes = settings.YOLO_CLASSES
    logger.info("YOLOv5 model loaded successfully.")
except Exception as e:
    logger.error(f"Could not load YOLOv5 model: {e}. Object detection will be disabled.")

# --- FastAPI and Socket.IO Server ---
app = FastAPI()

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint to verify server and model status."""
    return {
        "status": "healthy",
        "models": {
            "captioning": captioning_model is not None,
            "yolo": yolo_model is not None,
            "face_mesh": face_mesh is not None
        },
        "device": device,
        "active_connections": len(user_states)
    }

# Configure CORS based on settings
cors_origins = "*" if settings.ALLOW_ALL_ORIGINS else settings.CORS_ORIGINS
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins=cors_origins,
    logger=True,
    engineio_logger=False
)
socket_app = socketio.ASGIApp(sio)
app.mount("/", socket_app)
logger.info(f"FastAPI and Socket.IO server mounted. CORS: {'ALL ORIGINS (*)' if settings.ALLOW_ALL_ORIGINS else 'RESTRICTED'}")

# --- Global State Management ---
user_states = {}

# --- AI Analysis Functions ---
def get_local_image_analysis(frame_rgb, sid: str, trigger_reason: str):
    if not all([captioning_model, captioning_processor]):
        return "Contextual analysis model not loaded."
    try:
        logger.info(f"[{sid}] Getting local analysis for: {trigger_reason}")
        image = Image.fromarray(frame_rgb)
        pixel_values = captioning_processor(images=image, return_tensors="pt").pixel_values.to(device)
        generated_ids = captioning_model.generate(pixel_values=pixel_values, max_length=50)
        caption = captioning_processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
        logger.info(f"[{sid}] Generated caption: '{caption}'")
        return f"Analysis: {caption.strip()}"
    except Exception as e:
        logger.error(f"[{sid}] Error during local image analysis: {e}")
        return "Local analysis failed."

def run_yolo_detection(frame, sid: str):
    if yolo_model is None: return []
    try:
        results = yolo_model(frame)
        labels = results.pandas().xyxy[0]
        detected_objects = labels['name'].unique().tolist()
        if detected_objects:
            logger.info(f"[{sid}] YOLO detected: {', '.join(detected_objects)}")
        return detected_objects
    except Exception as e:
        logger.error(f"[{sid}] Error during YOLO detection: {e}")
        return []

# --- Socket.IO Event Handlers ---
@sio.event
async def connect(sid, environ):
    try:
        logger.info(f"Interviewer client connected: {sid}")
        user_states[sid] = {
            'last_analysis_call': 0,
            'last_yolo_call': 0,
            'gaze_off_screen_start': 0,
            'face_not_detected_start': 0,
            'frame_count': 0,
            'error_count': 0
        }
        await sio.emit('proctoring_alert', {
            'alert': '🟢 System Connected',
            'description': 'AI proctor is ready.',
            'models_loaded': {
                'captioning': captioning_model is not None,
                'yolo': yolo_model is not None
            }
        }, to=sid)
    except Exception as e:
        logger.error(f"Error during connection for {sid}: {e}", exc_info=True)

@sio.event
async def disconnect(sid):
    logger.info(f"Interviewer client disconnected: {sid}")
    if sid in user_states:
        del user_states[sid]

@sio.on('video_frame')
async def handle_video_frame(sid, data):
    if sid not in user_states:
        logger.warning(f"Received frame from unknown session: {sid}")
        return

    state = user_states[sid]
    current_time = time.time()
    state['frame_count'] += 1
    
    try:
        # Validate data format
        if not data or ',' not in data:
            logger.error(f"[{sid}] Invalid frame data format")
            state['error_count'] += 1
            return
            
        image_data = base64.b64decode(data.split(',')[1])
        nparr = np.frombuffer(image_data, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if frame is None:
            logger.warning(f"[{sid}] Failed to decode frame")
            state['error_count'] += 1
            return
            
        # Log processing stats periodically
        if state['frame_count'] % 100 == 0:
            logger.info(f"[{sid}] Processed {state['frame_count']} frames, {state['error_count']} errors")

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img_h, img_w, _ = frame.shape
        suspicion_trigger = None
        results = face_mesh.process(frame_rgb)

        if results.multi_face_landmarks:
            state['face_not_detected_start'] = 0
            face_landmarks = results.multi_face_landmarks[0].landmark
            
            nose_tip = face_landmarks[1]
            chin = face_landmarks[199]
            left_eye = face_landmarks[33]
            right_eye = face_landmarks[263]
            yaw = nose_tip.x - (left_eye.x + right_eye.x) / 2
            pitch = nose_tip.y - chin.y

            if abs(yaw) * img_w > settings.HEAD_YAW_THRESHOLD:
                if state['gaze_off_screen_start'] == 0: state['gaze_off_screen_start'] = current_time
                elif current_time - state['gaze_off_screen_start'] > settings.GAZE_ALERT_DELAY:
                    suspicion_trigger = f"Candidate looking {'left' if yaw < 0 else 'right'}"
            elif pitch * img_h > settings.HEAD_PITCH_THRESHOLD:
                if state['gaze_off_screen_start'] == 0: state['gaze_off_screen_start'] = current_time
                elif current_time - state['gaze_off_screen_start'] > settings.GAZE_ALERT_DELAY:
                    suspicion_trigger = "Candidate looking down"
            else:
                state['gaze_off_screen_start'] = 0
        else:
            if state['face_not_detected_start'] == 0: state['face_not_detected_start'] = current_time
            elif current_time - state['face_not_detected_start'] > settings.FACE_MISSING_ALERT_DELAY:
                suspicion_trigger = "Candidate's face is not visible"

        if suspicion_trigger and (current_time - state['last_yolo_call'] > settings.YOLO_COOLDOWN):
            state['last_yolo_call'] = current_time
            alert_map = {
                "Candidate looking left": ("🟠 WARNING: Off-Screen Gaze", "Candidate is looking to the left."),
                "Candidate looking right": ("🟠 WARNING: Off-Screen Gaze", "Candidate is looking to the right."),
                "Candidate looking down": ("🟠 WARNING: Looking Down", "Detected downward glances."),
                "Candidate's face is not visible": ("🟡 ATTENTION: Face Not Visible", "Candidate is not visible in the camera feed.")
            }
            alert_title, alert_desc = alert_map.get(suspicion_trigger, ("Alert", "Suspicious behavior detected."))
            
            detected_objects = run_yolo_detection(frame_rgb, sid)
            high_risk_objects = {'cell phone', 'book', 'person'}
            detected_risk_objects = set(detected_objects) & high_risk_objects

            if detected_risk_objects:
                if current_time - state['last_analysis_call'] > settings.LOCAL_ANALYSIS_COOLDOWN:
                    state['last_analysis_call'] = current_time
                    detected_str = ", ".join(detected_risk_objects)
                    analysis = get_local_image_analysis(frame_rgb, sid, f"{suspicion_trigger} with {detected_str} detected.")
                    alert = {"alert": f"🔴 URGENT: {detected_str.title()} Detected", "description": analysis}
                    await sio.emit('proctoring_alert', alert, to=sid)
            else:
                alert = {"alert": alert_title, "description": alert_desc}
                await sio.emit('proctoring_alert', alert, to=sid)

    except base64.binascii.Error as e:
        logger.error(f"[{sid}] Base64 decode error: {e}")
        state['error_count'] += 1
    except cv2.error as e:
        logger.error(f"[{sid}] OpenCV error: {e}")
        state['error_count'] += 1
    except Exception as e:
        logger.error(f"[{sid}] Unhandled error in handle_video_frame: {e}", exc_info=True)
        state['error_count'] += 1
        
        # If too many errors, notify client
        if state['error_count'] > 10 and state['error_count'] % 10 == 0:
            await sio.emit('proctoring_alert', {
                'alert': '⚠️ Processing Errors',
                'description': f'Encountered {state["error_count"]} errors processing frames. Check video quality.'
            }, to=sid)

@sio.on('client_alert')
async def client_side_alert(sid, data):
    """Handles alerts generated by the client (e.g., tab switch) and sends them back."""
    try:
        logger.info(f"[{sid}] Received client-side alert: {data.get('alert', 'Unknown')}")
        await sio.emit('proctoring_alert', data, to=sid)
    except Exception as e:
        logger.error(f"[{sid}] Error handling client alert: {e}", exc_info=True)

@sio.event
async def connect_error(sid, data):
    """Handle connection errors."""
    logger.error(f"Connection error for {sid}: {data}")

@sio.event
async def error(sid, data):
    """Handle general Socket.IO errors."""
    logger.error(f"Socket.IO error for {sid}: {data}")

# --- Main Entry Point ---
if __name__ == '__main__':
    logger.info("--- AI Proctoring System ---")
    logger.info(f"Backend API & WebSocket running at: http://{settings.HOST}:{settings.PORT}")
    logger.info("Run the browser extension in a meeting to begin.")
    logger.info("-----------------------------")
    
    uvicorn.run(
        app,
        host=settings.HOST,
        port=settings.PORT,
        log_level="info"
    )
