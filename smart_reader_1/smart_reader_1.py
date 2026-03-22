import cv2
import pytesseract
import subprocess # We use this instead of pyttsx3
import time

# --- SETUP ---
# No engine.init() needed anymore!

# Initialize Camera
cap = cv2.VideoCapture(0)
cap.set(3, 640)
cap.set(4, 480)

if not cap.isOpened():
    print("Error: Could not open camera.")
    exit()

# Helper function to speak
def speak(text):
    print(f"Speaking: {text}")
    # This calls the espeak command directly from the system
    # --stdout | aplay pipes the audio directly to the speakers
    subprocess.call(f'espeak "{text}" --stdout | aplay 2>/dev/null', shell=True)

print("SYSTEM READY.")
print("Press 's' to Scan and Speak.")
print("Press 'q' to Quit.")

while True:
    ret, frame = cap.read()
    if not ret:
        print("Failed to grab frame")
        break

    cv2.imshow('Smart Reader View', frame)
    key = cv2.waitKey(1) & 0xFF

    # --- ACTION: SCAN TEXT ---
    if key == ord('s'):
        print("\n--- Capturing Image... ---")
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Run OCR
        custom_config = r'--oem 3 --psm 6' 
        text = pytesseract.image_to_string(gray, config=custom_config)
        clean_text = text.strip()
        
        if len(clean_text) > 2:
            print(f"DETECTED: {clean_text}")
            speak(clean_text) # Use our new function
            print("Done.")
        else:
            print("No clear text found. Try holding it steady.")

    elif key == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
