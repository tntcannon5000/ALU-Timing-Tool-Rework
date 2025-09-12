"""
Image Processing Module

This module handles image processing tasks for timer and distance detection.
"""

import cv2
import numpy as np
from typing import Optional, Dict
from PIL import Image
import torch
from torchvision import transforms


class ImageProcessor:
    """
    Image processor for timer and distance detection.
    """
    
    def __init__(self):
        """Initialize the image processor."""
        self.data_transforms = transforms.Compose([
            transforms.Resize((64, 64)),
            transforms.Grayscale(),
            transforms.ToTensor(),
            transforms.Normalize((0.5,), (0.5,))
        ])
    
    def find_timer_roi_coords(self, frame: np.ndarray) -> Optional[Dict[str, int]]:
        """
        Find timer ROI coordinates using the blue mask (BGR 228,0,0).
        
        Args:
            frame: Input frame
            
        Returns:
            Dictionary with timer ROI coordinates or None
        """
        # Crop to right half of the original frame
        height, width = frame.shape[:2]
        right_half = frame[:, int(width * 0.5):]
        right_half_offset = int(width * 0.5)
        
        # Create blue mask (BGR 228,0,0) with tolerance
        tolerance = 30
        target_bgr = np.array([228, 0, 0])
        lower_bgr = np.maximum(target_bgr - tolerance, 0)
        upper_bgr = np.minimum(target_bgr + tolerance, 255)
        blue_mask = cv2.inRange(right_half, lower_bgr, upper_bgr)
        
        # Find contours in the blue mask
        contours, _ = cv2.findContours(blue_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if contours:
            # Find the largest contour (should be the timer box)
            largest_contour = max(contours, key=cv2.contourArea)
            x, y, w, h = cv2.boundingRect(largest_contour)
            area = cv2.contourArea(largest_contour)
            
            # Validate size (timer should be reasonably sized)
            if w > 50 and h > 20 and area > 1000:
                # No padding
                x = max(0, x)
                y = max(0, y)
                w = min(right_half.shape[1] - x, w)
                h = min(right_half.shape[0] - y, h)
                
                # Crop 10% from the left side
                crop_left = int(w * 0.2)
                
                # Return coordinates relative to the full frame
                return {
                    'x': x + right_half_offset + crop_left,
                    'y': y,
                    'w': w - crop_left,
                    'h': h
                }
        
        return None
    
    def extract_timer_roi_from_coords(self, frame: np.ndarray, coords: Dict[str, int]) -> Optional[np.ndarray]:
        """
        Extract timer ROI using cached coordinates.
        
        Args:
            frame: Input frame
            coords: Timer ROI coordinates
            
        Returns:
            Grayscale image with white background and black text, or None
        """
        if coords is None:
            return None
        
        # Crop to right half of the original frame
        height, width = frame.shape[:2]
        right_half = frame[:, int(width * 0.5):]
        
        # Create blue mask (BGR 228,0,0) with tolerance
        tolerance = 30
        target_bgr = np.array([228, 0, 0])
        lower_bgr = np.maximum(target_bgr - tolerance, 0)
        upper_bgr = np.minimum(target_bgr + tolerance, 255)
        blue_mask = cv2.inRange(right_half, lower_bgr, upper_bgr)
        
        # Calculate coordinates relative to right_half
        right_half_offset = int(width * 0.5)
        rel_x = coords['x'] - right_half_offset
        rel_y = coords['y']
        rel_w = coords['w']
        rel_h = coords['h']
        
        # Ensure coordinates are within bounds
        rel_x = max(0, min(rel_x, right_half.shape[1] - 1))
        rel_y = max(0, min(rel_y, right_half.shape[0] - 1))
        rel_w = min(rel_w, right_half.shape[1] - rel_x)
        rel_h = min(rel_h, right_half.shape[0] - rel_y)
        
        if rel_w > 0 and rel_h > 0:
            # Extract the timer ROI from the blue mask
            timer_roi_mask = blue_mask[rel_y:rel_y+rel_h, rel_x:rel_x+rel_w]
            
            # The blue mask has white pixels where blue background is detected
            # We want white background with black text, so we use the mask directly
            # Blue background areas become white (255), text areas become black (0)
            timer_roi_corrected = timer_roi_mask.copy()
            
            return timer_roi_corrected
        
        return None
    
    def process_timer_roi(self, timer_roi: np.ndarray, timer_recognizer, 
                         last_percentage: Optional[int] = None) -> Optional[str]:
        """
        Process the timer ROI using template matching and convert to milliseconds.
        Ensures exactly 7 digits are detected (mm:ss:xxx format).
        
        Args:
            timer_roi: Timer region of interest
            timer_recognizer: Timer recognition instance
            last_percentage: Last percentage for logging
            
        Returns:
            Extracted timer string or None
        """
        if timer_roi is None or timer_roi.size == 0:
            return None
        
        try:
            # Use template matching for digit recognition only
            if timer_recognizer.digit_templates:
                digits_string, digit_details, processed_img = timer_recognizer.extract_digits(timer_roi, debug=False)
                
                # Check if we have exactly 7 digits (mm:ss:xxx format)
                if len(digits_string) == 7:
                    # Convert to total milliseconds if we have enough digits
                    total_ms = timer_recognizer.convert_to_milliseconds(digits_string)
                    
                    if digits_string:
                        # Print timer information when percentage changes
                        if total_ms is not None:
                            minutes = total_ms // 60000
                            seconds = (total_ms % 60000) // 1000
                            milliseconds = total_ms % 1000
                            print(f"Timer at {last_percentage}: {digits_string} -> {minutes:02d}:{seconds:02d}.{milliseconds:03d} ({total_ms}ms)")
                        else:
                            print(f"Timer at {last_percentage}: {digits_string} (conversion failed)")
                            
                        return digits_string
                else:
                    # If we don't have exactly 7 digits, log the issue but don't return a result
                    print(f"Timer at {last_percentage}: Detected {len(digits_string)} digits ({digits_string}) instead of expected 7 - ignoring")
                    return None
            
            return None
            
        except Exception as e:
            return None
    
    def preprocess_for_cnn(self, image_array: np.ndarray) -> torch.Tensor:
        """
        Preprocess image for CNN prediction.
        
        Args:
            image_array: Input image array
            
        Returns:
            Preprocessed tensor
        """
        # Convert numpy array to PIL Image
        pil_image = Image.fromarray(image_array)
        
        # Apply transforms
        tensor_image = self.data_transforms(pil_image)
        
        return tensor_image.unsqueeze(0)
