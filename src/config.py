# src/config.py
import yaml
from pathlib import Path
from typing import Dict, Any

class Config:
    def __init__(self, config_path: str = "config/config.yaml", lang: str = "pt"):
        self.config_path = Path(config_path)
        self.lang = lang
        self.config = self._load_config()
        self.messages = self._load_messages()
    
    def _load_config(self) -> Dict[str, Any]:
        with open(self.config_path) as f:
            return yaml.safe_load(f)
    
    def _load_messages(self) -> Dict[str, Any]:
        lang_file = Path(f"config/i18n/{self.lang}.yaml")
        with open(lang_file) as f:
            return yaml.safe_load(f)
    
    def get_risk_level(self, pose: str) -> Dict[str, Any]:
        pose_risks = self.config["monitoring"]["pose_risks"]
        risk_levels = self.config["monitoring"]["risk_levels"]
        pose_risk = pose_risks.get(pose, {}).get("risk", "low")
        risk_config = risk_levels[pose_risk]
        risk_config["risk"] = pose_risk
        return risk_config
    
    def get_message(self, key: str, **kwargs) -> str:
        """Get localized message with formatting"""
        keys = key.split(".")
        msg = self.messages
        for k in keys:
            msg = msg[k]
        return msg.format(**kwargs)