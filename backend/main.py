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
from transformers import BlipForConditionalGeneration, BlipProcessor

# Import configuration from config.py
from config import settings
# Import enhanced detection modules
from enhanced_detection import (
    BehaviorAnalyzer, 
    EyeGazeTracker, 
    ObjectDetectionAnalyzer,
    get_alert_severity
)

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
    captioning_processor = BlipProcessor.from_pretrained(settings.LOCAL_CAPTION_MODEL)
    captioning_model = BlipForConditionalGeneration.from_pretrained(settings.LOCAL_CAPTION_MODEL).to(device)
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
    ping_timeout=30,  # Allow 30 seconds for ping-pong, up from default 5s
    ping_interval=10, # Send a ping every 10 seconds, down from default 25s
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
        inputs = captioning_processor(images=image, return_tensors="pt").to(device)
        pixel_values = inputs.pixel_values

        generated_ids = captioning_model.generate(pixel_values=pixel_values, max_length=50)
        caption = captioning_processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
        logger.info(f"[{sid}] Generated caption: '{caption}'")
        return f"Analysis: {caption.strip()}"
    except Exception as e:
        logger.error(f"[{sid}] Error during local image analysis: {e}")
        return "Local analysis failed."

def run_yolo_detection(frame, sid: str):
    if yolo_model is None: return [], []
    try:
        results = yolo_model(frame)
        
        # Use enhanced detection with confidence filtering
        detections = ObjectDetectionAnalyzer.filter_detections(
            results, 
            confidence_threshold=settings.YOLO_CONFIDENCE_THRESHOLD
        )
        
        detected_objects = [d['name'] for d in detections]
        
        if detected_objects:
            logger.info(f"[{sid}] YOLO detected: {', '.join(detected_objects)}")
            for d in detections:
                logger.info(f"[{sid}]   - {d['name']}: {d['confidence']:.2f} confidence")
        
        return detected_objects, detections
    except Exception as e:
        logger.error(f"[{sid}] Error during YOLO detection: {e}")
        return [], []

