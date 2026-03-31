import RPi.GPIO as GPIO
import threading
import time
import subprocess
import os
import socket

# --- CONFIGURATION ---
BASE_DIR = "/home/rishi/smart_reader"
PYTHON_BIN = f"{BASE_DIR}/env/bin/python"
EDGE_SCRIPT = f"{BASE_DIR}/smart_reader_2/smart_reader_2.py"
CLOUD_SCRIPT = f"{BASE_DIR}/cloud_reader/smart_reader_cloud.py"
TRIGGER_FILE = "/tmp/scan.trigger"
CLICK_SOUND = f"{BASE_DIR}/click.wav"

current_process = None
is_cloud = False

# --- AUDIO & PROCESS MANAGEMENT ---
def play_click():
    if os.path.exists(CLICK_SOUND):
        subprocess.Popen(['aplay', CLICK_SOUND, '-q'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def announce(text):
    print(f"ANNOUNCING: {text}")
    subprocess.run(f'pico2wave -w /tmp/mode.wav "{text}" && aplay /tmp/mode.wav 2>/dev/null', shell=True)

def silence_system():
    subprocess.run(['pkill', 'aplay'], stderr=subprocess.DEVNULL)
    subprocess.run(['pkill', 'mpg123'], stderr=subprocess.DEVNULL)

def start_script():
    global current_process
    if current_process:
        current_process.terminate()
        try:
            current_process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            current_process.kill()
    
    silence_system()
    if os.path.exists(TRIGGER_FILE): os.remove(TRIGGER_FILE)

    script = CLOUD_SCRIPT if is_cloud else EDGE_SCRIPT
    current_process = subprocess.Popen([PYTHON_BIN, os.path.basename(script)], cwd=os.path.dirname(script))

# --- DEFERRED EVALUATION BUTTON LOGIC (For 'A') ---
class AdvancedButton:
    """Waits for falling edges and 500ms timeouts before acting."""
    def __init__(self, timeout=0.5, hold_time=1.0):
        self.timeout = timeout
        self.hold_time = hold_time
        self.click_count = 0
        self.press_time = 0
        self.timer = None

    def press(self):
        # Cancel any active timeout if clicked again quickly
        if self.timer:
            self.timer.cancel()
        self.press_time = time.time()

    def release(self):
        duration = time.time() - self.press_time
        
        # If held for a long time, evaluate immediately upon release
        if duration >= self.hold_time:
            self.on_hold()
            self.click_count = 0 
        else:
            # Short press: increment count and start the 500ms waiting period
            self.click_count += 1
            self.timer = threading.Timer(self.timeout, self._evaluate_clicks)
            self.timer.start()

    def _evaluate_clicks(self):
        # This only runs if 500ms passes with NO further clicks
        if self.click_count == 1:
            self.on_single()
        elif self.click_count >= 2:
            self.on_double()
        self.click_count = 0

    # The Actions assigned to 'A'
    def on_single(self):
        print("ACTION: Single Click Validated -> Scanning")
        open(TRIGGER_FILE, 'a').close()

    def on_double(self):
        print("ACTION: Double Click Validated -> Shutting Down")
        announce("Shutting down now. Goodbye.")
        time.sleep(1)
        subprocess.run(['sudo', 'shutdown', 'now'])

    def on_hold(self):
        global is_cloud
        print("ACTION: Hold Validated -> Switching Modes")
        is_cloud = not is_cloud
        start_script()
        announce("Cloud Processing Active" if is_cloud else "Edge Processing Active")

control_btn_A = AdvancedButton()

# --- MULTI-TAP & CATEGORY LOGIC ---
CATEGORIES = {
    "1": "I need help immediately.",
    "2": "I am hungry, I need food.",
    "3": "I am thirsty, I need water.",
    "4": "I need to use the restroom.",
    "5": "I am feeling unwell.",
    "6": "Thank you."
}
MULTITAP_MAP = {'7': 'pqrs', '8': 'tuv', '9': 'wxyz', '0': ' '}

current_word = ""
last_tap_key = None
last_tap_time = 0
char_idx = 0

def handle_typing_press(key):
    global current_word, last_tap_key, last_tap_time, char_idx
    play_click()

    if key in CATEGORIES:
        announce(CATEGORIES[key])
        current_word = ""

    elif key in MULTITAP_MAP:
        now = time.time()
        if key == last_tap_key and (now - last_tap_time) < 0.8:
            char_idx = (char_idx + 1) % len(MULTITAP_MAP[key])
            current_word = current_word[:-1] + MULTITAP_MAP[key][char_idx]
        else:
            char_idx = 0
            current_word += MULTITAP_MAP[key][0]
        
        last_tap_key = key
        last_tap_time = now
        announce(current_word[-1])

    elif key == "#":
        if current_word:
            # We use an edge-tts command directly to speak typed words
            subprocess.run(f'/home/rishi/smart_reader/env/bin/edge-tts --text "{current_word}" --voice en-IN-NeerjaNeural --play', shell=True)
            current_word = ""

    elif key == "*":
        if current_word:
            current_word = current_word[:-1]
            announce("Deleted")
        else:
            silence_system()
            announce("Silenced")

# --- INDUSTRIAL KEYPAD SCANNER ---
class MatrixKeypad:
    """Non-blocking scanner with 30ms strict software debouncing."""
    def __init__(self):
        self.ROWS = [5, 6, 13, 19]
        self.COLS = [12, 16, 20, 21]
        self.KEYS = [
            ['1', '2', '3', 'A'],
            ['4', '5', '6', 'B'],
            ['7', '8', '9', 'C'],
            ['*', '0', '#', 'D']
        ]
        
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        for row in self.ROWS:
            GPIO.setup(row, GPIO.OUT)
            GPIO.output(row, GPIO.HIGH)
        for col in self.COLS:
            GPIO.setup(col, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        self.state = {r: {c: False for c in range(4)} for r in range(4)}
        self.debounce = {r: {c: 0 for c in range(4)} for r in range(4)}
        self.THRESHOLD = 3 # Requires 3 consecutive identical reads to register an edge

        threading.Thread(target=self._scan_loop, daemon=True).start()

    def _scan_loop(self):
        while True:
            for r_idx, row in enumerate(self.ROWS):
                GPIO.output(row, GPIO.LOW)
                for c_idx, col in enumerate(self.COLS):
                    # Pulled up normally. LOW means pressed.
                    is_pressed = not GPIO.input(col) 
                    
                    if is_pressed != self.state[r_idx][c_idx]:
                        self.debounce[r_idx][c_idx] += 1
                        if self.debounce[r_idx][c_idx] >= self.THRESHOLD:
                            self.state[r_idx][c_idx] = is_pressed
                            self.debounce[r_idx][c_idx] = 0
                            self._trigger_edge(self.KEYS[r_idx][c_idx], is_pressed)
                    else:
                        self.debounce[r_idx][c_idx] = 0
                GPIO.output(row, GPIO.HIGH)
            time.sleep(0.01) # 10ms loop time. 10ms * 3 threshold = 30ms stable debounce

    def _trigger_edge(self, key, is_pressed):
        if key == 'A':
            if is_pressed: control_btn_A.press()
            else: control_btn_A.release()
        else:
            # Typing/Categories only care about the rising edge (the press down)
            if is_pressed: handle_typing_press(key)

# --- BOOT UP ---
keypad_thread = MatrixKeypad()

try:
    socket.create_connection(("8.8.8.8", 53), timeout=2)
    is_cloud = True
except:
    is_cloud = False

announce("Controller Online. Cloud Processing Active" if is_cloud else "Controller Online. Edge Processing Active")
start_script()

try:
    while True: time.sleep(1) # Keep main thread alive
except KeyboardInterrupt:
    if current_process: current_process.terminate()
    GPIO.cleanup()