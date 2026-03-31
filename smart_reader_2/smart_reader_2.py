import cv2
import pytesseract
import subprocess
import time
import os
import threading # NEW

HAS_DISPLAY = bool(os.environ.get('DISPLAY'))
TRIGGER_FILE = "/tmp/scan.trigger"
BEEP_SOUND = "/home/rishi/smart_reader/beep.wav"

cap = cv2.VideoCapture(0)
cap.set(3, 640)
cap.set(4, 480)

is_processing = False

def beep_loop():
    while is_processing:
        if os.path.exists(BEEP_SOUND):
            subprocess.run(['aplay', BEEP_SOUND, '-q'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1.2) # Faster beeps for Edge mode

def speak_better(text):
    safe_text = text.replace('"', '').replace("'", "").replace('\n', ' ').strip()
    audio_file = "latest_reading.wav"
    command = f'pico2wave -w {audio_file} "{safe_text}" && aplay {audio_file} 2>/dev/null'
    subprocess.run(command, shell=True)

def clean_image_for_ocr(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    larger = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    blur = cv2.GaussianBlur(larger, (5,5), 0)
    return cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 51, 15)

while True:
    ret, frame = cap.read()
    if not ret: break
    key = None
    do_scan = False

    if HAS_DISPLAY:
        try:
            cv2.imshow('Edge Camera View', frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord('s'): do_scan = True
        except: HAS_DISPLAY = False
    else:
        time.sleep(0.05)

    if os.path.exists(TRIGGER_FILE):
        os.remove(TRIGGER_FILE)
        do_scan = True

    if do_scan:
        is_processing = True
        threading.Thread(target=beep_loop, daemon=True).start()
        
        processed_img = clean_image_for_ocr(frame)
        cv2.imwrite("cleaned_vision.jpg", processed_img)
        text = pytesseract.image_to_string(processed_img, config=r'--oem 3 --psm 11')
        
        is_processing = False # Stop beeps
        
        clean_text = text.strip()
        final_lines = [line.strip() for line in clean_text.split('\n') if len(line.strip()) > 2]
        polished_text = "\n".join(final_lines)
        
        if polished_text:
            speak_better(polished_text)

    if key == ord('q'): break

cap.release()
cv2.destroyAllWindows()