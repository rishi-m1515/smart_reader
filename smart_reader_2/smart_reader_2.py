import cv2
import pytesseract
import subprocess
import time

# Initialize Camera
cap = cv2.VideoCapture(0)
cap.set(3, 640)
cap.set(4, 480)

if not cap.isOpened():
    print("Error: Could not open camera.")
    exit()

def speak_better(text):
    print(f"Speaking: {text}")
    # Clean the text so special characters don't break the terminal command
    safe_text = text.replace('"', '').replace("'", "").replace('\n', ' ').strip()
    
    # Save it in the same folder as your script
    audio_file = "latest_reading.wav"
    
    # pico2wave creates the wav file, aplay plays it
    command = f'pico2wave -w {audio_file} "{safe_text}" && aplay {audio_file} 2>/dev/null'
    try:
        subprocess.run(command, shell=True)
        print(f"Saved audio to: {audio_file}")
    except Exception as e:
        print(f"Audio Error: {e}")

def clean_image_for_ocr(frame):
    """
    The Goldilocks Pipeline: Handles shadows (curved books) AND ignores noise (medicine boxes).
    """
    # 1. Grayscale
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    
    # 2. Resize (Make it 2x bigger)
    larger = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    
    # 3. Slight blur
    blur = cv2.GaussianBlur(larger, (5,5), 0)
    
    # 4. The Magic Adaptive Threshold
    # 51 = Block size (looks at a large 51x51 pixel area to figure out the lighting)
    # 15 = Constant (subtracts 15 to aggressively kill background noise/snow)
    thresh = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 51, 15)
    
    return thresh

print("--- SMART READER: EDGE PRO ---")
print("Press 's' to Scan. Press 'q' to Quit.")

while True:
    ret, frame = cap.read()
    if not ret: break

    cv2.imshow('Camera View', frame)
    key = cv2.waitKey(1) & 0xFF

    if key == ord('s'):
        print("\n--- Processing Image... ---")
        
        # Pass the image through our cleaning pipeline
        processed_img = clean_image_for_ocr(frame)
        
        # Optional: Save the cleaned image to see what Tesseract sees!
        cv2.imwrite("cleaned_vision.jpg", processed_img)
        
        # Run OCR with optimized settings
        # psm 3 = Fully automatic page segmentation
        # oem 3 = Default OCR Engine Mode
        custom_config = r'--oem 3 --psm 11'
        text = pytesseract.image_to_string(processed_img, config=custom_config)
        
        clean_text = text.strip()

        # --- THE GARBAGE FILTER ---
        final_lines = []
        # Check line by line
        for line in clean_text.split('\n'):
            line = line.strip()
            # If the line has more than 2 characters, keep it. 
            # This deletes the random "ae", "k", "|", and "-" artifacts.
            if len(line) > 2:
                final_lines.append(line)
        
        # Stitch it back together
        polished_text = "\n".join(final_lines)
        
        if polished_text:
            print(f"POLISHED OUTPUT:\n{polished_text}\n")
            speak_better(polished_text)
        else:
            print("No clear text found.")

    elif key == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()