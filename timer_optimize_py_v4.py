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
    TimingToolUI,
    RaceDataManager
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
        self.race_data_manager = RaceDataManager()
        self.ui = TimingToolUI(self.race_data_manager)
        
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
        self.race_completed = False
        self.max_percentage_reached = 0
        self.race_in_progress = False
        self.reached_98_percent = False
        self.reached_99_percent_capture = False
        self.at_99_percent = False
        self.last_captured_timer_ms = 0  # Store last captured timer for final time
        self.last_valid_99_percent_timer = 0  # Store last valid timer at 99%
        self.last_valid_delta = "--.---"  # Store last valid delta for display at 99%
        self.last_valid_delta = "--.---"  # Store last valid delta for display at 99%
        
        # Performance tracking
        self.loop_times: List[float] = []
        self.avg_loop_time = 0.0
        self.total_loops = 0
        
        # UI update throttling
        self.last_ui_update = 0
        self.ui_update_interval = 1.0 / 48.0  # Update UI at 48 fps (~20.8ms)
        
        # Setup window capture
        self._setup_capture()
        
        # Setup UI callbacks
        self.ui.set_callbacks(
            on_mode_change=self._on_mode_change,
            on_load_ghost=self._on_load_ghost,
            on_save_ghost=self._on_save_ghost,
            on_save_race=self._on_save_race
        )
        
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
    
    def _on_mode_change(self, mode: str):
        """Handle race mode change."""
        print(f"Race mode changed to: {mode}")
        # Allow switching to race mode without ghost - user can load ghost later
    
    def _on_load_ghost(self, filepath: str):
        """Handle loading a ghost file."""
        success = self.race_data_manager.load_ghost_data(filepath)
        if success:
            filename = self.race_data_manager.get_ghost_filename()
            self.ui.update_ghost_filename(filename)
            print(f"Loaded ghost: {filename}")
        else:
            self.ui.show_message("Error", "Failed to load ghost file. Please check the file format.", is_error=True)
    
    def _on_save_race(self, filename: str):
        """Handle saving race data."""
        success = self.race_data_manager.save_race_data(filename)
        if success:
            print(f"Saved race data: {filename}.json")
        else:
            self.ui.show_message("Error", "Failed to save race data.", is_error=True)
    
    def _on_save_ghost(self, filepath: str):
        """Handle saving current race data as ghost file."""
        success = self.race_data_manager.save_race_data(filepath.replace('.json', ''))
        if success:
            # Show temporary "Ghost Saved!" message instead of popup
            self.ui.show_ghost_saved_message()
            print(f"Saved ghost: {filepath}")
        else:
            self.ui.show_message("Error", "Failed to save ghost file. No race data available.", is_error=True)
    
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
                previous_percentage = self.last_percentage
                self.last_percentage = predicted_percentage
                print(f"Percentage changed to: {predicted_percentage}%")
                
                # Check for race completion conditions
                if predicted_percentage >= 99:
                    self.reached_98_percent = True
                if predicted_percentage >= 99:
                    if not hasattr(self, 'reached_99_percent_capture') or not self.reached_99_percent_capture:
                        self.reached_99_percent_capture = True
                        print("Reached 99% - capturing timer each loop for precise finish detection")
                
                # Track when we reach 99% for race completion detection
                if predicted_percentage == 99:
                    self.at_99_percent = True
                    print("Reached 99% - watching for timer extraction failures to detect race completion")
                elif predicted_percentage != 99:
                    self.at_99_percent = False
                
                # Race completion detection: was at 99% and now dropped
                if (previous_percentage == 99 and 
                    predicted_percentage < 99 and 
                    not self.race_completed and 
                    self.race_in_progress):
                    print(f"Race completed! Dropped from 99% to {predicted_percentage}%")
                    self._handle_race_completion()
                
                # Update max percentage reached
                if predicted_percentage > self.max_percentage_reached:
                    self.max_percentage_reached = predicted_percentage
                
                # Mark race as in progress if we have a valid percentage
                if predicted_percentage > 0 and not self.race_in_progress:
                    self.race_in_progress = True
                    print(f"Race in progress detected at {predicted_percentage}%")
            
            self.percentage = f"{predicted_percentage}%"
            
            # Throttled UI update for percentage
            current_time = systime.time()
            if current_time - self.last_ui_update >= self.ui_update_interval:
                self.ui.update_percentage(self.percentage)
                self.last_ui_update = current_time
            
            # Reset bounding box if confidence is too low
            if not self.cnn_predictor.is_confident(confidence):
                self.dist_box = None
                
            # Update UI with inference times (also throttled)
            if current_time - self.last_ui_update >= self.ui_update_interval:
                self.ui.update_inference_time(
                    self.cnn_predictor.inference_times[-1] if self.cnn_predictor.inference_times else 0,
                    self.cnn_predictor.avg_inference_time
                )
            
            return predicted_percentage if percentage_changed else None
        else:
            self.dist_box = None
            return None
    
    def _process_timer_if_needed(self, window: np.ndarray, should_extract: bool):
        """
        Process timer extraction if needed.
        Retries until exactly 7 digits are detected or max retries reached.
        
        Args:
            window: Full frame
            should_extract: Whether to extract timer (percentage changed or frequent capture mode)
        """
        if should_extract and self.timer_roi_coords is not None:
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
                            # Check for race completion: at 99% and timer goes backwards
                            if (self.at_99_percent and 
                                self.reached_98_percent and 
                                not self.race_completed and 
                                self.race_in_progress and
                                self.last_captured_timer_ms > 0 and
                                timer_ms < self.last_captured_timer_ms):
                                print(f"Race completed! At 99% and timer went backwards: {timer_ms}ms < {self.last_captured_timer_ms}ms")
                                self._handle_race_completion()
                                return  # Don't process this timer value
                            
                            self.current_timer_ms = timer_ms
                            # Store last captured timer for final time recording
                            self.last_captured_timer_ms = timer_ms
                            
                            # If we're at 99%, also store this as the last valid 99% timer
                            if self.last_percentage == 99:
                                self.last_valid_99_percent_timer = timer_ms
                            
                            # Format for display: MM:SS.mmm
                            minutes = timer_ms // 60000
                            seconds = (timer_ms % 60000) // 1000
                            milliseconds = timer_ms % 1000
                            self.current_timer_display = f"{minutes:02d}:{seconds:02d}.{milliseconds:03d}"
                            self.ui.update_timer(self.current_timer_display)
                            
                            # Record time data and update delta
                            current_mode = self.ui.get_current_mode()
                            percentage_num = int(self.last_percentage) if self.last_percentage is not None else 0
                            
                            # Only save time data if we're actually in a race
                            if self.race_in_progress:
                                self.race_data_manager.record_time_at_percentage(percentage_num, timer_ms)
                                print(f"Recorded time at {percentage_num}%: {timer_ms}ms")
                                # Update save ghost button state
                                self.ui.update_save_ghost_button_state()
                            
                            # Calculate and display delta (skip if at 99% to prevent freakouts)
                            if (current_mode == "race" and 
                                self.race_data_manager.is_ghost_loaded() and 
                                self.race_in_progress and 
                                percentage_num < 99):  # Don't calculate delta at 99%
                                delta_seconds = self.race_data_manager.calculate_delta(percentage_num, timer_ms)
                                if delta_seconds is not None:
                                    # Format delta: +/- seconds with 3 decimal places
                                    delta_sign = "+" if delta_seconds >= 0 else ""
                                    delta_str = f"{delta_sign}{delta_seconds:.3f}"
                                    self.last_valid_delta = delta_str  # Store the last valid delta
                                    self.ui.update_delta(delta_str)
                                    
                                    # Update background color based on delta
                                    self.ui.update_background_color("race", delta_seconds)
                                    
                                    print(f"Race delta at {percentage_num}%: {delta_str}s")
                                else:
                                    self.ui.update_delta("--.---")
                            elif (current_mode == "race" and 
                                  self.race_data_manager.is_ghost_loaded() and 
                                  self.race_in_progress and 
                                  percentage_num == 99):
                                # At 99%, show the last valid delta instead of calculating new one
                                self.ui.update_delta(self.last_valid_delta)
                                print(f"At 99% - showing last valid delta: {self.last_valid_delta}")
                            else:
                                # Record mode, no ghost loaded - show placeholder
                                self.ui.update_delta("--.---")
                                self.ui.update_background_color("record")
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
                
                # Check for race completion: at 99% and timer extraction fails
                if (self.at_99_percent and 
                    self.reached_98_percent and 
                    not self.race_completed and 
                    self.race_in_progress):
                    print("Race completed! At 99% and timer extraction failed - race finished")
                    self._handle_race_completion()
    
    def _handle_race_completion(self):
        """Handle race completion logic."""
        current_mode = self.ui.get_current_mode()
        if current_mode == "record" and not self.race_completed:
            self.race_completed = True
            
            # Record final time at 100% using the best available timer
            final_time = self.last_captured_timer_ms
            # Use the last valid 99% timer if it's higher than the last captured timer
            if (self.last_valid_99_percent_timer > 0 and 
                self.last_valid_99_percent_timer > final_time):
                final_time = self.last_valid_99_percent_timer
                print(f"Using last valid 99% timer ({final_time}ms) instead of last captured timer ({self.last_captured_timer_ms}ms)")
            
            if final_time > 0:
                self.race_data_manager.record_final_time(final_time)
            
            print("Race completed! Prompting to save race data...")
            
            # Prompt to save race data in a separate thread to avoid blocking the main loop
            import threading
            def prompt_save():
                import time
                time.sleep(1)  # Small delay to ensure UI is ready
                self.ui.prompt_save_race()
            
            threading.Thread(target=prompt_save, daemon=True).start()
        elif current_mode == "race":
            self.race_completed = True
            
            # Record final time for race mode too using the best available timer
            final_time = self.last_captured_timer_ms
            # Use the last valid 99% timer if it's higher than the last captured timer
            if (self.last_valid_99_percent_timer > 0 and 
                self.last_valid_99_percent_timer > final_time):
                final_time = self.last_valid_99_percent_timer
                print(f"Using last valid 99% timer ({final_time}ms) instead of last captured timer ({self.last_captured_timer_ms}ms)")
            
            if final_time > 0:
                self.race_data_manager.record_final_time(final_time)
            
            print("Race completed in race mode! Prompting to save new ghost...")
            
            # Prompt to save race data in race mode as well
            import threading
            def prompt_save():
                import time
                time.sleep(1)  # Small delay to ensure UI is ready
                self.ui.prompt_save_race()
            
            threading.Thread(target=prompt_save, daemon=True).start()
    
    def _handle_race_end(self):
        """Handle when race ends (dist_box becomes None)."""
        if self.race_in_progress:
            current_mode = self.ui.get_current_mode()
            
            # If we reached 98%+ and then dist_box became None, this is race completion
            if self.reached_98_percent and not self.race_completed:
                print("Race completed! Reached 98%+ and then exited to menus")
                self._handle_race_completion()
            
            # Reset race tracking state but keep the data
            self.race_in_progress = False
            print("Race ended - returned to menus")
    
    def _handle_potential_race_start(self):
        """Handle potential start of a new race."""
        # Reset race completion flags but keep data until we're sure it's a new race
        if self.race_completed:
            print("Potential new race detected after completion - resetting race state")
            self.reset_race_state()
    
    def reset_race_state(self):
        """Reset race state for a new race."""
        self.race_completed = False
        self.max_percentage_reached = 0
        self.race_in_progress = False
        self.reached_98_percent = False
        self.reached_99_percent_capture = False
        self.at_99_percent = False
        self.last_captured_timer_ms = 0
        self.last_valid_99_percent_timer = 0
        self.last_valid_delta = "--.---"
        self.race_data_manager.reset_race_data()
        # Update save ghost button state after reset
        self.ui.update_save_ghost_button_state()
        print("Race state reset for new race")
    
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
                # dist_box is None - race not in progress (menus, etc.)
                if self.race_in_progress:
                    print("Race ended - dist_box became None (likely in menus)")
                    self._handle_race_end()
                
                # Recalculate timer ROI coordinates when dist_box is None (re-searching for race)
                old_timer_roi_coords = self.timer_roi_coords
                self.timer_roi_coords = self.image_processor.find_timer_roi_coords(window)
                
                # Clear digit ROI cache if timer position changed
                if old_timer_roi_coords != self.timer_roi_coords:
                    self.timer_recognizer.clear_digit_roi_cache()
                
                # Find DIST bounding box
                self.dist_box = self._find_dist_bbox(top_right_region)
                
                # If we found dist_box again, we might be starting a new race
                if self.dist_box is not None and not self.race_in_progress:
                    print("Potential race start detected - dist_box found")
                    self._handle_potential_race_start()
            
            # CNN prediction
            predicted_percentage = self._process_cnn_prediction(top_right_region)
            percentage_changed = predicted_percentage is not None
            
            # Timer extraction - capture every loop when above 99%, otherwise only when percentage changes
            force_timer_capture = self.reached_99_percent_capture and self.last_percentage >= 99
            self._process_timer_if_needed(window, percentage_changed or force_timer_capture)
            
            # If dist_box is None (not in race), ensure we show placeholder
            if self.dist_box is None:
                self.ui.update_delta("--.---")
                self.ui.update_background_color("record")
            
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
            'timer_ms': self.current_timer_ms,
            'race_in_progress': self.race_in_progress,
            'race_completed': self.race_completed,
            'max_percentage_reached': self.max_percentage_reached,
            'reached_98_percent': self.reached_98_percent,
            'race_mode': self.ui.get_current_mode() if self.ui else 'record',
            'ghost_loaded': self.race_data_manager.is_ghost_loaded(),
            'ghost_filename': self.race_data_manager.get_ghost_filename()
        }
        
        # Add CNN stats
        stats.update(self.cnn_predictor.get_stats())
        
        return stats
