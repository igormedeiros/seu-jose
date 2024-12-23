# src/main.py
from dotenv import load_dotenv
from controller import MonitoringController
from logger import setup_logging
from config import Config

import os

def main():
    load_dotenv()
    setup_logging()
    
    config = Config(lang=os.getenv("LANGUAGE", "pt"))
    controller = MonitoringController(config)
    controller.run()

if __name__ == "__main__":
    main()