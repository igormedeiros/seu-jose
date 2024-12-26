import cv2
import numpy as np
import pygame
import time
import platform
import psutil
import GPUtil
import subprocess
import threading
import os
from queue import Queue
from utils import get_video_source
import sys

delay = 3  # Delay inicial para o teste

# Função para capturar informações do hardware e rede
def get_system_info():
    system_info = {
        "CPU": platform.processor(),
        "CPU Cores": psutil.cpu_count(logical=False),
        "Logical CPUs": psutil.cpu_count(logical=True),
        "Memory (GB)": round(psutil.virtual_memory().total / 1e9, 2),
    }
    gpus = GPUtil.getGPUs()
    if (gpus):
        system_info["GPU"] = gpus[0].name
        system_info["GPU Memory (GB)"] = gpus[0].memoryTotal
    else:
        system_info["GPU"] = "No GPU detected"
    return system_info

# Função para capturar informações de rede
def get_network_info():
    # Inicializa contadores de tráfego
    net_start = psutil.net_io_counters()
    time.sleep(1)  # Aguarda para medir a taxa de transferência
    net_end = psutil.net_io_counters()
    
    # Teste de latência
    try:
        result = subprocess.run(
            ["ping", "-c", "4", "8.8.8.8"], capture_output=True, text=True
        )
        latency = [
            float(line.split("time=")[-1].split(" ")[0])
            for line in result.stdout.split("\n")
            if "time=" in line
        ]
        avg_latency = sum(latency) / len(latency) if latency else None
        
    except Exception as e:
        avg_latency = None

    # Calcular tráfego de rede
    sent_bytes = net_end.bytes_sent - net_start.bytes_sent
    recv_bytes = net_end.bytes_recv - net_start.bytes_recv
    sent_rate = sent_bytes / 1.0  # Taxa de envio (Bps)
    recv_rate = recv_bytes / 1.0  # Taxa de recepção (Bps)

    network_info = {
        "Data Sent (MB)": round(sent_bytes / 1e6, 2),
        "Data Received (MB)": round(recv_bytes / 1e6, 2),
        "Send Rate (KB/s)": round(sent_rate / 1e3, 2),
        "Receive Rate (KB/s)": round(recv_rate / 1e3, 2),
        "Average Latency (ms)": round(avg_latency, 2) if avg_latency else "N/A",
    }
    
    return network_info

def flash_screen():
    """Create brighter, longer flashes"""
    pygame.init()
    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    timestamps = []
    time.sleep(delay)

    for _ in range(10):
        # Brighter white flash
        screen.fill((255, 255, 255))
        pygame.display.update()
        timestamps.append(time.time())
        time.sleep(0.5)  # Longer flash duration
        
        # Black screen
        screen.fill((0, 0, 0))
        pygame.display.update()
        time.sleep(0.5)  # Shorter interval
        
    pygame.quit()
    return timestamps

def initialize_camera():
    """Initialize camera without delay"""
    video_source = get_video_source()
    cap = cv2.VideoCapture(video_source)
    if not cap.isOpened():
        raise RuntimeError("Could not open camera")
    return cap

def adjust_camera_settings(cap):
    """Adjust camera settings to prevent auto-compensation"""
    # Disable auto exposure and auto gain if supported
    cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0)  # 0 = manual mode
    cap.set(cv2.CAP_PROP_EXPOSURE, -6)  # Lower exposure
    cap.set(cv2.CAP_PROP_GAIN, 0)  # Minimum gain
    cap.set(cv2.CAP_PROP_BRIGHTNESS, 128)  # Mid brightness
    cap.set(cv2.CAP_PROP_CONTRAST, 128)  # Mid contrast
    return cap

