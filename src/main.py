# src/main.py
from dotenv import load_dotenv
from controller import MonitoringController
from logger import setup_logging
from config import Config

import os

def main():
    load_dotenv()
    setup_logging()
    
    config = Config(lang=os.getenv("LANGUAGE"))
    controller = MonitoringController(config)
    
    # Get RTSP URL from environment variables
    RTSP_USERNAME = os.getenv("RTSP_USERNAME")
    RTSP_ACCESS_KEY = os.getenv("RTSP_ACCESS_KEY")
    RTSP_CAMERA_IP = os.getenv("RTSP_CAMERA_IP")
    RTSP_CAMERA_PORT = os.getenv("RTSP_CAMERA_PORT")

    if not RTSP_USERNAME or not RTSP_ACCESS_KEY or not RTSP_CAMERA_IP:
        print("Error: Missing environment variables.")
        exit(1)

    rtsp_url = f'rtsp://{RTSP_USERNAME}:{RTSP_ACCESS_KEY}@{RTSP_CAMERA_IP}:{RTSP_CAMERA_PORT}/cam/realmonitor?channel=1&subtype=0'
        
    rtsp_url = '1.mp4'
    
    controller.run(rtsp_url)

if __name__ == "__main__":
    main()