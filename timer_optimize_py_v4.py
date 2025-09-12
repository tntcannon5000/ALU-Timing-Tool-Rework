"""
Main Timer Application

This module contains the main application logic for the ALU Timing Tool.
"""

import dxcam_cpp as dxcam
import numpy as np
import cv2
import time as systime
from easyocr import Reader
from typing import Optional, List

from src.utils.helpers import (
    pre_process,
    pre_process_distbox,
    setup_window_capture
)
from src.modules import (
    TimerRecognizer,
    ImageProcessor,
    CNNPredictor,
    TimingToolUI
)


class ALUTimingTool:
    """
    Main application class for the ALU Timing Tool.
    """
    
    def __init__(self, window_name: str = "asphalt", confidence_threshold: float = 0.65):
        """
        Initialize the ALU Timing Tool.
        
        Args:
            window_name: Name of the window to capture
            confidence_threshold: CNN confidence threshold
        """
        self.window_name = window_name
        self.confidence_threshold = confidence_threshold
        
        # Initialize components
        self.timer_recognizer = TimerRecognizer()
        self.image_processor = ImageProcessor()
        self.cnn_predictor = CNNPredictor(confidence_threshold)
        self.ui = TimingToolUI()
        
        # Camera and capture setup
        self.camera = None
        self.capture_coords = None
        self.monitor_id = None
        
        # OCR reader
        self.reader = Reader(['en'], gpu=True)
        
        # State variables
        self.capturing = True
        self.dist_box = None
        self.timer_roi_coords = None
        self.last_percentage = None
        self.current_timer = None
        self.current_timer_ms = 0
        self.current_timer_display = "00:00.000"
        self.percentage = "0%"
        
        # Performance tracking
        self.loop_times: List[float] = []
        self.avg_loop_time = 0.0
        self.total_loops = 0
        
        # Setup window capture
        self._setup_capture()
        
        # Start UI
        self.ui_thread = self.ui.start_ui_thread()
    
    def _setup_capture(self):
        """Setup window capture and camera."""
        print("Setting up window capture...")
        
        # Setup window capture
        coords, self.monitor_id, normalised_coords, aspect_ratio, self.capture_coords = setup_window_capture(self.window_name)
        
        print(f"Window found at: {coords}")
        print(f"Monitor ID: {self.monitor_id}")
        print(f"Normalized coords: {normalised_coords}")
        print(f"Aspect ratio: {aspect_ratio}")
        print(f"Capture coords: {self.capture_coords}")
        
        # Initialize camera
        self.camera = dxcam.create(device_idx=0, output_idx=self.monitor_id)
        
        # Test grab
        window = self.camera.grab()
        if window is None:
            raise RuntimeError("Failed to grab initial frame from camera")
        
        # Start camera with region
        self.camera.start(region=self.capture_coords, target_fps=90)
        print("Camera setup complete!")
    
    def _find_dist_bbox(self, top_right_region: np.ndarray) -> Optional[np.ndarray]:
        """
        Find the DIST bounding box in the top right region.
        
        Args:
            top_right_region: Image region to search
            
        Returns:
            Bounding box coordinates or None
        """
        preprocessed_region = pre_process(top_right_region)
        results = self.reader.readtext(preprocessed_region)
        
        dist_found = False
        dist_bbox = None
        dist_index = -1
        
        # Find DIST
        for i, (bbox, text, confidence) in enumerate(results):
            if "dist" in text.lower() and not dist_found:
                dist_bbox = np.array(bbox)
                dist_index = i
                dist_found = True
        
        # If we found DIST, look for percentage
        if dist_found:
            dist_x0, dist_y0 = np.min(dist_bbox[:, 0]), np.min(dist_bbox[:, 1])
            dist_x1, dist_y1 = np.max(dist_bbox[:, 0]), np.max(dist_bbox[:, 1])
            dist_center_y = (dist_y0 + dist_y1) / 2
            
            best_percentage_match = None
            best_score = 0
            
            # Look for percentage indicators with more flexible criteria
            for j, (bbox, text, confidence) in enumerate(results):
                if j == dist_index:  # Skip the DIST box itself
                    continue
                    
                bbox_array = np.array(bbox)
                nx0, ny0 = np.min(bbox_array[:, 0]), np.min(bbox_array[:, 1])
                nx1, ny1 = np.max(bbox_array[:, 0]), np.max(bbox_array[:, 1])
                bbox_center_y = (ny0 + ny1) / 2
                
                # More flexible matching criteria
                text_clean = text.strip().replace(' ', '').replace(',', '').replace('.', '')
                
                # Check if it looks like a percentage
                has_percent = '%' in text_clean
                has_numbers = any(char.isdigit() for char in text_clean)
                ends_with_7 = text_clean.endswith('7')  # Sometimes % is read as 7
                
                # Position criteria (more flexible)
                reasonable_y_distance = abs(bbox_center_y - dist_center_y) < 50
                to_the_right = nx0 > dist_x0
                reasonable_x_distance = (nx0 - dist_x1) < 200
                
                # Calculate a score for this match
                score = 0
                if has_percent:
                    score += 50
                if has_numbers:
                    score += 20
                if ends_with_7:
                    score += 10
                if reasonable_y_distance:
                    score += 30
                if to_the_right:
                    score += 20
                if reasonable_x_distance:
                    score += 10
                
                # Add confidence boost
                score += confidence * 10
                
                if score > best_score and score > 40:
                    best_score = score
                    best_percentage_match = (j, bbox, text, confidence)
            
            # If we found a good percentage match
            if best_percentage_match is not None:
                j, next_bbox, next_text, next_confidence = best_percentage_match
                
                # Calculate combined bounding box
                next_box = np.array(next_bbox)
                nx0, ny0 = np.min(next_box[:, 0]), np.min(next_box[:, 1])
                nx1, ny1 = np.max(next_box[:, 0]), np.max(next_box[:, 1])
                
                # Extend bounding box to include both with some padding
                x0 = int(min(dist_x0, nx0)) - 5
                y0 = int(min(dist_y0, ny0)) - 5
                x1 = int(max(dist_x1, nx1)) + 5
                y1 = int(max(dist_y1, ny1)) + 5
                
                # Ensure bounds are within image
                x0 = max(0, x0)
                y0 = max(0, y0)
                x1 = min(top_right_region.shape[1], x1)
                y1 = min(top_right_region.shape[0], y1)
            else:
                # Fallback: just use DIST box with some expansion
                x0 = int(dist_x0) - 10
                y0 = int(dist_y0) - 10
                x1 = int(dist_x1) + 100
                y1 = int(dist_y1) + 30
                
                # Ensure bounds are within image
                x0 = max(0, x0)
                y0 = max(0, y0)
                x1 = min(top_right_region.shape[1], x1)
                y1 = min(top_right_region.shape[0], y1)
            
            # Create the final bounding box
            return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]])
        
        return None
    
    def _process_cnn_prediction(self, top_right_region: np.ndarray) -> Optional[int]:
        """
        Process CNN prediction for percentage recognition.
        
        Args:
            top_right_region: Image region to analyze
            
        Returns:
            Predicted percentage value or None
        """
        if self.dist_box is None:
            return None
            
        # Extract ROI
        roi = top_right_region[int(self.dist_box[0][1]):int(self.dist_box[2][1]), 
                              int(self.dist_box[0][0]):int(self.dist_box[1][0])]
        roi = roi[:, int(roi.shape[1] * 23 / 40):]

        # Preprocess the cropped image for CNN
        preprocessed_region = pre_process_distbox(roi, for_cnn=True)

        # Prepare tensor for CNN
        tensor_image = self.image_processor.preprocess_for_cnn(preprocessed_region)

        # Use CNN for recognition
        cnn_result = self.cnn_predictor.predict(tensor_image)
        
        if cnn_result is not None:
            predicted_percentage, confidence = cnn_result
            
            # Check if percentage changed
            percentage_changed = False
            if self.last_percentage != predicted_percentage:
                percentage_changed = True
                self.last_percentage = predicted_percentage
                print(f"Percentage changed to: {predicted_percentage}%")
            
            self.percentage = f"{predicted_percentage}%"
            self.ui.update_percentage(self.percentage)

            # Reset bounding box if confidence is too low
            if not self.cnn_predictor.is_confident(confidence):
                self.dist_box = None
                
            # Update UI with inference times
            self.ui.update_inference_time(
                self.cnn_predictor.inference_times[-1] if self.cnn_predictor.inference_times else 0,
                self.cnn_predictor.avg_inference_time
            )
            
            return predicted_percentage if percentage_changed else None
        else:
            self.dist_box = None
            return None
    
    def _process_timer_if_needed(self, window: np.ndarray, percentage_changed: bool):
        """
        Process timer extraction if percentage changed.
        Retries until exactly 7 digits are detected or max retries reached.
        
        Args:
            window: Full frame
            percentage_changed: Whether percentage changed
        """
        if percentage_changed and self.timer_roi_coords is not None:
            max_retries = 5  # Maximum number of retry attempts
            retry_count = 0
            extracted_timer = None
            
            while retry_count < max_retries and extracted_timer is None:
                # Extract timer at this milestone
                timer_roi = self.image_processor.extract_timer_roi_from_coords(window, self.timer_roi_coords)
                if timer_roi is not None:
                    extracted_timer = self.image_processor.process_timer_roi(
                        timer_roi, self.timer_recognizer, self.last_percentage
                    )
                    
                    if extracted_timer is not None:
                        # Successfully extracted exactly 7 digits
                        self.current_timer = extracted_timer
                        
                        # Convert to milliseconds and update display
                        timer_ms = self.timer_recognizer.convert_to_milliseconds(extracted_timer)
                        if timer_ms is not None:
                            self.current_timer_ms = timer_ms
                            # Format for display: MM:SS.mmm
                            minutes = timer_ms // 60000
                            seconds = (timer_ms % 60000) // 1000
                            milliseconds = timer_ms % 1000
                            self.current_timer_display = f"{minutes:02d}:{seconds:02d}.{milliseconds:03d}"
                            self.ui.update_timer(self.current_timer_display)
                            
                            # Update delta display (placeholder for now)
                            # TODO: Calculate actual delta based on target time
                            self.ui.update_delta("+99.999")
                        break
                    else:
                        # Didn't get exactly 7 digits, retry
                        retry_count += 1
                        if retry_count < max_retries:
                            print(f"Retry {retry_count}/{max_retries} for timer extraction at {self.last_percentage}%")
                            # Re-find timer ROI coordinates for next attempt
                            old_timer_roi_coords = self.timer_roi_coords
                            self.timer_roi_coords = self.image_processor.find_timer_roi_coords(window)
                            # Clear digit ROI cache if timer position changed
                            if old_timer_roi_coords != self.timer_roi_coords:
                                self.timer_recognizer.clear_digit_roi_cache()
                            if self.timer_roi_coords is None:
                                print(f"Failed to find timer ROI on retry {retry_count}")
                                break
                else:
                    # Failed to extract timer ROI, retry with new coordinates
                    retry_count += 1
                    if retry_count < max_retries:
                        print(f"Retry {retry_count}/{max_retries} for timer ROI extraction at {self.last_percentage}%")
                        # Re-find timer ROI coordinates for next attempt
                        old_timer_roi_coords = self.timer_roi_coords
                        self.timer_roi_coords = self.image_processor.find_timer_roi_coords(window)
                        # Clear digit ROI cache if timer position changed
                        if old_timer_roi_coords != self.timer_roi_coords:
                            self.timer_recognizer.clear_digit_roi_cache()
                        if self.timer_roi_coords is None:
                            print(f"Failed to find timer ROI on retry {retry_count}")
                            break
            
            if extracted_timer is None:
                print(f"Failed to extract timer with exactly 7 digits after {max_retries} attempts at {self.last_percentage}%")
    
    def run_main_loop(self):
        """Run the main processing loop."""
        print("Starting main processing loop...")
        
        while self.capturing:
            if not self.capturing:
                break
                
            # Start timing the entire loop
            loop_start_time = systime.perf_counter()
            self.total_loops += 1
            
            # Get latest frame
            window = self.camera.get_latest_frame()
            if window is None:
                continue
                
            height, width, _ = window.shape
            top_right_region = window[50:height, 0:int(width * 0.35)]

            # Always update timer ROI coordinates to keep track of timer location
            if self.timer_roi_coords is None:
                self.timer_roi_coords = self.image_processor.find_timer_roi_coords(window)

            # OCR search when needed
            percentage_changed = False
            if self.dist_box is None:
                # Recalculate timer ROI coordinates when dist_box is None (re-searching for race)
                old_timer_roi_coords = self.timer_roi_coords
                self.timer_roi_coords = self.image_processor.find_timer_roi_coords(window)
                
                # Clear digit ROI cache if timer position changed
                if old_timer_roi_coords != self.timer_roi_coords:
                    self.timer_recognizer.clear_digit_roi_cache()
                
                # Find DIST bounding box
                self.dist_box = self._find_dist_bbox(top_right_region)
            
            # CNN prediction
            predicted_percentage = self._process_cnn_prediction(top_right_region)
            percentage_changed = predicted_percentage is not None
            
            # Timer extraction only when percentage changes
            self._process_timer_if_needed(window, percentage_changed)
            
            # End timing the entire loop
            loop_end_time = systime.perf_counter()
            elapsed_ms = (loop_end_time - loop_start_time) * 1000
            
            # Update loop time tracking with running average (30 samples)
            self.loop_times.append(elapsed_ms)
            if len(self.loop_times) > 30:  # Keep last 30 measurements for running average
                self.loop_times.pop(0)
            
            # Calculate new average loop time
            self.avg_loop_time = sum(self.loop_times) / len(self.loop_times)
            
            # Update UI
            self.ui.update_loop_time(elapsed_ms, self.avg_loop_time)

            systime.sleep(0.001)
    
    def stop(self):
        """Stop the application."""
        print("Stopping ALU Timing Tool...")
        self.capturing = False
        
        if self.camera:
            self.camera.stop()
        
        self.ui.close()
        print("ALU Timing Tool stopped.")
    
    def get_stats(self) -> dict:
        """
        Get application statistics.
        
        Returns:
            Dictionary with application statistics
        """
        stats = {
            'total_loops': self.total_loops,
            'avg_loop_time': self.avg_loop_time,
            'current_percentage': self.percentage,
            'current_timer': self.current_timer_display,
            'timer_ms': self.current_timer_ms
        }
        
        # Add CNN stats
        stats.update(self.cnn_predictor.get_stats())
        
        return stats
