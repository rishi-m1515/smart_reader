import subprocess
import os
import socket
import time
import signal
from gpiozero import Button

# --- CONFIGURATION ---
BASE_DIR = "/home/rishi/smart_reader"
PYTHON_BIN = f"{BASE_DIR}/env/bin/python"
EDGE_SCRIPT = f"{BASE_DIR}/smart_reader_2/smart_reader_2.py"
CLOUD_SCRIPT = f"{BASE_DIR}/cloud_reader/smart_reader_cloud.py"
TRIGGER_FILE = "/tmp/scan.trigger"

# Paths to sound files (Place these in your ~/smart_reader folder)
CLICK_SOUND = f"{BASE_DIR}/click.wav"

btn = Button(17, hold_time=2) 
current_process = None
is_cloud = False

last_click_time = 0
double_click_threshold = 0.4
is_confirming_shutdown = False
shutdown_timer = 0

def cleanup(signum, frame):
    global current_process
    if current_process:
        current_process.terminate()
        try:
            current_process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            current_process.kill()
    exit(0)

signal.signal(signal.SIGTERM, cleanup)
signal.signal(signal.SIGINT, cleanup)

def play_click():
    """Plays a quick click sound immediately."""
    if os.path.exists(CLICK_SOUND):
        subprocess.Popen(['aplay', CLICK_SOUND, '-q'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def announce(text):
    print(f"ANNOUNCING: {text}")
    subprocess.run(f'pico2wave -w /tmp/mode.wav "{text}" && aplay /tmp/mode.wav 2>/dev/null', shell=True)

def silence_system():
    """Forcefully stops all background audio processes immediately."""
    # kills aplay (Edge/System sounds) and any edge-tts/mpg123 processes
    subprocess.run(['pkill', 'aplay'], stderr=subprocess.DEVNULL)
    subprocess.run(['pkill', 'mpg123'], stderr=subprocess.DEVNULL)
    # If using pygame, this is harder to kill from outside, 
    # but killing the sub-script usually handles it.

def start_script():
    global current_process
    if current_process:
        print("Switching modes: Terminating previous process...")
        current_process.terminate()
        try:
            current_process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            current_process.kill() # Force kill if it's stuck in a heavy OCR loop
    
    # 1. SILENCE everything before announcing the new mode
    silence_system()
    
    # 2. CLEAR the trigger file so an old click doesn't carry over
    if os.path.exists(TRIGGER_FILE):
        os.remove(TRIGGER_FILE)

    script = CLOUD_SCRIPT if is_cloud else EDGE_SCRIPT
    folder = os.path.dirname(script)
    current_process = subprocess.Popen([PYTHON_BIN, os.path.basename(script)], cwd=folder)

def handle_double_click_logic():
    global is_confirming_shutdown, shutdown_timer
    if not is_confirming_shutdown:
        is_confirming_shutdown = True
        shutdown_timer = time.time()
        announce("Do you want to shutdown? Click once to confirm, or double click to cancel.")
    else:
        is_confirming_shutdown = False
        announce("Shutdown cancelled.")

def handle_click():
    global last_click_time, is_confirming_shutdown
    play_click() # Immediate feedback
    
    current_time = time.time()
    if (current_time - last_click_time) < double_click_threshold:
        handle_double_click_logic()
    else:
        if is_confirming_shutdown:
            announce("Shutting down now. Goodbye.")
            time.sleep(1)
            subprocess.run(['sudo', 'shutdown', 'now'])
        else:
            open(TRIGGER_FILE, 'a').close()
            
    last_click_time = current_time

def handle_hold():
    global is_cloud, is_confirming_shutdown
    # If we were in shutdown mode, cancel it first
    is_confirming_shutdown = False 
    
    print("Action: Long Press -> Hard Reset & Toggle Mode.")
    is_cloud = not is_cloud
    
    # The start_script now handles silencing and clearing triggers
    start_script()
    
    # Announce the new mode only AFTER the old one is dead and silent
    announce("Cloud Processing Active" if is_cloud else "Edge Processing Active")

btn.when_pressed = handle_click
btn.when_held = handle_hold

if os.path.exists(TRIGGER_FILE): os.remove(TRIGGER_FILE)
try:
    socket.create_connection(("8.8.8.8", 53), timeout=2)
    is_cloud = True
except:
    is_cloud = False

announce("Cloud Processing Active" if is_cloud else "Edge Processing Active")
start_script()

try:
    while True:
        if is_confirming_shutdown and (time.time() - shutdown_timer > 15):
            is_confirming_shutdown = False
            announce("Shutdown request timed out.")
        time.sleep(0.1)
except KeyboardInterrupt:
    if current_process: current_process.terminate()