"""
Timer Recognition Module

This module handles digit recognition using template matching for timer extraction.
"""

import os
import cv2
import numpy as np
from typing import Dict, List, Tuple, Optional
from src.utils.helpers import get_template_dir

# Configuration constants
TEMPLATE_DIR = get_template_dir()
MATCH_THRESHOLD = 0.7
ITALIC_SHEAR_ANGLE = -15

# Global optimization variables
_clahe = None
_shear_matrix = None

def load_digit_templates() -> Dict[str, np.ndarray]:
    """
    Load the manually created digit templates (0-9) from the processed directory.
    
    Returns:
        Dict mapping digit strings to template images
    """
    templates = {}
    
    if not os.path.exists(TEMPLATE_DIR):
        print(f"Template directory {TEMPLATE_DIR} not found!")
        return templates
    
    # Load digit templates (0-9)
    for digit in range(10):
        template_path = os.path.join(TEMPLATE_DIR, f"{digit}.png")
        
        if os.path.exists(template_path):
            template = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
            if template is not None:
                templates[str(digit)] = template
                print(f"Loaded template for digit '{digit}' (size: {template.shape[1]}x{template.shape[0]})")
            else:
                print(f"Failed to load template: {template_path}")
        else:
            print(f"Template not found: {template_path}")
    
    return templates

def correct_italic_text(image: np.ndarray, shear_angle_degrees: float = ITALIC_SHEAR_ANGLE) -> np.ndarray:
    """
    Correct italic text by applying inverse shear transformation.
    
    Args:
        image: Input grayscale image
        shear_angle_degrees: Angle to correct (negative for left-leaning italic)
        
    Returns:
        Corrected image
    """
    global _shear_matrix
    height, width = image.shape
    
    if _shear_matrix is None:
        shear_angle = np.radians(shear_angle_degrees)
        shear_factor = -np.tan(shear_angle)
        _shear_matrix = np.float32([[1, shear_factor, 0], [0, 1, 0]])
    
    new_width = int(width + abs(np.tan(np.radians(shear_angle_degrees)) * height))
    
    corrected = cv2.warpAffine(image, _shear_matrix, (new_width, height), 
                              borderMode=cv2.BORDER_CONSTANT, 
                              borderValue=255)
    
    return corrected

def preprocess_timer_image(image: np.ndarray) -> np.ndarray:
    """
    Preprocess timer image: correct italics, enhance contrast, ensure binary.
    
    Args:
        image: Input grayscale image
        
    Returns:
        Preprocessed binary image
    """
    global _clahe
    if _clahe is None:
        _clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    
    corrected = correct_italic_text(image)
    enhanced = _clahe.apply(corrected)
    denoised = cv2.medianBlur(enhanced, 3)
    _, binary = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    return binary

