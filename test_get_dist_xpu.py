import os
#os.environ["PYTORCH_ENABLE_XPU_FALLBACK"] = "1"
import dxcam_cpp as dxcam
from src.utils.windowtools import (
    fuzzy_window_search,
    calculate_aspect_ratio,
    check_aspect_ratio_validity,
    get_monitor_number_from_coords,
    normalise_coords_to_monitor
)
from src.utils.helpers import (
    pre_process,
    pre_process_distbox,
)
from src.utils.gpu import get_easyocr_reader_xpu
#import matplotlib.pyplot as plt
#import line_profiler
import numpy as np
import tkinter as tk
import threading
import time as systime
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())

os.environ["LINE_PROFILE"] = "1"
os.environ["PYTORCH_ENABLE_XPU_FALLBACK"] = "1"

coords = fuzzy_window_search("asphalt")

monitor_id = get_monitor_number_from_coords(coords)

normalised_coords = normalise_coords_to_monitor(coords, monitor_id)

aspect_ratio = calculate_aspect_ratio(normalised_coords)

check_aspect_ratio_validity(aspect_ratio)
print(coords)

# Global vars
camera = dxcam.create(device_idx=0, output_idx=monitor_id)
capturing = True
time = 0
elapsed_ms = 0
percentage = 0

reader = get_easyocr_reader_xpu(languages=['en'])

# Grab a frame from the camera
window = camera.grab()

# Extract coordinates from the coords variable
x1, y1, x2, y2 = normalised_coords

capture_coords = (x1, y1, x2, int(y1 + (y2 - y1) / 3.4))

camera.start(region=capture_coords, target_fps=90)

def start_capturing():
    global capturing
    capturing = True
    print("Capturing started")

def stop_capturing():
    global capturing
    capturing = False
    print("Capturing stopped")

def update_time_label():
    time_label.config(text=f"Time: {time}")
    elapsed_label.config(text=f"Elapsed: {elapsed_ms:.2f} ms")
    percentage_label.config(text=f"Percentage: {percentage}")
    # Schedule the next update in 100 ms
    time_label.after(100, update_time_label)

def create_ui():
    global time_label, elapsed_label, percentage_label
    root = tk.Tk()
    root.title("Capture Control")

    start_button = tk.Button(root, text="Start", command=start_capturing, bg="green", fg="white", font=("Helvetica", 16))
    start_button.pack(pady=10)

    stop_button = tk.Button(root, text="Stop", command=stop_capturing, bg="red", fg="white", font=("Helvetica", 16))
    stop_button.pack(pady=10)

    time_label = tk.Label(root, text=f"Time: {time}", font=("Helvetica", 14))
    time_label.pack(pady=10)

    elapsed_label = tk.Label(root, text=f"Elapsed: {elapsed_ms:.2f} ms", font=("Helvetica", 14))
    elapsed_label.pack(pady=10)

    percentage_label = tk.Label(root, text=f"Percentage: {percentage}", font=("Helvetica", 14))
    percentage_label.pack(pady=10)

    # Start periodic UI updates in the main thread
    update_time_label()

    root.mainloop()
# ...existing code...





#from IPython.display import clear_output
textarray = []
dist_box = None


#@line_profiler.profile
def the_loop():
    global dist_box
    global capturing
    global textarray
    global reader
    global camera
    global percentage
    global elapsed_ms

        # Start the loop
    while capturing:
        if capturing:
            start_time = systime.perf_counter()
            window = camera.get_latest_frame()
            height, width, _ = window.shape
            top_right_region = window[50:height, 0:int(width * 0.35)]

            if dist_box is None:
                print("No bounding box found, searching for DIST...")
                print("No bounding box found, searching for DIST...")
                preprocessed_region = pre_process(top_right_region)

                results = reader.readtext(preprocessed_region)
                
                for i, (bbox, text, _) in enumerate(results):
                    if "dist" in text.lower():
                        # Get bbox of "DIST"
                        dist_box = np.array(bbox)
                        x0, y0 = np.min(dist_box[:, 0]), np.min(dist_box[:, 1])
                        x1, y1 = np.max(dist_box[:, 0]), np.max(dist_box[:, 1])

                        # Look for a % or 7 to the right on the same line
                        for j in range(i + 1, len(results)):
                            next_bbox, next_text, _ = results[j]
                            next_box = np.array(next_bbox)
                            nx0, ny0 = np.min(next_box[:, 0]), np.min(next_box[:, 1])
                            nx1, ny1 = np.max(next_box[:, 0]), np.max(next_box[:, 1])

                            # Check if next box is horizontally aligned and to the right
                            same_line = abs(ny0 - y0) < 20  # small y-difference = same line
                            right_of_dist = nx0 > x1
                            ends_correctly = next_text.strip().endswith('%') or next_text.strip().endswith('7')

                            if same_line and right_of_dist and ends_correctly:
                                # Extend bounding box to include both
                                x0 = int(min(x0, nx0))
                                y0 = int(min(y0, ny0))
                                x1 = int(max(x1, nx1))
                                y1 = int(max(y1, ny1))
                                break  # only extend to first match

                        # # imshow the boxed image
                        # plt.imshow(boxed)
                        # plt.axis('off')
                        # plt.title('DIST to % box')
                        # plt.show()

                        # Return coordinates of the bounding box
                        dist_box = np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]])
                        break  # only do once per frame
            

            #clear_output(wait=False)

            # run clear in terminal
            #os.system('cls' if os.name == 'nt' else 'clear')  # Windows: cls, Unix/Linux/macOS: clear
            #os.system('cls')
            # If we have the bounding box, crop the image
            if dist_box is not None:
                roi = top_right_region[int(dist_box[0][1]):int(dist_box[2][1]), int(dist_box[0][0]):int(dist_box[1][0])]
                roi = roi[:, int(roi.shape[1] * 23 / 40):]

                

                # Preprocess the cropped image
                preprocessed_region = pre_process_distbox(roi)
                # imshow the cropped image
                # plt.imshow(preprocessed_region, cmap='gray')
                # plt.axis('off')
                # plt.title('Cropped image')
                # plt.show()

                #textxdddd = pytesseract.image_to_string(preprocessed_region, config=config)

                textxdddd = reader.recognize(preprocessed_region, detail=0, allowlist='0123456789%')
                print(textxdddd)

            # Append text to a single string
            try:
                text2 = ''.join(textxdddd).replace(" ", "")
                # store text in an array
                percentage = text2.strip()
                textxdddd = ""

                if not text2:
                    dist_box = None
                    print("No DIST found in text, resetting bounding box.")
            except Exception as e:
                dist_box = None
            text2 = ""
            end_time = systime.perf_counter()    # End timing
            elapsed_ms = (end_time - start_time) * 1000
            print(f"Loop iteration took {elapsed_ms:.2f} ms")

            systime.sleep(0.2)

if __name__ == "__main__":

    #ui_thread = threading.Thread(target=create_ui)
    #ui_thread.start()
    the_loop()