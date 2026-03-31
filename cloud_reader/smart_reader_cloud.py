import os
import cv2
import time
import subprocess
import pygame
from google import genai
from PIL import Image
from dotenv import load_dotenv, find_dotenv

# AUTO-DETECT GUI
HAS_DISPLAY = bool(os.environ.get('DISPLAY'))
TRIGGER_FILE = "/tmp/scan.trigger"

# Setup[cite: 7]
load_dotenv(find_dotenv())
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
client = genai.Client(api_key=GOOGLE_API_KEY)

cap = cv2.VideoCapture(0)
cap.set(3, 640)
cap.set(4, 480)

try:
    pygame.mixer.init()
except Exception as e:
    print("Audio init warning:", e)

def play_audio(filename):
    try:
        pygame.mixer.music.load(filename)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            time.sleep(0.1)
        pygame.mixer.music.unload()
    except Exception as e:
        pass

def speak_online(text):
    print(f"Speaking: {text}")
    output_file = "cloud_reading.mp3" 
    # Point directly to the edge-tts program inside your virtual environment
    EDGE_TTS_BIN = "/home/rishi/smart_reader/env/bin/edge-tts"
    command = f'{EDGE_TTS_BIN} --text "{text}" --write-media {output_file} --voice en-IN-NeerjaNeural'
    try:
        subprocess.run(command, shell=True, check=True)
        play_audio(output_file)
    except Exception as e:
        print(f"TTS Error: {e}")

def analyze_image_with_ai(image_path):
    print("Sending to Google AI...")
    try:
        pil_image = Image.open(image_path)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=["Read the text in this image. Join sentences together fluidly into paragraphs. Do not include line breaks just because the text wraps to the next line in the physical image. Only use line breaks for actual new paragraphs. If there is no text, say 'No text found'. Do not explain, just read.", pil_image]
        )
        return response.text
    except Exception as e:
        return f"AI Error: {e}"

print(f"--- SMART READER ULTIMATE (GUI Mode: {HAS_DISPLAY}) ---")

while True:
    ret, frame = cap.read()
    if not ret: break

    key = None
    do_scan = False

    if HAS_DISPLAY:
        try:
            cv2.imshow('Cloud AI View', frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord('s'):
                do_scan = True
        except cv2.error:
            HAS_DISPLAY = False
    else:
        time.sleep(0.05)

    if os.path.exists(TRIGGER_FILE):
        os.remove(TRIGGER_FILE)
        do_scan = True

    if do_scan:
        print("\n--- Snap! ---")
        img_name = "cloud_vision.jpg"
        cv2.imwrite(img_name, frame)
        text = analyze_image_with_ai(img_name)
        clean_text = text.replace("*", "").replace("â€“", "-").replace("-\n", "").strip()
        print(f"\nAI READ:\n{clean_text}\n")
        if clean_text and "No text found" not in clean_text:
            speak_online(clean_text)

    if key is not None and key == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()