import cv2
import time
import subprocess
import os
import pygame
from google import genai
from PIL import Image

# NEW: Import dotenv
from dotenv import load_dotenv, find_dotenv

# --- CONFIGURATION ---
# find_dotenv() automatically searches up the folder tree to find your .env file
load_dotenv(find_dotenv())

# Grab the key securely from the environment
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

if not GOOGLE_API_KEY:
    print("CRITICAL ERROR: Google API Key not found. Please check your .env file.")
    exit()

# Setup the new 2026 Google Client
client = genai.Client(api_key=GOOGLE_API_KEY)

# Initialize Camera
cap = cv2.VideoCapture(0)
cap.set(3, 640)
cap.set(4, 480)

# Initialize Audio Player
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
        print(f"Audio Playback Error: {e}")

def speak_online(text):
    print(f"Speaking: {text}")
    
    # NEW: Distinct audio file for the Cloud version
    output_file = "cloud_reading.mp3" 
    
    command = f'edge-tts --text "{text}" --write-media {output_file} --voice en-IN-NeerjaNeural'
    # ... rest of the function stays the same
    
    try:
        subprocess.run(command, shell=True, check=True)
        print(f"Saved audio to: {output_file}")
        play_audio(output_file)
    except Exception as e:
        print(f"TTS Error: {e}")

def analyze_image_with_ai(image_path):
    print("Sending to Google AI...")
    try:
        # Load image with Pillow (Required for the new 2026 GenAI library)
        pil_image = Image.open(image_path)

        # Using the new 2.5 Flash model
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                "Read the text in this image exactly as it appears. If there is no text, say 'No text found'. Do not explain, just read.",
                pil_image
            ]
        )
        return response.text
    except Exception as e:
        return f"AI Error: {e}"

print("--- SMART READER ULTIMATE (CLOUD AI) ---")
print("Press 's' to Scan. Press 'q' to Quit.")

while True:
    ret, frame = cap.read()
    if not ret: break

    cv2.imshow('Cloud AI View', frame)
    key = cv2.waitKey(1) & 0xFF

    if key == ord('s'):
        print("\n--- Snap! ---")
        img_name = "cloud_vision.jpg"
        cv2.imwrite(img_name, frame)
        
        # 1. Vision (Gemini 2.5)
        text = analyze_image_with_ai(img_name)
        
        # Clean up Markdown artifacts AI sometimes adds
        clean_text = text.replace("*", "").strip()
        print(f"\nAI READ:\n{clean_text}\n")
        
        # 2. Voice (Edge TTS Neural)
        if clean_text and "No text found" not in clean_text:
            speak_online(clean_text)

    elif key == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()