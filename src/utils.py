# src/utils.py

import numpy as np

def calculate_angle(point1, point2, point3):
    """Calculate angle between three points"""
    vector1 = np.array([point1.x - point2.x, point1.y - point2.y])
    vector2 = np.array([point3.x - point2.x, point3.y - point2.y])
    
    cosine_angle = np.dot(vector1, vector2) / (np.linalg.norm(vector1) * np.linalg.norm(vector2))
    angle = np.arccos(cosine_angle)
    
    return np.degrees(angle)
