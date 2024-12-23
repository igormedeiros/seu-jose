# src/exceptions.py

class MonitoringException(Exception):
    """Base exception for monitoring system"""
    def __init__(self, message: str, error_code: int = None, details: dict = None):
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)

    def __str__(self):
        error_str = f"[Error {self.error_code}] {self.message}" if self.error_code else self.message
        if self.details:
            error_str += f"\nDetails: {self.details}"
        return error_str

class CameraException(MonitoringException):
    """Camera related exceptions"""
    def __init__(self, message: str, device_id: str = None, **kwargs):
        super().__init__(
            message=message,
            error_code=1000,
            details={
                "device_id": device_id,
                "type": "camera_error",
                **kwargs
            }
        )

class DetectionException(MonitoringException):
    """Detection related exceptions"""
    def __init__(self, message: str, model_name: str = None, frame_id: int = None, **kwargs):
        super().__init__(
            message=message,
            error_code=2000,
            details={
                "model_name": model_name,
                "frame_id": frame_id,
                "type": "detection_error",
                **kwargs
            }
        )

class NotificationException(MonitoringException):
    """Notification related exceptions"""
    def __init__(self, message: str, notification_type: str = None, recipient: str = None, **kwargs):
        super().__init__(
            message=message,
            error_code=3000,
            details={
                "notification_type": notification_type,
                "recipient": recipient,
                "type": "notification_error",
                **kwargs
            }
        )