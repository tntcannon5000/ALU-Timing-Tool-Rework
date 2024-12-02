import dxcam
from src.utils.windowtools import fuzzy_window_search, calculate_aspect_ratio, check_aspect_ratio_validity
import matplotlib.pyplot as plt
import pytesseract
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
import numpy as np
import cv2
import tkinter as tk
import threading
import time as systime

# Global vars
camera = dxcam.create()
capturing = True
time = 0

coords = fuzzy_window_search("asphalt")

aspect_ratio = calculate_aspect_ratio(coords)

check_aspect_ratio_validity(aspect_ratio)
print(coords)

# Grab a frame from the camera

camera.start(region=coords, target_fps=90)

def start_capturing():
    global capturing
    capturing = True
    print("Capturing started")

def stop_capturing():
    global capturing
    capturing = False
    print("Capturing stopped")

def update_time_label():
    global time
    while True:
        time_label.config(text=time)
        time_label.update()
        systime.sleep(0.15)

def create_ui():
    root = tk.Tk()
    root.title("Capture Control")

    start_button = tk.Button(root, text="Start", command=start_capturing, bg="green", fg="white", font=("Helvetica", 16))
    start_button.pack(pady=10)

    stop_button = tk.Button(root, text="Stop", command=stop_capturing, bg="red", fg="white", font=("Helvetica", 16))
    stop_button.pack(pady=10)

    global time_label
    time_label = tk.Label(root, text=f"Time: {time}", font=("Helvetica", 14))
    time_label.pack(pady=10)

    threading.Thread(target=update_time_label, daemon=True).start()

    root.mainloop()

# ui_thread = threading.Thread(target=create_ui)
# ui_thread.start()


# Target BGR values - easy to adjust
target_B = 228
target_G = 0
target_R = 0
tolerance = 1

while True:
    if capturing:
        window = camera.get_latest_frame()
        # First crop to top-right region
        height, width, _ = window.shape
        top_right_region = window[0:int(height*0.28), int(width*0.6):width]
        print(top_right_region)

        # Create mask looking for the target color with tolerance
        mask = np.zeros(top_right_region.shape[:2], dtype=np.uint8)
        mask[
            (top_right_region[:,:,0] >= max(0, target_B - tolerance)) & 
            (top_right_region[:,:,0] <= min(255, target_B + tolerance)) &  # Blue channel
            (top_right_region[:,:,1] >= max(0, target_G - tolerance)) & 
            (top_right_region[:,:,1] <= min(255, target_G + tolerance)) &  # Green channel
            (top_right_region[:,:,2] >= max(0, target_R - tolerance)) & 
            (top_right_region[:,:,2] <= min(255, target_R + tolerance))  # Red channel
        ] = 255

            # Display the frame
        plt.imshow(mask)
        plt.axis('off')  # Hide the axis
        plt.show()

        # Find contours in the mask
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if contours:
            # Find the largest contour
            largest_contour = max(contours, key=cv2.contourArea)
            x, y, w, h = cv2.boundingRect(largest_contour)
            
            # Extract the region within the box
            box_region = top_right_region[y:y+h, x:x+w]
            
            # Convert to grayscale and extract text
            gray_region = cv2.cvtColor(box_region, cv2.COLOR_BGR2GRAY)
            text = pytesseract.image_to_string(gray_region, config='--psm 6')
            
            # Extract numbers while preserving time format
            numbers = ''.join(filter(str.isdigit, text))
            numbers = numbers[-7:] if len(numbers) >= 7 else numbers
            print("Extracted time:", numbers)
            #print(f"Number of contours found: {len(contours)}")
        else:
            print("No contours found")
    systime.sleep(0.2)