# --- Socket.IO Event Handlers ---
@sio.event
async def connect(sid, environ, auth):
    try:
        # Authenticate the client
        if not auth or auth.get('token') != settings.SECRET_KEY:
            logger.warning(f"Authentication failed for {sid}. Connection rejected.")
            return False  # Reject the connection

        logger.info(f"Interviewer client connected and authenticated: {sid}")
        user_states[sid] = {
            'start_time': time.time(),
            'last_analysis_call': 0,
            'last_yolo_call': 0,
            'gaze_off_screen_start': 0,
            'face_not_detected_start': 0,
            'frame_count': 0,
            'error_count': 0,
            'behavior_analyzer': BehaviorAnalyzer(
                history_size=settings.ALERT_HISTORY_SIZE,
                time_window=settings.BEHAVIOR_ANALYSIS_WINDOW
            ) if settings.ENABLE_BEHAVIOR_ANALYSIS else None,
            'last_suspicion_score': 0,
            'last_multiple_faces_alert_time': 0,
            'last_360_scan_request_time': 0,
            'has_sent_first_360_scan': False,
        }
        await sio.emit('proctoring_alert', {
            'alert': '🟢 System Connected',
            'description': 'AI proctor is ready with enhanced detection.',
            'models_loaded': {
                'captioning': captioning_model is not None,
                'yolo': yolo_model is not None,
                'behavior_analysis': settings.ENABLE_BEHAVIOR_ANALYSIS,
                'eye_tracking': settings.ENABLE_EYE_TRACKING
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

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)


        # Log processing stats periodically
        if state['frame_count'] % 100 == 0:
            logger.info(f"[{sid}] Processed {state['frame_count']} frames, {state['error_count']} errors")
        img_h, img_w, _ = frame.shape
        suspicion_trigger = None
        event_type = None
        results = face_mesh.process(frame_rgb)

        # Check for multiple faces if enabled
        if settings.ENABLE_MULTIPLE_FACE_DETECTION and results.multi_face_landmarks and len(results.multi_face_landmarks) > 1:
            if current_time - state.get('last_multiple_faces_alert_time', 0) > settings.MULTIPLE_FACES_COOLDOWN:
                state['last_multiple_faces_alert_time'] = current_time
                num_faces = len(results.multi_face_landmarks)
                await sio.emit('proctoring_alert', {
                    'alert': '🔴 ALERT: Multiple People Detected',
                    'description': f'Detected {num_faces} people in the frame. Only the candidate should be present.',
                    'suspicion_score': 85
                }, to=sid)
                logger.warning(f'[{sid}] Multiple faces detected: {num_faces}')
                if state.get('behavior_analyzer'):
                    state['behavior_analyzer'].add_event('multiple_faces', 'urgent', current_time)
                return # Stop processing this frame as it's a critical violation

        if results.multi_face_landmarks:
            state['face_not_detected_start'] = 0
            face_landmarks = results.multi_face_landmarks[0].landmark
            
            # Enhanced eye gaze tracking
            if settings.ENABLE_EYE_TRACKING:
                eye_gaze = EyeGazeTracker.analyze_eye_gaze(face_landmarks, img_w, img_h)
                if eye_gaze.get('eyes_closed'):
                    logger.info(f"[{sid}] Eyes closed detected")
                if eye_gaze.get('looking_away'):
                    logger.info(f"[{sid}] Eye gaze indicates looking away")
            
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
                    event_type = 'looking_left' if yaw < 0 else 'looking_right'
            elif pitch * img_h > settings.HEAD_PITCH_THRESHOLD:
                if state['gaze_off_screen_start'] == 0: state['gaze_off_screen_start'] = current_time
                elif current_time - state['gaze_off_screen_start'] > settings.GAZE_ALERT_DELAY:
                    suspicion_trigger = "Candidate looking down"
                    event_type = 'looking_down'
            else:
                state['gaze_off_screen_start'] = 0
        else:
            if state['face_not_detected_start'] == 0: state['face_not_detected_start'] = current_time
            elif current_time - state['face_not_detected_start'] > settings.FACE_MISSING_ALERT_DELAY:
                suspicion_trigger = "Candidate's face is not visible"
                event_type = 'face_missing'

        # Always run YOLO detection periodically, regardless of suspicion trigger
        if current_time - state['last_yolo_call'] > settings.YOLO_COOLDOWN:
            state['last_yolo_call'] = current_time
            alert_map = {
                "Candidate looking left": ("🟠 WARNING: Off-Screen Gaze", "Candidate is looking to the left."),
                "Candidate looking right": ("🟠 WARNING: Off-Screen Gaze", "Candidate is looking to the right."),
                "Candidate looking down": ("🟠 WARNING: Looking Down", "Detected downward glances."),
                "Candidate's face is not visible": ("🟡 ATTENTION: Face Not Visible", "Candidate is not visible in the camera feed.")
            }
            alert_title, alert_desc = alert_map.get(suspicion_trigger, (None, None))
            
            # Enhanced YOLO detection with confidence filtering
            detected_objects, detections = run_yolo_detection(frame_rgb, sid)
            high_risk_objects = {'cell phone', 'book', 'person', 'tv', 'remote'}
            detected_risk_objects = set(detected_objects) & high_risk_objects

            # Record event in behavior analyzer
            if state['behavior_analyzer'] and event_type:
                severity = get_alert_severity(event_type, len(detected_risk_objects) > 0)
                state['behavior_analyzer'].add_event(event_type, severity, current_time)

            # Count persons detected by YOLO, but only if MediaPipe didn't already detect multiple faces
            person_count = detected_objects.count('person')
            if person_count > 1 and settings.ENABLE_MULTIPLE_FACE_DETECTION and not (results.multi_face_landmarks and len(results.multi_face_landmarks) > 1):
                if current_time - state.get('last_multiple_persons_alert_time', 0) > settings.MULTIPLE_FACES_COOLDOWN:
                    state['last_multiple_persons_alert_time'] = current_time
                    await sio.emit('proctoring_alert', {
                        'alert': '🔴 ALERT: Multiple People Detected',
                        'description': f'Detected {person_count} people in the frame. Only the candidate should be present.',
                        'suspicion_score': 85
                    }, to=sid)
                    logger.warning(f'[{sid}] Multiple persons detected via YOLO: {person_count}')
                    if state.get('behavior_analyzer'):
                        state['behavior_analyzer'].add_event('multiple_persons', 'urgent', current_time)

            # Analyze object context
            object_context = ObjectDetectionAnalyzer.analyze_object_context(detections) if detections else None

            if detected_risk_objects:
                if current_time - state['last_analysis_call'] > settings.LOCAL_ANALYSIS_COOLDOWN:
                    state['last_analysis_call'] = current_time
                    detected_str = ", ".join(detected_risk_objects)
                    analysis = get_local_image_analysis(frame_rgb, sid, f"{suspicion_trigger} with {detected_str} detected.")
                    
                    alert = {
                        "alert": f"🔴 URGENT: {detected_str.title()} Detected",
                        "description": analysis
                    }
                    
                    # Add object confidence info
                    if object_context and object_context.get('detected_risks'):
                        risk_details = ", ".join([
                            f"{r['object']} ({r['confidence']:.0%})"
                            for r in object_context['detected_risks']
                        ])
                        alert['description'] += f" | Confidence: {risk_details}"
                    
                    await sio.emit('proctoring_alert', alert, to=sid)
            elif alert_title:
                # Only send gaze/face alerts if no high-risk object was found
                alert = {"alert": alert_title, "description": alert_desc}
                await sio.emit('proctoring_alert', alert, to=sid)
            
            # Calculate and send suspicion score if behavior analysis enabled
            if state['behavior_analyzer'] and settings.ENABLE_BEHAVIOR_ANALYSIS:
                suspicion_score, reasons = state['behavior_analyzer'].calculate_suspicion_score()
                
                # Send high suspicion score alert
                if suspicion_score >= settings.SUSPICION_SCORE_THRESHOLD and suspicion_score > state['last_suspicion_score']:
                    state['last_suspicion_score'] = suspicion_score
                    pattern_summary = state['behavior_analyzer'].get_pattern_summary()
                    
                    await sio.emit('proctoring_alert', {
                        'alert': f'⚠️ HIGH SUSPICION SCORE: {suspicion_score}/100',
                        'description': f"Behavioral patterns detected: {'; '.join(reasons)}",
                        'suspicion_score': suspicion_score,
                        'pattern_summary': pattern_summary
                    }, to=sid)
                    logger.warning(f"[{sid}] High suspicion score: {suspicion_score} - {reasons}")

            # Request a one-time 360-degree environmental scan after 5 minutes
            if not state['has_sent_first_360_scan']:
                # Check if 5 minutes (300 seconds) have passed since monitoring started
                if current_time - state.get('start_time', current_time) > 300:
                    state['has_sent_first_360_scan'] = True # Ensure this only runs once
                    await sio.emit('proctoring_alert', {
                        'alert': '🔵 REQUEST: 360° Environmental Scan',
                        'description': 'Please show your surroundings by doing a 360-degree scan with your camera.',
                        'type': 'request_360_scan'
                    }, to=sid)
                    logger.info(f'[{sid}] Requested one-time 5-minute 360-degree environmental scan.')

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

@sio.on('manual_request')
async def handle_manual_request(sid, data):
    logger.info(f"[{sid}] Received manual request: {data}")
    request_type = data.get('type')
    state = user_states.get(sid)

    if not state:
        return

    if request_type == 'request_360_scan':
        state['last_360_scan_request_time'] = time.time()
        await sio.emit('proctoring_alert', {
            'alert': '🔵 REQUEST: 360° Environmental Scan',
            'description': 'Proctor has manually requested a 360-degree scan of your surroundings.',
            'type': 'request_360_scan'
        }, to=sid)
        logger.info(f'[{sid}] Manually triggered 360-degree environmental scan.')



@sio.on('client_response')
async def handle_client_response(sid, data):
    """Handles client responses, like acknowledging a 360 scan."""
    logger.info(f"[{sid}] Received client response: {data}")

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
    logger.info(f"Backend API & WebSocket running at: http://{settings.BACKEND_HOST}:{settings.BACKEND_PORT}")
    logger.info("Run the browser extension in a meeting to begin.")
    logger.info("-----------------------------")
    
    uvicorn.run(
        app,
        host=settings.BACKEND_HOST,
        port=settings.BACKEND_PORT,
        log_level="info"
    )
