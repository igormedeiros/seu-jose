# src/utils.py

import os
from dotenv import load_dotenv

import numpy as np

def calculate_angle(point1, point2, point3):
    """Calculate angle between three points"""
    vector1 = np.array([point1.x - point2.x, point1.y - point2.y])
    vector2 = np.array([point3.x - point2.x, point3.y - point2.y])
    
    cosine_angle = np.dot(vector1, vector2) / (np.linalg.norm(vector1) * np.linalg.norm(vector2))
    angle = np.arccos(cosine_angle)
    
    return np.degrees(angle)

def get_video_source():
        """Get video source from configuration"""
        # Get RTSP URL from environment variables
        
        load_dotenv()
        
        RTSP_USERNAME = os.getenv("RTSP_USERNAME")
        RTSP_ACCESS_KEY = os.getenv("RTSP_ACCESS_KEY")
        RTSP_CAMERA_IP = os.getenv("RTSP_CAMERA_IP")
        RTSP_CAMERA_PORT = os.getenv("RTSP_CAMERA_PORT")

        if not RTSP_USERNAME or not RTSP_ACCESS_KEY or not RTSP_CAMERA_IP:
            print("Error: Missing environment variables.")
            exit(1)

        rtsp_url = f'rtsp://{RTSP_USERNAME}:{RTSP_ACCESS_KEY}@{RTSP_CAMERA_IP}:{RTSP_CAMERA_PORT}/cam/realmonitor?channel=1&subtype=0'
            
        # rtsp_url = '3.mp4'
        return rtsp_url