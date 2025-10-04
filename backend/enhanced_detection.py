"""
Enhanced Detection Module
Provides advanced behavioral analysis and pattern detection
"""
import time
from collections import deque
from typing import Dict, List, Tuple, Optional
import numpy as np


class BehaviorAnalyzer:
    """Analyzes behavioral patterns to calculate suspicion scores"""
    
    def __init__(self, history_size: int = 50, time_window: float = 60.0):
        self.history_size = history_size
        self.time_window = time_window
        self.alert_history = deque(maxlen=history_size)
        
    def add_event(self, event_type: str, severity: str, timestamp: float = None):
        """Record a behavioral event"""
        if timestamp is None:
            timestamp = time.time()
        
        self.alert_history.append({
            'type': event_type,
            'severity': severity,
            'timestamp': timestamp
        })
    
    def calculate_suspicion_score(self) -> Tuple[int, List[str]]:
        """
        Calculate suspicion score based on recent behavior patterns
        Returns: (score, [reasons])
        Score ranges from 0-100, higher = more suspicious
        """
        if not self.alert_history:
            return 0, []
        
        current_time = time.time()
        recent_events = [
            event for event in self.alert_history
            if current_time - event['timestamp'] <= self.time_window
        ]
        
        if not recent_events:
            return 0, []
        
        score = 0
        reasons = []
        
        # Count events by severity
        urgent_count = sum(1 for e in recent_events if e['severity'] == 'urgent')
        warning_count = sum(1 for e in recent_events if e['severity'] == 'warning')
        attention_count = sum(1 for e in recent_events if e['severity'] == 'attention')
        
        # Score calculation
        if urgent_count > 0:
            score += urgent_count * 25  # Each urgent event adds 25 points
            reasons.append(f"{urgent_count} high-risk object(s) detected")
        
        if warning_count >= 3:
            score += 20  # Multiple gaze deviations
            reasons.append(f"{warning_count} gaze warnings in {int(self.time_window)}s")
        
        if attention_count >= 5:
            score += 15  # Frequent face disappearance or looking down
            reasons.append(f"{attention_count} attention alerts in {int(self.time_window)}s")
        
        # Pattern detection
        event_types = [e['type'] for e in recent_events]
        
        # Repeated looking down (reading notes pattern)
        looking_down_count = event_types.count('looking_down')
        if looking_down_count >= 3:
            score += 15
            reasons.append("Repeated looking down detected")
        
        # Alternating gaze pattern (suspicious)
        if 'looking_left' in event_types and 'looking_right' in event_types:
            score += 10
            reasons.append("Suspicious gaze alternation pattern")
        
        # Rapid event succession (nervous behavior)
        if len(recent_events) >= 5:
            time_diffs = [
                recent_events[i+1]['timestamp'] - recent_events[i]['timestamp']
                for i in range(len(recent_events) - 1)
            ]
            avg_interval = np.mean(time_diffs) if time_diffs else 0
            
            if avg_interval < 5.0 and len(recent_events) >= 5:  # Events less than 5 seconds apart
                score += 10
                reasons.append("Rapid suspicious activity detected")
        
        # Cap score at 100
        score = min(score, 100)
        
        return score, reasons
    
    def get_pattern_summary(self) -> Dict:
        """Get summary of behavioral patterns"""
        if not self.alert_history:
            return {
                'total_events': 0,
                'patterns': []
            }
        
        current_time = time.time()
        recent_events = [
            event for event in self.alert_history
            if current_time - event['timestamp'] <= self.time_window
        ]
        
        return {
            'total_events': len(recent_events),
            'urgent': sum(1 for e in recent_events if e['severity'] == 'urgent'),
            'warning': sum(1 for e in recent_events if e['severity'] == 'warning'),
            'attention': sum(1 for e in recent_events if e['severity'] == 'attention'),
            'time_window': f"{int(self.time_window)}s"
        }