def match_digit_at_position(roi_image: np.ndarray, templates: Dict[str, np.ndarray], 
                          threshold: float = MATCH_THRESHOLD) -> Tuple[Optional[str], float]:
    """
    Match a character ROI against digit templates (0-9).
    
    Args:
        roi_image: Region of interest image
        templates: Dictionary of digit templates
        threshold: Confidence threshold for matching
        
    Returns:
        Tuple of (best_digit, confidence)
    """
    best_digit = None
    best_confidence = 0
    
    if len(roi_image.shape) == 3:
        roi_image = cv2.cvtColor(roi_image, cv2.COLOR_BGR2GRAY)
    
    _, roi_binary = cv2.threshold(roi_image, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    scale_factors = [0.8, 0.9, 1.0, 1.1, 1.2]
    
    for digit, template in templates.items():
        max_confidence_for_digit = 0
        
        for scale_factor in scale_factors:
            scaled_height = int(template.shape[0] * scale_factor)
            scaled_width = int(template.shape[1] * scale_factor)
            
            if scaled_height > 0 and scaled_width > 0:
                template_resized = cv2.resize(template, (scaled_width, scaled_height), 
                                            interpolation=cv2.INTER_CUBIC)
                
                if (roi_binary.shape[0] >= template_resized.shape[0] and 
                    roi_binary.shape[1] >= template_resized.shape[1]):
                    result = cv2.matchTemplate(roi_binary, template_resized, cv2.TM_CCOEFF_NORMED)
                    confidence = np.max(result)
                elif (template_resized.shape[0] >= roi_binary.shape[0] and 
                      template_resized.shape[1] >= roi_binary.shape[1]):
                    result = cv2.matchTemplate(template_resized, roi_binary, cv2.TM_CCOEFF_NORMED)
                    confidence = np.max(result)
                else:
                    confidence = 0
                
                if confidence > max_confidence_for_digit:
                    max_confidence_for_digit = confidence
        
        if max_confidence_for_digit > best_confidence:
            best_confidence = max_confidence_for_digit
            best_digit = digit
    
    if best_confidence >= threshold:
        return best_digit, best_confidence
    else:
        return None, best_confidence

def find_digit_regions(processed_image: np.ndarray) -> List[Tuple[int, int, int, int]]:
    """
    Find potential digit regions in the processed image using contour detection.
    
    Args:
        processed_image: Preprocessed binary image
        
    Returns:
        List of (x, y, w, h) bounding boxes sorted left to right
    """
    inverted = cv2.bitwise_not(processed_image)
    contours, _ = cv2.findContours(inverted, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    digit_regions = []
    
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = cv2.contourArea(contour)
        
        if (w >= 8 and h >= 12 and w <= 100 and h <= 100 and  
            area > 50 and  
            h/w >= 0.8 and h/w <= 4.0):
            digit_regions.append((x, y, w, h))
    
    digit_regions.sort(key=lambda region: region[0])
    
    return digit_regions

def extract_digits_from_timer(image: np.ndarray, templates: Dict[str, np.ndarray], 
                            debug: bool = False) -> Tuple[str, List, np.ndarray]:
    """
    Extract only digits (0-9) from a timer image, ignoring punctuation.
    
    Args:
        image: Timer image
        templates: Digit templates dictionary
        debug: Whether to print debug information
        
    Returns:
        Tuple of (digits_string, digit_details, processed_image)
    """
    processed_image = preprocess_timer_image(image)
    digit_regions = find_digit_regions(processed_image)
    
    recognized_digits = []
    digit_details = []
    
    if debug:
        print(f"Found {len(digit_regions)} potential digit regions")
    
    for i, (x, y, w, h) in enumerate(digit_regions):
        padding = max(2, min(w, h) // 8)
        x_start = max(0, x - padding)
        y_start = max(0, y - padding)
        x_end = min(processed_image.shape[1], x + w + padding)
        y_end = min(processed_image.shape[0], y + h + padding)
        
        digit_roi = processed_image[y_start:y_end, x_start:x_end]
        
        if digit_roi.size > 0:
            digit, confidence = match_digit_at_position(digit_roi, templates)
            
            if digit is not None:
                recognized_digits.append(digit)
                digit_details.append((digit, confidence, (x, y, w, h), digit_roi))
                if debug:
                    print(f"  Region {i}: Digit '{digit}' (confidence: {confidence:.3f})")
            else:
                if debug:
                    print(f"  Region {i}: No match (best confidence: {confidence:.3f})")
    
    digits_only = ''.join(recognized_digits)
    
    return digits_only, digit_details, processed_image

def convert_timer_to_milliseconds(timer_string: str) -> Optional[int]:
    """
    Convert timer string in format mmssxxx to total milliseconds.
    
    Args:
        timer_string: Timer string (mmssxxx format)
        
    Returns:
        Total milliseconds or None if conversion fails
    """
    if not timer_string:
        return None
    
    try:
        # Handle different lengths of timer strings
        if len(timer_string) >= 6:
            # Pad with zeros if needed to ensure we have at least 6 digits
            padded_timer = timer_string.ljust(7, '0')[:7]
            
            # Extract components based on expected format
            if len(timer_string) == 6:
                # Format: mmssxx (6 digits) - treat last 2 as centiseconds (multiply by 10)
                minutes = int(padded_timer[0:2])
                seconds = int(padded_timer[2:4])
                centiseconds = int(padded_timer[4:6])
                milliseconds = centiseconds * 10  # Convert centiseconds to milliseconds
            else:
                # Format: mmssxxx (7 digits) - standard format
                minutes = int(padded_timer[0:2])
                seconds = int(padded_timer[2:4])
                milliseconds = int(padded_timer[4:7])
            
            total_ms = (minutes * 60 * 1000) + (seconds * 1000) + milliseconds
            
            return total_ms
        else:
            return None
    except (ValueError, IndexError):
        return None

class TimerRecognizer:
    """
    Timer recognition class that encapsulates all timer-related functionality.
    """
    
    def __init__(self):
        """Initialize the timer recognizer with digit templates."""
        print("Loading digit templates for timer recognition...")
        self.digit_templates = load_digit_templates()
        print(f"Loaded {len(self.digit_templates)} digit templates for timer recognition\n")
        
        # Cache for digit ROI coordinates (standardized width)
        self.cached_digit_rois = None
        self.last_processed_image_shape = None
    
    def _create_standardized_digit_rois(self, digit_regions: List[Tuple[int, int, int, int]], 
                                       image_shape: Tuple[int, int]) -> List[Tuple[int, int, int, int]]:
        """
        Create standardized digit ROIs with fixed width to handle narrow digits like '1'.
        
        Args:
            digit_regions: Original detected digit regions (x, y, w, h)
            image_shape: Shape of the processed image (height, width)
            
        Returns:
            List of standardized ROI coordinates (x, y, w, h)
        """
        if not digit_regions:
            return []
        
        # Calculate standard width based on average/maximum expected digit width
        widths = [w for x, y, w, h in digit_regions]
        heights = [h for x, y, w, h in digit_regions]
        
        # Use the maximum width found, with a minimum reasonable size
        standard_width = max(max(widths) if widths else 20, 20)
        standard_height = max(max(heights) if heights else 30, 30)
        
        standardized_rois = []
        
        for x, y, w, h in digit_regions:
            # Center the standardized ROI on the detected digit center
            center_x = x + w // 2
            center_y = y + h // 2
            
            # Calculate new coordinates with standard width/height
            new_x = max(0, center_x - standard_width // 2)
            new_y = max(0, center_y - standard_height // 2)
            
            # Ensure we don't go beyond image boundaries
            new_x = min(new_x, image_shape[1] - standard_width)
            new_y = min(new_y, image_shape[0] - standard_height)
            
            # Adjust width/height if near boundaries
            actual_width = min(standard_width, image_shape[1] - new_x)
            actual_height = min(standard_height, image_shape[0] - new_y)
            
            standardized_rois.append((new_x, new_y, actual_width, actual_height))
        
        return standardized_rois

    def _extract_digits_with_cached_rois(self, processed_image: np.ndarray) -> Tuple[str, List]:
        """
        Extract digits using cached ROI coordinates for better performance.
        
        Args:
            processed_image: Preprocessed binary image
            
        Returns:
            Tuple of (digits_string, digit_details)
        """
        if self.cached_digit_rois is None:
            return "", []
        
        recognized_digits = []
        digit_details = []
        
        for i, (x, y, w, h) in enumerate(self.cached_digit_rois):
            # Extract ROI with some padding
            padding = 2
            x_start = max(0, x - padding)
            y_start = max(0, y - padding)
            x_end = min(processed_image.shape[1], x + w + padding)
            y_end = min(processed_image.shape[0], y + h + padding)
            
            digit_roi = processed_image[y_start:y_end, x_start:x_end]
            
            if digit_roi.size > 0:
                digit, confidence = match_digit_at_position(digit_roi, self.digit_templates)
                
                if digit is not None:
                    recognized_digits.append(digit)
                    digit_details.append((digit, confidence, (x, y, w, h), digit_roi))
        
        return ''.join(recognized_digits), digit_details

    def extract_digits(self, image: np.ndarray, debug: bool = False) -> Tuple[str, List, np.ndarray]:
        """
        Extract digits from timer image with ROI caching for performance.
        
        Args:
            image: Timer image
            debug: Whether to print debug information
            
        Returns:
            Tuple of (digits_string, digit_details, processed_image)
        """
        processed_image = preprocess_timer_image(image)
        current_shape = processed_image.shape
        
        # Try using cached ROIs first if available and image shape hasn't changed
        if (self.cached_digit_rois is not None and 
            self.last_processed_image_shape == current_shape):
            
            digits_string, digit_details = self._extract_digits_with_cached_rois(processed_image)
            
            # If we got exactly 7 digits, return the cached result
            if len(digits_string) == 7:
                if debug:
                    print(f"Used cached ROIs: {digits_string}")
                return digits_string, digit_details, processed_image
            else:
                if debug:
                    print(f"Cached ROIs failed ({len(digits_string)} digits), falling back to contour detection")
        
        # Fall back to full contour detection
        digit_regions = find_digit_regions(processed_image)
        recognized_digits = []
        digit_details = []
        
        if debug:
            print(f"Found {len(digit_regions)} potential digit regions")
        
        for i, (x, y, w, h) in enumerate(digit_regions):
            padding = max(2, min(w, h) // 8)
            x_start = max(0, x - padding)
            y_start = max(0, y - padding)
            x_end = min(processed_image.shape[1], x + w + padding)
            y_end = min(processed_image.shape[0], y + h + padding)
            
            digit_roi = processed_image[y_start:y_end, x_start:x_end]
            
            if digit_roi.size > 0:
                digit, confidence = match_digit_at_position(digit_roi, self.digit_templates)
                
                if digit is not None:
                    recognized_digits.append(digit)
                    digit_details.append((digit, confidence, (x, y, w, h), digit_roi))
                    if debug:
                        print(f"  Region {i}: Digit '{digit}' (confidence: {confidence:.3f})")
                else:
                    if debug:
                        print(f"  Region {i}: No match (best confidence: {confidence:.3f})")
        
        digits_string = ''.join(recognized_digits)
        
        # Cache the standardized ROIs if we got exactly 7 digits
        if len(digits_string) == 7:
            self.cached_digit_rois = self._create_standardized_digit_rois(digit_regions, current_shape)
            self.last_processed_image_shape = current_shape
            if debug:
                print(f"Cached {len(self.cached_digit_rois)} standardized ROIs")
        
        return digits_string, digit_details, processed_image
    
    def clear_digit_roi_cache(self):
        """Clear the cached digit ROI coordinates."""
        self.cached_digit_rois = None
        self.last_processed_image_shape = None

    def convert_to_milliseconds(self, timer_string: str) -> Optional[int]:
        """
        Convert timer string to milliseconds.
        
        Args:
            timer_string: Timer string in mmssxxx format
            
        Returns:
            Total milliseconds or None if conversion fails
        """
        return convert_timer_to_milliseconds(timer_string)
