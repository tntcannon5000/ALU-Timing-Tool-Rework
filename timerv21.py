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
camera = dxcam.create(device_idx=0)
capturing = False
time = 0

coords = fuzzy_window_search("asphalt")

aspect_ratio = calculate_aspect_ratio(coords)

check_aspect_ratio_validity(aspect_ratio)
print(coords)

window = camera.grab()

# Extract coordinates from the coords variable
x1, y1, x2, y2 = coords

capture_coords = (x1, y1, x2, int(y1 + (y2 - y1) / 3.4))

camera.start(region=capture_coords, target_fps=90)

# # Calculate the top-right region based on the coords
# top_right_region = window[y1:int(y1 + (y2 - y1) * 0.28), int(x2 - (x2 - x1) * 0.4):x2]

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


def find_time_region():
    # Target BGR values
    target_B, target_G, target_R = 228, 0, 0
    tolerance = 5
    
    window = camera.get_latest_frame()

    plt.imshow(window)
    plt.axis('off')  # Hide the axis
    plt.show()
    if window is None:
        return None
    
    

    # Create mask for the target color
    mask = np.zeros(window.shape[:2], dtype=np.uint8)
    mask[
        (window[:,:,0] >= max(0, target_B - tolerance)) & 
        (window[:,:,0] <= min(255, target_B + tolerance)) &  # Blue channel
        (window[:,:,1] >= max(0, target_G - tolerance)) & 
        (window[:,:,1] <= min(255, target_G + tolerance)) &  # Green channel
        (window[:,:,2] >= max(0, target_R - tolerance)) & 
        (window[:,:,2] <= min(255, target_R + tolerance))  # Red channel
    ] = 255
    
    # # Display the frame
    # plt.imshow(mask)
    # plt.axis('off')  # Hide the axis
    # plt.show()

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if contours:
        largest_contour = max(contours, key=cv2.contourArea)
        x, y, w, h = cv2.boundingRect(largest_contour)
        return (x, y, w, h)
    return None


def define_percent_region():
    window = camera.get_latest_frame()
    if window is None:
        return None
    
    x1, y1, x2, y2 = coords
    x2 = x1 + (x2 - x1) // 4

    percent_region = x1, y1, x2, y2

    return percent_region
    
percent_region = define_percent_region()


def get_current_percent():
    x1, y1, x2, y2 = percent_region
    print(f"x1: {x1}, y1: {y1}, x2: {x2}, y2: {y2}")
    frame = camera.get_latest_frame()
    percent_frame = frame[y1:y2, x1:x2]
    plt.imshow(percent_frame)
    plt.axis('off')  # Hide the axis
    plt.show()
    

    # Convert to grayscale and extract text
    gray_frame = cv2.cvtColor(percent_frame, cv2.COLOR_BGR2GRAY)
    text = pytesseract.image_to_string(gray_frame, config='--psm 6')
    return text

print(get_current_percent())

timer_rect = find_time_region()
x, y, w, h = timer_rect


while True:
    if capturing:
        

        
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
    systime.sleep(0.2)


