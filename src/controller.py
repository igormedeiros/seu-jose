import cv2
import time 
from rich.panel import Panel
from rich.table import Table
from service import TelegramService, PoseService
from logger import logging, console
from enums import PoseType, GenderType
from config import Config

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
        
        # Performance monitoring
        self.processing_times = []
        self.max_times_buffer = 30  # Keep last 30 frames for moving average
        self.frame_count = 0
    
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
                f"Elderly Male - {pose} ({self.pose_frame_count}/{required_frames} frames)",
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
    
    def run(self, video_source='1.mp4'):
        """Run the monitoring system"""
        console.print("[bold green]Starting Elderly Monitoring System...[/]")
        logging.info("System started")
        
        self.telegram_service.start()
        
        try:
            cap = cv2.VideoCapture(video_source)
            
            # Get FPS from config
            frame_rate = self.config.config["monitoring"]["performance"]["fps"]
            prev_time = 0

            with console.status("[bold blue]Processing video feed...") as status:
                while True:
                    ret, frame = cap.read()
                    if not ret:
                        break
                    
                    current_time = time.time()
                    elapsed_time = current_time - prev_time

                    # Process frame at configured FPS
                    if elapsed_time > 1.0 / frame_rate:
                        prev_time = current_time
                        frame, is_person, is_elderly, gender, position = self.process_frame(frame)
                        
                        if is_person:
                            console.print("[green]Person detected! 👤[/]")
                            if is_elderly:
                                console.print(Panel.fit(
                                    f"[bold yellow]Elderly {gender} detected! 👴[/]",
                                    border_style="red"
                                ))
                    
                        status_table = self.create_status_table(is_person, is_elderly, gender, position)
                        console.print(status_table)
                        console.print("-" * 50)
                        
                        cv2.imshow("Elderly Monitoring System", frame)
                    
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break
                
        finally:
            cap.release()
            cv2.destroyAllWindows()
            self.telegram_service.stop()
            logging.info("System stopped")
            console.print("[bold red]Monitoring system stopped.[/]")

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
