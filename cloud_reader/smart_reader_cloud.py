import os
import cv2
import time
import subprocess
import pygame
import threading # NEW: For non-blocking beeps
from google import genai
from PIL import Image
from dotenv import load_dotenv, find_dotenv

HAS_DISPLAY = bool(os.environ.get('DISPLAY'))
TRIGGER_FILE = "/tmp/scan.trigger"
BEEP_SOUND = "/home/rishi/smart_reader/beep.wav"

load_dotenv(find_dotenv())
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
client = genai.Client(api_key=GOOGLE_API_KEY)

cap = cv2.VideoCapture(0)
cap.set(3, 640)
cap.set(4, 480)
pygame.mixer.init()

# --- BEEP LOGIC ---
is_processing = False

def beep_loop():
    """Plays a beep every 1.5 seconds while processing."""
    while is_processing:
        if os.path.exists(BEEP_SOUND):
            subprocess.run(['aplay', BEEP_SOUND, '-q'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1.5)

def play_audio(filename):
    try:
        pygame.mixer.music.load(filename)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            time.sleep(0.1)
        pygame.mixer.music.unload()
    except: pass

def speak_online(text):
    print(f"Speaking: {text}")
    output_file = "cloud_reading.mp3" 
    EDGE_TTS_BIN = "/home/rishi/smart_reader/env/bin/edge-tts"
    command = f'{EDGE_TTS_BIN} --text "{text}" --write-media {output_file} --voice en-IN-NeerjaNeural'
    try:
        subprocess.run(command, shell=True, check=True)
        play_audio(output_file)
    except Exception as e:
        print(f"TTS Error: {e}")

def analyze_image_with_ai(image_path):
    global is_processing
    is_processing = True
    # Start the beep thread
    threading.Thread(target=beep_loop, daemon=True).start()
    
    print("Sending to Google AI (Concise Mode)...")
    try:
        pil_image = Image.open(image_path)
        
        # TO THE POINT PROMPT
        # We use a "Strict Instruction" style to minimize output tokens.
        prompt = (
            "Read all text in the image exactly. "
            "If it's a specific object (e.g., medicine, food), name it in 3 words or less. "
            "If no text exists, describe the scene in one short sentence. "
            "Be extremely brief. No introductory remarks or conversational filler."
        )

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[prompt, pil_image]
        )
        
        is_processing = False 
        return response.text
    except Exception as e:
        is_processing = False
        return f"AI Error: {e}"

while True:
    ret, frame = cap.read()
    if not ret: break
    key = None
    do_scan = False

    if HAS_DISPLAY:
        try:
            cv2.imshow('Cloud AI View', frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord('s'): do_scan = True
        except: HAS_DISPLAY = False
    else:
        time.sleep(0.05)

    if os.path.exists(TRIGGER_FILE):
        os.remove(TRIGGER_FILE)
        do_scan = True

    if do_scan:
        img_name = "cloud_vision.jpg"
        cv2.imwrite(img_name, frame)
        text = analyze_image_with_ai(img_name)
        clean_text = text.replace("*", "").replace("â€“", "-").replace("-\n", "").strip()
        if clean_text and "No text found" not in clean_text:
            speak_online(clean_text)

    if key == ord('q'): break

cap.release()
cv2.destroyAllWindows()