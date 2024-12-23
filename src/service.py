# src/service.py

import os
import logging
import cv2
import numpy as np
import mediapipe as mp
import time

from datetime import datetime
from telegram import Bot
from telegram.ext import Updater, CommandHandler
from exceptions import NotificationException
from ultralytics import YOLO
from enums import PoseType, GenderType
from config import Config

class TelegramService:
    def __init__(self, config: Config):
        self.config = config
        self.token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID')
        self.bot = Bot(token=self.token)
        self.updater = Updater(token=self.token, use_context=True)
        self.dispatcher = self.updater.dispatcher
        self.alert_acknowledged = False
        self.last_alert_time = 0
        self.alert_interval = 300  # 5 minutes
        
        # Add command handlers
        self.dispatcher.add_handler(CommandHandler("ok", self.handle_ok))
        
    def start(self):
        self.updater.start_polling()
        
    def stop(self):
        self.updater.stop()
        
    def handle_ok(self, update, context):
        """Handle OK response from Telegram"""
        self.alert_acknowledged = True
        logging.info("Alert acknowledged by user")
        update.message.reply_text("Alert acknowledged. Stopping notifications.")

    def send_alert(self, pose, frame_or_risk_config, frame=None):
        """
        Send alert via Telegram
        Args:
            pose: PoseType value
            frame_or_risk_config: Either risk_config dict or frame when using legacy format
            frame: Frame image (optional, used with risk_config)
        """
        try:
            current_time = time.time()
            
            # Handle both parameter formats
            if isinstance(frame_or_risk_config, dict):
                risk_config = frame_or_risk_config
                frame_to_send = frame
            else:
                # Get risk config from pose when not provided
                risk_config = self.config.get_risk_level(pose)
                frame_to_send = frame_or_risk_config

            if (current_time - self.last_alert_time >= self.alert_interval or 
                not self.last_alert_time) and not self.alert_acknowledged:
                
                # Get alert message
                message = self.config.get_message(f"messages.alerts.{risk_config['risk']}")
                
                # Instead of sending text first, just send a single photo with caption:
                if frame_to_send is not None:
                    temp_image = f"alert_{risk_config['risk']}_{int(time.time())}.jpg"
                    cv2.imwrite(temp_image, frame_to_send)
                    
                    with open(temp_image, 'rb') as photo:
                        self.bot.send_photo(
                            chat_id=self.chat_id,
                            photo=photo,
                            caption=message
                        )
                    os.remove(temp_image)
                else:
                    # If no frame, optionally just send text, or skip if you always want a photo
                    self.bot.send_message(
                        chat_id=self.chat_id,
                        text=message
                    )

                self.last_alert_time = current_time
                logging.info(f"Alert sent with caption: {message}")
                
        except Exception as e:
            raise NotificationException(str(e))