class EyeGazeTracker:
    """Enhanced eye gaze tracking using iris landmarks"""
    
    @staticmethod
    def analyze_eye_gaze(face_landmarks, img_w: int, img_h: int) -> Dict:
        """
        Analyze eye gaze direction using iris landmarks
        Returns: dict with gaze direction and confidence
        """
        try:
            # Left eye iris landmarks (468-477 in MediaPipe)
            # Right eye iris landmarks (473-478)
            # For basic implementation, we use eye corners and center
            
            # Left eye: inner corner (133), outer corner (33), center (468)
            # Right eye: inner corner (362), outer corner (263), center (473)
            
            left_eye_inner = face_landmarks[133]
            left_eye_outer = face_landmarks[33]
            right_eye_inner = face_landmarks[362]
            right_eye_outer = face_landmarks[263]
            
            # Calculate eye openness (for blink detection)
            left_eye_top = face_landmarks[159]
            left_eye_bottom = face_landmarks[145]
            right_eye_top = face_landmarks[386]
            right_eye_bottom = face_landmarks[374]
            
            left_eye_height = abs(left_eye_top.y - left_eye_bottom.y) * img_h
            right_eye_height = abs(right_eye_top.y - right_eye_bottom.y) * img_h
            
            avg_eye_height = (left_eye_height + right_eye_height) / 2
            
            # Detect if eyes are closed (possible distraction or looking away)
            eyes_closed = avg_eye_height < 8  # Threshold for closed eyes
            
            # Calculate horizontal gaze direction
            left_eye_center_x = (left_eye_inner.x + left_eye_outer.x) / 2
            right_eye_center_x = (right_eye_inner.x + right_eye_outer.x) / 2
            
            # Normalized gaze (-1 = left, 0 = center, 1 = right)
            gaze_direction = (left_eye_center_x + right_eye_center_x) / 2 - 0.5
            
            return {
                'gaze_direction': gaze_direction,
                'eyes_closed': eyes_closed,
                'left_eye_height': left_eye_height,
                'right_eye_height': right_eye_height,
                'looking_away': abs(gaze_direction) > 0.15  # Threshold for looking away
            }
            
        except Exception as e:
            return {
                'gaze_direction': 0,
                'eyes_closed': False,
                'left_eye_height': 10,
                'right_eye_height': 10,
                'looking_away': False,
                'error': str(e)
            }


class ObjectDetectionAnalyzer:
    """Enhanced object detection with confidence filtering"""
    
    @staticmethod
    def filter_detections(results, confidence_threshold: float = 0.5) -> List[Dict]:
        """
        Filter YOLO detections by confidence threshold
        Returns: List of high-confidence detections
        """
        try:
            detections = []
            labels_df = results.pandas().xyxy[0]
            
            for _, row in labels_df.iterrows():
                if row['confidence'] >= confidence_threshold:
                    detections.append({
                        'name': row['name'],
                        'confidence': float(row['confidence']),
                        'bbox': [row['xmin'], row['ymin'], row['xmax'], row['ymax']]
                    })
            
            return detections
        except Exception as e:
            return []
    
    @staticmethod
    def analyze_object_context(detections: List[Dict]) -> Dict:
        """
        Analyze context of detected objects
        Returns: Risk assessment
        """
        risk_objects = {
            'cell phone': 10,
            'book': 8,
            'person': 9,
            'laptop': 5,
            'keyboard': 3,
            'mouse': 2
        }
        
        total_risk = 0
        detected_risks = []
        
        for detection in detections:
            obj_name = detection['name']
            confidence = detection['confidence']
            
            if obj_name in risk_objects:
                risk_value = risk_objects[obj_name] * confidence
                total_risk += risk_value
                detected_risks.append({
                    'object': obj_name,
                    'confidence': confidence,
                    'risk_score': risk_value
                })
        
        return {
            'total_risk': total_risk,
            'detected_risks': detected_risks,
            'high_risk': total_risk >= 8
        }


def get_alert_severity(event_type: str, has_objects: bool = False) -> str:
    """Determine alert severity based on event type and context"""
    if has_objects or event_type in ['cell_phone', 'book', 'extra_person']:
        return 'urgent'
    elif event_type in ['looking_left', 'looking_right', 'looking_down']:
        return 'warning'
    else:
        return 'attention'
