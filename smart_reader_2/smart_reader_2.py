import cv2
import pytesseract
import subprocess
import time
import os

# AUTO-DETECT GUI: True if a monitor/VNC is active, False if headless
HAS_DISPLAY = bool(os.environ.get('DISPLAY'))
TRIGGER_FILE = "/tmp/scan.trigger"

# Initialize Camera[cite: 6]
cap = cv2.VideoCapture(0)
cap.set(3, 640)
cap.set(4, 480)

if not cap.isOpened():
    print("Error: Could not open camera.")
    exit()

def speak_better(text):
    # Your original speak function[cite: 6]
    print(f"Speaking: {text}")
    safe_text = text.replace('"', '').replace("'", "").replace('\n', ' ').strip()
    audio_file = "latest_reading.wav"
    command = f'pico2wave -w {audio_file} "{safe_text}" && aplay {audio_file} 2>/dev/null'
    try:
        subprocess.run(command, shell=True)
    except Exception as e:
        print(f"Audio Error: {e}")

def clean_image_for_ocr(frame):
    # Your original image filter[cite: 6]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    larger = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    blur = cv2.GaussianBlur(larger, (5,5), 0)
    thresh = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 51, 15)
    return thresh

print(f"--- SMART READER: EDGE PRO (GUI Mode: {HAS_DISPLAY}) ---")

while True:
    ret, frame = cap.read()
    if not ret: break

    key = None
    do_scan = False

    # 1. Check for GUI Keyboard Input
    if HAS_DISPLAY:
        try:
            cv2.imshow('Edge Camera View', frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord('s'):
                do_scan = True
        except cv2.error:
            HAS_DISPLAY = False # Fallback if GUI crashes
    else:
        time.sleep(0.05) # Save CPU when headless

    # 2. Check for Physical Button Input
    if os.path.exists(TRIGGER_FILE):
        os.remove(TRIGGER_FILE)
        do_scan = True

    # 3. Execute Scan[cite: 6]
    if do_scan:
        print("\n--- Processing Image... ---")
        processed_img = clean_image_for_ocr(frame)
        cv2.imwrite("cleaned_vision.jpg", processed_img)
        text = pytesseract.image_to_string(processed_img, config=r'--oem 3 --psm 11')
        clean_text = text.strip()

        final_lines = [line.strip() for line in clean_text.split('\n') if len(line.strip()) > 2]
        polished_text = "\n".join(final_lines)
        
        if polished_text:
            print(f"POLISHED OUTPUT:\n{polished_text}\n")
            speak_better(polished_text)
        else:
            print("No clear text found.")

    if key is not None and key == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()