def camera_thread(cap, detections, flash_times, stop_event):
    cv2.namedWindow('Camera', cv2.WINDOW_NORMAL)
    cv2.resizeWindow('Camera', 960, 720)
    cv2.moveWindow('Camera', 0, 0)
    
    prev_brightness = 0
    latencies = []
    FLASH_THRESHOLD = 240
    
    while not stop_event.is_set():
        ret, frame = cap.read()
        if ret:
            frame = cv2.resize(frame, (960, 720))
            
            h, w = frame.shape[:2]
            x1, y1 = w//3, h//3
            x2, y2 = (w*2)//3, (h*2)//3
            
            center = frame[y1:y2, x1:x2]
            brightness = np.mean(center)
            brightness_change = brightness - prev_brightness
            
            # Detection area
            color = (0, 255, 0) if brightness_change <= FLASH_THRESHOLD else (0, 0, 255)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)
            
            # Current values
            cv2.putText(frame, f"Brightness: {brightness:.1f}", (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            cv2.putText(frame, f"Change: {brightness_change:.1f}", (10, 70),
                       cv2.FONT_HERSHEY_SIMPLEX, 1, color, 2)
            
            # Flash detection with synchronized printing
            if brightness_change > FLASH_THRESHOLD:
                detect_time = time.time()
                print("\n*** Flash detected! ***", flush=True)
                
                if flash_times:
                    flash_time = flash_times[-1]
                    latency = (detect_time - flash_time) * 1000
                    latencies.append(latency)
                    avg_latency = sum(latencies) / len(latencies)
                    
                    print(f"Latency: {latency:.1f}ms", flush=True)
                    print(f"Average ({len(latencies)} flashes): {avg_latency:.1f}ms", flush=True)
                    print("-" * 40, flush=True)
                
                detections.append(detect_time)
            
            prev_brightness = brightness
            cv2.imshow('Camera', frame)
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                # Print final report before closing
                if latencies:
                    print("\n=== Final Report ===", flush=True)
                    print(f"Total flashes: {len(latencies)}", flush=True)
                    print(f"Average latency: {sum(latencies)/len(latencies):.1f}ms", flush=True)
                    print(f"Min latency: {min(latencies):.1f}ms", flush=True)
                    print(f"Max latency: {max(latencies):.1f}ms", flush=True)
                stop_event.set()
                break

def measure_camera_latency(video_source, num_frames=100):
    cap = cv2.VideoCapture(video_source)
    acquisition_times = []
    
    for _ in range(num_frames):
        # Start timing before grab()
        start_time = time.time()
        
        # grab() only gets the frame from camera buffer
        grabbed = cap.grab()
        if not grabbed:
            break
            
        # retrieve() decodes the frame
        ret, frame = cap.retrieve()
        
        # Calculate acquisition time
        acquisition_time = time.time() - start_time
        acquisition_times.append(acquisition_time)
    
    cap.release()
    
    # Calculate statistics
    avg_acquisition = sum(acquisition_times) / len(acquisition_times)
    print(f"\n--- Camera Acquisition Test ---")
    print(f"Average acquisition time (s): {avg_acquisition:.4f}")
    print(f"Individual times (s): {acquisition_times}")
    
    return avg_acquisition, acquisition_times

def print_results(latencies, system_info, network_info):
    """Print test results with millisecond latency"""
    print("\n--- Teste Finalizado ---")
    
    if not latencies:
        print("Aviso: Nenhuma latência detectada. Verifique se as piscadas brancas foram capturadas.")
        return None
    
    # Convert to milliseconds and calculate stats
    latencies_ms = [lat * 1000 for lat in latencies]
    avg_latency_ms = sum(latencies_ms) / len(latencies_ms)
    min_latency_ms = min(latencies_ms)
    max_latency_ms = max(latencies_ms)
    
    print("\n--- Medições de Latência ---")
    print(f"Latência média: {avg_latency_ms:.2f} ms")
    print(f"Latência mínima: {min_latency_ms:.2f} ms")
    print(f"Latência máxima: {max_latency_ms:.2f} ms")
    print(f"Número de medições: {len(latencies)}")
    print("\nLatências individuais (ms):", [f"{lat:.2f}" for lat in latencies_ms])
    
    print("\n--- Informações do Sistema ---")
    for key, value in system_info.items():
        print(f"{key}: {value}")
        
    print("\n--- Informações da Rede ---")
    for key, value in network_info.items():
        print(f"{key}: {value}")

# Função principal para calcular latências e tempo de processamento
def main():
    # Initialize camera
    cap = cv2.VideoCapture(get_video_source())
    cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0)
    cap.set(cv2.CAP_PROP_EXPOSURE, -6)
    
    # Create windows
    cv2.namedWindow('Camera', cv2.WINDOW_NORMAL)
    cv2.namedWindow('Flash', cv2.WINDOW_NORMAL)
    cv2.resizeWindow('Camera', 960, 720)
    cv2.resizeWindow('Flash', 960, 720)
    cv2.moveWindow('Camera', 0, 0)
    cv2.moveWindow('Flash', 970, 0)
    
    prev_brightness = 0
    latencies = []
    FLASH_THRESHOLD = 200
    last_flash_time = None
    
    # Create black frame for flash window
    flash_frame = np.zeros((720, 960, 3), dtype=np.uint8)
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
            
        frame = cv2.resize(frame, (960, 720))
        
        # Analyze center region
        h, w = frame.shape[:2]
        x1, y1 = w//3, h//3
        x2, y2 = (w*2)//3, (h*2)//3
        center = frame[y1:y2, x1:x2]
        brightness = np.mean(center)
        brightness_change = brightness - prev_brightness
        
        # Draw detection box
        color = (0, 255, 0) if brightness_change <= FLASH_THRESHOLD else (0, 0, 255)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)
        
        # Show measurements
        cv2.putText(frame, f"Brightness: {brightness:.1f}", (10, 130),
               cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        cv2.putText(frame, f"Change: {brightness_change:.1f}", (10, 170),
               cv2.FONT_HERSHEY_SIMPLEX, 1, color, 2)
        
        # Flash detection
        if brightness > FLASH_THRESHOLD:
            detect_time = time.time()
            if last_flash_time:
                latency = (detect_time - last_flash_time) * 1000
                latencies.append(latency)
                avg_latency = sum(latencies) / len(latencies)
                
                cv2.putText(frame, "FLASH DETECTED!", (10, 250),
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                cv2.putText(frame, f"Latency: {latency:.1f}ms", (10, 290),
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
        
        prev_brightness = brightness
        cv2.imshow('Camera', frame)
        cv2.imshow('Flash', flash_frame)
        
        # Handle keyboard
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            if latencies:
                print("\n=== Final Report ===")
                print(f"Total flashes: {int(len(latencies) / 4)}")
                print(f"Average latency: {sum(latencies)/len(latencies):.1f}ms")
                print(f"Min latency: {min(latencies):.1f}ms")
                print(f"Max latency: {max(latencies):.1f}ms")
            break
        elif key == ord(' '):
            # Generate flash
            flash_frame.fill(255)
            cv2.imshow('Flash', flash_frame)
            last_flash_time = time.time()
            cv2.waitKey(200)  # Show white for 200ms
            flash_frame.fill(0)
            cv2.imshow('Flash', flash_frame)
    
    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()