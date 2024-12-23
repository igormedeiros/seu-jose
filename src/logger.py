# src/logger.py
import logging
from rich.console import Console

console = Console()

def setup_logging():
    logging.basicConfig(
        filename='elderly_monitoring.log',
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )