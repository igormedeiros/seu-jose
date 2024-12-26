import cv2
import time
from rich.panel import Panel
from rich.table import Table
from service import TelegramService, PoseService
from logger import logging, console
from enums import PoseType, GenderType
from config import Config
import numpy as np

class MonitoringController:
    def __init__(self, config: Config):
        self.config = config
        self.telegram_service = TelegramService(config)
        self.pose_service = PoseService(config)
        
        # Pose tracking
        self.current_pose = None
        self.pose_frame_count = 0
        self.last_alert_time = 0
        self.fps = self.config.config["monitoring"]["performance"]["fps"]
        
        # Frame comparison
        self.previous_frame = None
        self.frame_threshold = 0.1
        
        # Performance monitoring
        self.processing_times = []  # Initialize empty list for processing times
        self.max_times_buffer = 30  # Keep last 30 measurements
        
    def calculate_moving_average(self):
        """Calculate moving average of processing times"""
        if not self.processing_times:
            return 0
        return sum(self.processing_times) / len(self.processing_times)
    
    def check_pose_duration(self, pose):
        """Check if pose has been maintained for required frames"""
        # Reset counter if pose changed
        if pose != self.current_pose:
            self.current_pose = pose
            self.pose_frame_count = 0
            logging.info(f"Pose changed to: {pose}")
            return False
        
        # Increment frame counter
        self.pose_frame_count += 1
        
        # Get required duration from config
        required_duration = (
            self.config.config["monitoring"]["pose_confirmation"]["emergency"]
            if pose == PoseType.LYING.value
            else self.config.config["monitoring"]["pose_confirmation"]["standard"]
        )
        
        # Calculate required frames (now with 10 fps)
        required_frames = int(required_duration * self.fps)  # 3s * 10fps = 30 frames for sitting
        
        # Log for debugging
        logging.info(f"Pose: {pose}, Frames: {self.pose_frame_count}/{required_frames}")
        
        # Check if enough frames have passed
        return self.pose_frame_count >= required_frames
    
    def process_frame_internal(self, frame):
        landmarks, is_elderly, pose, bbox = self.pose_service.analyze_pose(frame)
        
        if is_elderly:
            # Get risk configuration
            risk_config = self.config.get_risk_level(pose.lower())  # Ensure lowercase
            
            if self.check_pose_duration(pose):
                console.print(Panel.fit(
                    self.config.get_message(f"messages.alerts.{risk_config['risk']}"),
                    border_style=risk_config['color']
                ))
                self.telegram_service.send_alert(pose, risk_config, frame.copy())
        
        if landmarks is None:
            return frame, False, False, GenderType.UNKNOWN.value, PoseType.UNKNOWN.value
        
        if is_elderly:
            x1, y1, x2, y2 = bbox
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            success, _ = self.pose_service.draw_skeleton(frame, landmarks, bbox)
            
            required_duration = (
                self.config.config["monitoring"]["pose_confirmation"]["emergency"]
                if pose == PoseType.LYING.value
                else self.config.config["monitoring"]["pose_confirmation"]["standard"]
            )
            required_frames = int(required_duration * self.fps)
            
            cv2.putText(
                frame,
                f"Idoso - {pose} ({self.pose_frame_count}/{required_frames} frames)",
                (x1, y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.9,
                (0, 0, 255),
                2
            )
            
            if self.check_pose_duration(pose):
                risk_config = self.config.get_risk_level(pose.lower())
                if pose == PoseType.LYING.value:
                    console.print(Panel.fit(
                        self.config.get_message("messages.alerts.emergency"),
                        border_style="red"
                    ))
                    self.telegram_service.send_alert(pose, risk_config, frame.copy())
                elif pose == PoseType.SITTING.value:
                    console.print(Panel.fit(
                        self.config.get_message("messages.alerts.moderate"),
                        border_style="yellow"
                    ))
                    self.telegram_service.send_alert(pose, risk_config, frame.copy())
            
            return frame, True, True, GenderType.MALE.value, pose
            
        return frame, True, False, GenderType.UNKNOWN.value, PoseType.UNKNOWN.value
    
    def process_frame(self, frame):
        start_time = time.time()
        
        # Original frame processing
        frame, is_person, is_elderly, gender, position = self.process_frame_internal(frame)
        
        # Calculate current frame processing time
        current_time = (time.time() - start_time) * 1000  # to milliseconds
        
        # Update moving average
        self.processing_times.append(current_time)
        if len(self.processing_times) > self.max_times_buffer:
            self.processing_times.pop(0)
        
        avg_time = self.calculate_moving_average()
        
        # Add two-line time overlay
        cv2.putText(
            frame,
            f"Frame: {current_time:.1f}ms ({1000/current_time:.1f} FPS)",
            (10, 130),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0),
            2
        )
        
        cv2.putText(
            frame,
            f"Avg: {avg_time:.1f}ms ({1000/avg_time:.1f} FPS)",
            (10, 160),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0),
            2
        )
        
        return frame, is_person, is_elderly, gender, position
    
    def create_status_table(self, is_person, is_elderly, gender, position="unknown"):
        table = Table(title="Detection Status", show_header=True)
        
        table.add_column("Person Detected", style="green")
        table.add_column("Elderly Status", style="yellow")
        table.add_column("Gender", style="blue")
        table.add_column("Position", style="red")
        
        table.add_row(
            "✓" if is_person else "✗",
            "Elderly" if is_elderly else "Not Elderly",
            gender.capitalize(),
            position.capitalize()
        )
        
        return table
    
    def has_significant_change(self, frame):
        """Quick check for frame differences"""
        if self.previous_frame is None:
            self.previous_frame = frame.copy()
            return True
            
        # Calculate simple difference
        diff = cv2.absdiff(
            cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY),
            cv2.cvtColor(self.previous_frame, cv2.COLOR_BGR2GRAY)
        )
        
        # Quick mean calculation
        mean_diff = np.mean(diff)
        
        # Update previous frame only if different
        if mean_diff > self.frame_threshold:
            self.previous_frame = frame.copy()
            return True
            
        return False

    def run(self, video_source):
        cap = cv2.VideoCapture(video_source)
        
        try:
            target_fps = self.config.config["monitoring"]["performance"]["fps"]
            process_delay = 1.0 / target_fps
            next_process_time = time.time()
            
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                
                # Quick resize for comparison
                resized = cv2.resize(frame, (self.pose_service.display_width, self.pose_service.display_height))
                
                # Skip processing if frame hasn't changed
                if not self.has_significant_change(resized):
                    cv2.imshow("Elderly Monitoring System", resized)
                    continue
                
                # Process only changed frames
                if time.time() >= next_process_time:
                    processed_frame, is_person, is_elderly, gender, position = self.process_frame(resized)
                    cv2.imshow("Elderly Monitoring System", processed_frame)
                    next_process_time = time.time() + process_delay
                
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
                    
        finally:
            cap.release()
            cv2.destroyAllWindows()
            self.telegram_service.stop()

    def draw_skeleton(self, frame, landmarks):
        """
        Draw skeleton on frame and return status
        Args:
            frame: Input image frame
            landmarks: MediaPipe pose landmarks
        Returns:
            Tuple(bool, landmarks): Success status and landmarks
        """
        if landmarks is None:
            return False, None
            
        try:
            self.mp_drawing.draw_landmarks(
                frame,
                landmarks,
                self.mp_pose.POSE_CONNECTIONS,
                landmark_drawing_spec=self.mp_drawing.DrawingSpec(
                    color=(0, 0, 255),
                    thickness=3,
                    circle_radius=3
                ),
                connection_drawing_spec=self.mp_drawing.DrawingSpec(
                    color=(0, 255, 0),
                    thickness=2
                )
            )
            return True, landmarks
        except Exception as e:
            logging.error(f"Error drawing skeleton: {str(e)}")
            return False, None