class PoseService:
    def __init__(self, config: Config):
        self.config = config
        self.person_model = YOLO('yolov8n.pt')
        self.pose_model = YOLO('yolov8n-pose.pt')
        self.mp_pose = mp.solutions.pose
        self.mp_drawing = mp.solutions.drawing_utils
        self.pose_detector = self.mp_pose.Pose(
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
    
    def detect_person(self, frame):
        """Detect person in frame using YOLOv8"""
        person_results = self.person_model(frame)[0]
        persons = [det for det in person_results.boxes.data if det[5] == 0]
        
        if not persons:
            return None, None
        
        person = persons[np.argmax([det[4] for det in persons])]
        return person, map(int, person[:4])

    def draw_skeleton(self, frame, landmarks, bbox):
        """Draw skeleton on frame"""
        if landmarks is None or bbox is None:
            return False, None
            
        x1, y1, x2, y2 = bbox
        frame_height, frame_width = frame.shape[:2]
        crop_height = y2 - y1
        crop_width = x2 - x1
        
        # Create new pose landmarks using mediapipe solution proto
        landmarks_copy = self.mp_pose.PoseLandmark(0)
        landmarks_copy.landmark = [self.mp_pose.PoseLandmark(i) for i in range(33)]  # Initialize with 33 landmarks
        for idx, landmark in enumerate(landmarks.landmark):
            # Scale back to original frame
            x = int(landmark.x * crop_width + x1)
            y = int(landmark.y * crop_height + y1)
            
            # Update landmark coordinates
            landmarks_copy.landmark[idx].x = x / frame_width
            landmarks_copy.landmark[idx].y = y / frame_height
            landmarks_copy.landmark[idx].z = landmark.z
            landmarks_copy.landmark[idx].visibility = landmark.visibility
        
        self.mp_drawing.draw_landmarks(
            frame,
            landmarks_copy,
            self.mp_pose.POSE_CONNECTIONS,
            landmark_drawing_spec=self.mp_drawing.DrawingSpec(
                color=(0, 0, 255),
                thickness=2,
                circle_radius=2
            ),
            connection_drawing_spec=self.mp_drawing.DrawingSpec(
                color=(0, 255, 0),
                thickness=1
            )
        )
        return True, landmarks_copy

    def estimate_elderly_from_pose(self, landmarks):
        """Estimate if person is elderly based on pose"""
        if not landmarks:
            return False
            
        shoulders = landmarks.landmark[self.mp_pose.PoseLandmark.LEFT_SHOULDER].y
        hips = landmarks.landmark[self.mp_pose.PoseLandmark.LEFT_HIP].y
        
        posture_bend = abs(shoulders - hips)
        return posture_bend > 0.15

    def calculate_angle(self, point1, point2, point3):
        """Calculate angle between three points"""
        vector1 = np.array([point1.x - point2.x, point1.y - point2.y])
        vector2 = np.array([point3.x - point2.x, point3.y - point2.y])
        
        cosine_angle = np.dot(vector1, vector2) / (np.linalg.norm(vector1) * np.linalg.norm(vector2))
        angle = np.arccos(cosine_angle)
        
        return np.degrees(angle)

    def classify_pose(self, landmarks):
        """Classify pose with improved accuracy"""
        if not landmarks:
            return PoseType.UNKNOWN.value
            
        # Get key landmarks
        nose = landmarks.landmark[self.mp_pose.PoseLandmark.NOSE]
        left_shoulder = landmarks.landmark[self.mp_pose.PoseLandmark.LEFT_SHOULDER]
        right_shoulder = landmarks.landmark[self.mp_pose.PoseLandmark.RIGHT_SHOULDER]
        left_hip = landmarks.landmark[self.mp_pose.PoseLandmark.LEFT_HIP]
        right_hip = landmarks.landmark[self.mp_pose.PoseLandmark.RIGHT_HIP]
        left_knee = landmarks.landmark[self.mp_pose.PoseLandmark.LEFT_KNEE]
        right_knee = landmarks.landmark[self.mp_pose.PoseLandmark.RIGHT_KNEE]
        
        # Calculate average heights
        shoulder_height = (left_shoulder.y + right_shoulder.y) / 2
        hip_height = (left_hip.y + right_hip.y) / 2
        knee_height = (left_knee.y + right_knee.y) / 2
        
        # Calculate angles
        torso_angle = abs(shoulder_height - hip_height)
        leg_angle = abs(hip_height - knee_height)
        
        # Improved classification logic
        if nose.y > hip_height and torso_angle < 0.15:  # Head below hips and flat torso
            return PoseType.LYING.value
        elif torso_angle < 0.3 and leg_angle < 0.3:  # Bent posture
            return PoseType.SITTING.value
        else:
            return PoseType.STANDING.value

    def analyze_pose(self, frame):
        """Analyze pose in frame"""
        # First detect person with YOLO
        person_results = self.person_model(frame)[0]
        persons = [det for det in person_results.boxes.data if det[5] == 0]
        
        if not persons:
            return None, None, None, None
        
        # Get largest person detection
        person = persons[np.argmax([det[4] for det in persons])]
        x1, y1, x2, y2 = map(int, person[:4])
        
        # Crop frame to person area
        person_frame = frame[y1:y2, x1:x2]
        
        # Process pose only on cropped region
        image_rgb = cv2.cvtColor(person_frame, cv2.COLOR_BGR2RGB)
        results = self.pose_detector.process(image_rgb)
        
        if not results.pose_landmarks:
            return None, None, None, None
            
        is_elderly = self.estimate_elderly_from_pose(results.pose_landmarks)
        pose = self.classify_pose(results.pose_landmarks)
        
        return results.pose_landmarks, is_elderly, pose, (x1, y1, x2, y2)