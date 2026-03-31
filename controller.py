import subprocess
import os
import socket
import time
import signal
from gpiozero import Button

# --- CONFIGURATION ---
BASE_DIR = "/home/rishi/smart_reader"
PYTHON_BIN = f"{BASE_DIR}/env/bin/python"

# UPDATE THESE PATHS to match your exact folder names
EDGE_SCRIPT = f"{BASE_DIR}/smart_reader_2/smart_reader_2.py"
CLOUD_SCRIPT = f"{BASE_DIR}/cloud_reader/smart_reader_cloud.py"
TRIGGER_FILE = "/tmp/scan.trigger"

# Physical Pin 11 = GPIO 17
btn = Button(17, hold_time=2) 
current_process = None
is_cloud = False

def cleanup(signum, frame):
    """This function runs when systemd tells the script to stop."""
    global current_process
    print("\nSystem stopping: Cleaning up processes...")
    if current_process:
        current_process.terminate()
        # Wait a moment for it to die, then force kill if needed
        try:
            current_process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            current_process.kill()
    print("Cleanup complete. Exiting.")
    exit(0)

# REGISTER THE SIGNALS: This tells Python to run cleanup() 
# whenever the system tries to stop or interrupt the script.
signal.signal(signal.SIGTERM, cleanup)
signal.signal(signal.SIGINT, cleanup)

def has_internet():
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=2)
        return True
    except OSError:
        return False

def announce(text):
    print(f"ANNOUNCING: {text}")
    subprocess.run(f'pico2wave -w /tmp/mode.wav "{text}" && aplay /tmp/mode.wav 2>/dev/null', shell=True)

def start_script():
    global current_process
    if current_process:
        current_process.terminate()
        try:
            current_process.wait(timeout=1)
        except:
            current_process.kill()
    
    script = CLOUD_SCRIPT if is_cloud else EDGE_SCRIPT
    folder = os.path.dirname(script)
    
    print(f"Starting: {script}")
    # Inherit os.environ so it knows if a DISPLAY/Monitor is attached
    current_process = subprocess.Popen([PYTHON_BIN, os.path.basename(script)], cwd=folder)

def handle_click():
    print("Action: Single Click -> Creating trigger file.")
    # Create the tiny file that the sub-scripts are looking for
    open(TRIGGER_FILE, 'a').close()

def handle_hold():
    global is_cloud
    print("Action: Long Press -> Toggling Mode.")
    is_cloud = not is_cloud
    announce("Cloud Processing Active" if is_cloud else "Edge Processing Active")
    start_script()

btn.when_pressed = handle_click
btn.when_held = handle_hold

# --- BOOT LOGIC ---
# Clear any old triggers
if os.path.exists(TRIGGER_FILE): os.remove(TRIGGER_FILE)

is_cloud = has_internet()
announce("Cloud Processing Active" if is_cloud else "Edge Processing Active")
start_script()

print("Controller Ready. Running in background...")
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    if current_process: current_process.terminate()