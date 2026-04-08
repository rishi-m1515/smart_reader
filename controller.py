import RPi.GPIO as GPIO
import threading
import time
import subprocess
import os
import socket
import hashlib


# --- CONFIGURATION ---
BASE_DIR = "/home/rishi/smart_reader"
PYTHON_BIN = f"{BASE_DIR}/env/bin/python"
EDGE_SCRIPT = f"{BASE_DIR}/smart_reader_2/smart_reader_2.py"
CLOUD_SCRIPT = f"{BASE_DIR}/cloud_reader/smart_reader_cloud.py"
TRIGGER_FILE = "/tmp/scan.trigger"
CLICK_SOUND = f"{BASE_DIR}/click.wav"
EDGE_TTS_BIN = f"{BASE_DIR}/env/bin/edge-tts"

# --- NEW CONFIG ---
PRESETS_DIR = f"{BASE_DIR}/preset_recordings"
os.makedirs(PRESETS_DIR, exist_ok=True) # Creates the folder if it doesn't exist

current_process = None
is_cloud = False

# --- SYSTEM STATE ---
custom_mode_active = False
input_mode = 'letters' # 'letters' or 'numbers'
current_case = 'lower' # 'lower' or 'upper'
current_word = ""

# --- AUDIO & PROCESS MANAGEMENT ---
def play_click():
    """Fires instantly on physical press."""
    if os.path.exists(CLICK_SOUND):
        subprocess.Popen(['aplay', CLICK_SOUND, '-q'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def get_safe_filename(text):
    """Creates a unique MP3 filename based on the text."""
    # Hashes the text so "I am hungry" becomes something like "b4f2c...mp3"
    file_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
    return os.path.join(PRESETS_DIR, f"{file_hash}.mp3")

def silence_system():
    subprocess.run(['pkill', 'aplay'], stderr=subprocess.DEVNULL)
    subprocess.run(['pkill', 'mpg123'], stderr=subprocess.DEVNULL)

def check_internet():
    """Quickly checks if the Pi actually has internet access."""
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=1.5)
        return True
    except:
        return False

def speak_cached(text):
    """For Presets & UX: Hands off TTS generation to a background thread so the keypad never freezes."""
    def audio_task():
        filepath = get_safe_filename(text)
        
        # 1. If cached, play it instantly in the background
        if os.path.exists(filepath):
            silence_system() 
            subprocess.Popen(['mpg123', '-q', filepath], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return

        # 2. If not recorded and we have Wi-Fi, generate then play
        if check_internet():
            print(f"Caching new audio for: {text}")
            gen_cmd = f'{EDGE_TTS_BIN} --text "{text}" --write-media {filepath} --voice en-IN-NeerjaNeural'
            result = subprocess.run(gen_cmd, shell=True) 
            
            if result.returncode == 0 and os.path.exists(filepath):
                silence_system()
                subprocess.Popen(['mpg123', '-q', filepath], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return

        # 3. Fallback: Offline generation
        print(f"Fallback local TTS for: {text}")
        safe_text = text.replace('"', '').replace("'", "").strip()
        subprocess.run(f'pico2wave -w /tmp/local.wav "{safe_text}"', shell=True) 
        silence_system()
        subprocess.Popen(['aplay', '/tmp/local.wav', '-q'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Start the task in a new thread instantly!
    threading.Thread(target=audio_task, daemon=True).start()

def speak_dynamic(text):
    """For Custom Typing: Hands off dynamic generation to a background thread."""
    def audio_task():
        if check_internet():
            temp_file = "/tmp/dynamic.mp3"
            gen_cmd = f'{EDGE_TTS_BIN} --text "{text}" --write-media {temp_file} --voice en-IN-NeerjaNeural'
            result = subprocess.run(gen_cmd, shell=True)
            if result.returncode == 0 and os.path.exists(temp_file):
                silence_system()
                subprocess.Popen(['mpg123', '-q', temp_file], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return

        # Fallback
        safe_text = text.replace('"', '').replace("'", "").strip()
        subprocess.run(f'pico2wave -w /tmp/local.wav "{safe_text}"', shell=True)
        silence_system()
        subprocess.Popen(['aplay', '/tmp/local.wav', '-q'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Start the task in a new thread instantly!
    threading.Thread(target=audio_task, daemon=True).start()

def announce(text):
    speak_cached(text)

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

# --- ADVANCED BUTTON (Falling Edge / Deferred Eval) ---
class AdvancedButton:
    def __init__(self, timeout=0.5, hold_time=1.0):
        self.timeout = timeout
        self.hold_time = hold_time
        self.click_count = 0
        self.press_time = 0
        self.timer = None

    def press(self):
        if self.timer:
            self.timer.cancel()
        self.press_time = time.time()

    def release(self):
        duration = time.time() - self.press_time
        if duration >= self.hold_time:
            self.on_hold()
            self.click_count = 0 
        else:
            self.click_count += 1
            self.timer = threading.Timer(self.timeout, self._evaluate_clicks)
            self.timer.start()

    def _evaluate_clicks(self):
        if self.click_count == 1:
            self.on_single()
        elif self.click_count >= 2:
            self.on_double()
        self.click_count = 0

    def on_single(self):
        print("ACTION: Single Click -> Scanning")
        open(TRIGGER_FILE, 'a').close()

    def on_double(self):
        speak_cached("Shutting down now. Goodbye.") # Use CACHED
        time.sleep(2)
        subprocess.run(['sudo', 'shutdown', 'now'])

    def on_hold(self):
        global is_cloud
        is_cloud = not is_cloud
        start_script()
        msg = "Cloud Processing Active" if is_cloud else "Edge Processing Active"
        speak_cached(msg) # Use CACHED

control_btn_A = AdvancedButton()

# --- PRESET & CUSTOM MODE LOGIC ---
PRESETS = {
    "1": "I need medical assistance immediately.",
    "2": "Please help me find my way or call 9 1 2 3 4 5 6 7 8 9.",
    "3": "I need to use the restroom, could you lead me there?",
    "4": "I am hungry.",
    "5": "I am thirsty.",
    "6": "I need my medication. It is in my bag.",
    "7": "Hello. I am blind and unable to speak. I communicate using this device.",
    "8": "Yes.",
    "9": "No.",
    "0": "Thank you."
}

MULTITAP_LETTERS = {
    '1': '.,?!', '2': 'abc', '3': 'def', '4': 'ghi', '5': 'jkl', 
    '6': 'mno', '7': 'pqrs', '8': 'tuv', '9': 'wxyz', '0': ' '
}
MULTITAP_NUMBERS = {str(i): str(i) for i in range(10)}

last_tap_key = None
last_tap_time = 0
char_idx = 0

def handle_preset_mode(key):
    global custom_mode_active
    
    if key == '#':
        custom_mode_active = True
        speak_cached("Custom message mode activated.") # Will cache!
        
    elif key in PRESETS:
        silence_system() 
        speak_cached(PRESETS[key]) # Will cache your emergency presets permanently!
        
    elif key == 'B': 
        print("ACTION: Cancel Processing -> Hard Reset")
        start_script() 
        speak_cached("Scan cancelled.") 
        
    elif key in ['C', 'D', '*']:
        speak_cached("Unassigned key.")

def handle_custom_mode(key):
    global custom_mode_active, input_mode, current_case, current_word, last_tap_key, last_tap_time, char_idx

    if key == '#':
        custom_mode_active = False
        speak_cached("Preset mode activated.")
    
    elif key == 'A': # Single Delete (Short tap)
        if current_word:
            current_word = current_word[:-1]
            speak_cached("Deleted")
        else:
            speak_cached("Empty")
            
    elif key == 'A_HOLD': # Clear All (2-second hold)
        if current_word:
            current_word = "" # Wipes the entire string
            speak_cached("Cleared all text.")
        else:
            speak_cached("Empty")
            
    elif key == 'B': # Review
        if current_word:
            # We use dynamic here because the word is custom
            speak_dynamic(f"{current_word}") 
        else:
            speak_cached("Text is empty.")
            
    elif key == 'C': # Toggle Case
        current_case = 'upper' if current_case == 'lower' else 'lower'
        speak_cached(f"{current_case}case")
        
    elif key == 'D': # Confirm / Send
        if current_word:
            speak_dynamic(current_word) # Dynamic because it's a custom sentence
            current_word = "" 
        else:
            speak_cached("Nothing to send.")
            
    elif key == '*': # Toggle Numbers/Letters
        input_mode = 'numbers' if input_mode == 'letters' else 'letters'
        speak_cached(f"{input_mode} mode")

    elif key in MULTITAP_LETTERS:
        now = time.time()
        active_map = MULTITAP_NUMBERS if input_mode == 'numbers' else MULTITAP_LETTERS
        
        # --- INCREASED TIMEOUT ---
        # Bumped up to 2.5 seconds to easily allow double and triple clicks
        if input_mode == 'letters' and key == last_tap_key and (now - last_tap_time) < 1:
            char_idx = (char_idx + 1) % len(active_map[key])
            new_char = active_map[key][char_idx]
            if current_case == 'upper': new_char = new_char.upper()
            current_word = current_word[:-1] + new_char
        else:
            char_idx = 0
            new_char = active_map[key][0]
            if current_case == 'upper' and input_mode == 'letters': new_char = new_char.upper()
            current_word += new_char
        
        last_tap_key = key
        last_tap_time = now
        
        # --- AUDIO FEEDBACK DICTIONARY ---
        PUNCTUATION_SPEECH = {
            '.': 'period',
            ',': 'comma',
            '?': 'question mark',
            '!': 'exclamation mark'
        }
        
        last_char = current_word[-1]
        
        if last_char == " ":
            speak_cached("Space")
        elif last_char in PUNCTUATION_SPEECH:
            speak_cached(PUNCTUATION_SPEECH[last_char]) # Speak the word, not the symbol!
        else:
            speak_cached(last_char.lower()) # Cache the pronunciation of individual letters

# --- INDUSTRIAL KEYPAD SCANNER ---
class MatrixKeypad:
    def __init__(self):
        self.ROWS = [5, 6, 13, 19]
        self.COLS = [12, 16, 20, 21]
        self.KEYS = [
            ['1', '2', '3', 'A'],
            ['4', '5', '6', 'B'],
            ['7', '8', '9', 'C'],
            ['*', '0', '#', 'D']
        ]
        
        self.custom_A_press_time = 0 # NEW: Tracks hold duration for Custom Mode

        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        for row in self.ROWS:
            GPIO.setup(row, GPIO.OUT)
            GPIO.output(row, GPIO.HIGH)
        for col in self.COLS:
            GPIO.setup(col, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        self.state = {r: {c: False for c in range(4)} for r in range(4)}
        self.debounce = {r: {c: 0 for c in range(4)} for r in range(4)}
        self.THRESHOLD = 3 

        threading.Thread(target=self._scan_loop, daemon=True).start()

    def _scan_loop(self):
        while True:
            for r_idx, row in enumerate(self.ROWS):
                GPIO.output(row, GPIO.LOW)
                for c_idx, col in enumerate(self.COLS):
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
            time.sleep(0.01) 

    def _trigger_edge(self, key, is_pressed):
        global custom_mode_active
        
        # 1. Universal immediate feedback
        if is_pressed:
            play_click()

        # 2. Route the logic based on current mode
        if not custom_mode_active:
            # Preset Mode Routing
            if key == 'A':
                if is_pressed: control_btn_A.press()
                else: control_btn_A.release()
            elif is_pressed:
                handle_preset_mode(key)
        else:
            # Custom Mode Routing
            if key == 'A':
                if is_pressed:
                    # Start the stopwatch when pressed down
                    self.custom_A_press_time = time.time()
                else:
                    # Check the stopwatch when released
                    duration = time.time() - self.custom_A_press_time
                    if duration >= 2.0:
                        handle_custom_mode('A_HOLD') # Held for 2+ seconds
                    else:
                        handle_custom_mode('A') # Short tap
            elif is_pressed:
                handle_custom_mode(key)

# --- BOOT UP ---
keypad_thread = MatrixKeypad()

try:
    socket.create_connection(("8.8.8.8", 53), timeout=2)
    is_cloud = True
except:
    is_cloud = False

announce("System Ready. Cloud Processing Active" if is_cloud else "System Ready. Edge Processing Active")
start_script()

try:
    while True: time.sleep(1)
except KeyboardInterrupt:
    if current_process: current_process.terminate()
    GPIO.cleanup()
