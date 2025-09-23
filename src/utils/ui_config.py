"""
UI Configuration Manager

This module handles saving and loading UI position and settings between sessions.
"""

import json
import os
import tkinter as tk
from typing import Dict, Tuple, Optional


class UIConfigManager:
    """
    Manages UI configuration including window position, size, and monitor validation.
    """
    
    def __init__(self, config_file: str = "ui_config.json"):
        """
        Initialize the UI configuration manager.
        
        Args:
            config_file: Name of the configuration file
        """
        self.config_file = config_file
        self.config_path = os.path.join(os.getcwd(), config_file)
        self.default_config = {
            "window_position": {"x": 100, "y": 100},
            "window_size": {"width": 300, "height": 120},
            "scaling": 1.15,
            "is_pinned": True,
            "panels": {
                "race_panel_expanded": False,
                "debug_panel_expanded": False
            }
        }
    
    def save_config(self, config: Dict) -> bool:
        """
        Save configuration to file.
        
        Args:
            config: Configuration dictionary to save
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving UI config: {e}")
            return False
    
    def load_config(self) -> Dict:
        """
        Load configuration from file.
        
        Returns:
            Configuration dictionary (defaults if file doesn't exist or is invalid)
        """
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    # Validate and merge with defaults
                    return self._validate_and_merge_config(config)
            else:
                print(f"Config file not found, using defaults: {self.config_path}")
                return self.default_config.copy()
        except Exception as e:
            print(f"Error loading UI config: {e}, using defaults")
            return self.default_config.copy()
    
    def _validate_and_merge_config(self, config: Dict) -> Dict:
        """
        Validate loaded config and merge with defaults for missing keys.
        
        Args:
            config: Loaded configuration
            
        Returns:
            Validated and merged configuration
        """
        result = self.default_config.copy()
        
        # Safely merge configuration
        if isinstance(config, dict):
            for key, value in config.items():
                if key in result:
                    if isinstance(result[key], dict) and isinstance(value, dict):
                        result[key].update(value)
                    else:
                        result[key] = value
        
        return result
    
    def get_available_monitors(self) -> list:
        """
        Get information about available monitors.
        
        Returns:
            List of monitor dictionaries with geometry information
        """
        try:
            # Create a temporary root window to get screen information
            temp_root = tk.Tk()
            temp_root.withdraw()  # Hide the window
            
            monitors = []
            
            # Get primary monitor info
            screen_width = temp_root.winfo_screenwidth()
            screen_height = temp_root.winfo_screenheight()
            
            # For Windows, we can get multiple monitor info using tkinter
            try:
                # Try to get monitor count (Windows-specific)
                import ctypes
                from ctypes import wintypes
                
                user32 = ctypes.windll.user32
                
                def enum_display_monitors():
                    """Enumerate all display monitors."""
                    monitors_info = []
                    
                    def monitor_enum_proc(hMonitor, hdcMonitor, lprcMonitor, dwData):
                        monitor_info = wintypes.RECT()
                        ctypes.windll.user32.GetMonitorInfoW(hMonitor, ctypes.byref(monitor_info))
                        
                        monitors_info.append({
                            'left': lprcMonitor.contents.left,
                            'top': lprcMonitor.contents.top,
                            'right': lprcMonitor.contents.right,
                            'bottom': lprcMonitor.contents.bottom,
                            'width': lprcMonitor.contents.right - lprcMonitor.contents.left,
                            'height': lprcMonitor.contents.bottom - lprcMonitor.contents.top
                        })
                        return True
                    
                    MONITORENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, 
                                                       wintypes.HMONITOR, 
                                                       wintypes.HDC, 
                                                       ctypes.POINTER(wintypes.RECT), 
                                                       wintypes.LPARAM)
                    
                    user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(monitor_enum_proc), 0)
                    return monitors_info
                
                monitors = enum_display_monitors()
                
            except Exception as e:
                print(f"Could not enumerate monitors: {e}, using primary monitor")
                # Fallback to primary monitor only
                monitors = [{
                    'left': 0, 'top': 0, 
                    'right': screen_width, 'bottom': screen_height,
                    'width': screen_width, 'height': screen_height
                }]
            
            temp_root.destroy()
            return monitors
            
        except Exception as e:
            print(f"Error getting monitor info: {e}")
            # Fallback monitor info
            return [{'left': 0, 'top': 0, 'right': 1920, 'bottom': 1080, 'width': 1920, 'height': 1080}]
    
    def validate_window_position(self, x: int, y: int, width: int = 300, height: int = 120) -> Tuple[int, int]:
        """
        Validate that a window position is visible on available monitors.
        
        Args:
            x: X coordinate
            y: Y coordinate
            width: Window width
            height: Window height
            
        Returns:
            Tuple of validated (x, y) coordinates
        """
        monitors = self.get_available_monitors()
        
        if not monitors:
            # Fallback to default position
            return 100, 100
        
        # Check if the window would be visible on any monitor
        for monitor in monitors:
            # Check if at least part of the window would be visible
            window_right = x + width
            window_bottom = y + height
            
            # Check for overlap with this monitor
            if (x < monitor['right'] and window_right > monitor['left'] and
                y < monitor['bottom'] and window_bottom > monitor['top']):
                
                # Window has some overlap with this monitor
                # Ensure at least part of the title bar area is accessible
                title_bar_y = y + 30  # Approximate title bar height
                
                if (x >= monitor['left'] and x < monitor['right'] and
                    title_bar_y >= monitor['top'] and title_bar_y < monitor['bottom']):
                    # Position is valid
                    return x, y
        
        # No valid position found, use primary monitor
        primary_monitor = monitors[0]
        
        # Place window with some margin from edges
        margin = 50
        safe_x = max(primary_monitor['left'] + margin, 
                    min(x, primary_monitor['right'] - width - margin))
        safe_y = max(primary_monitor['top'] + margin,
                    min(y, primary_monitor['bottom'] - height - margin))
        
        print(f"Window position {x},{y} is off-screen, moved to {safe_x},{safe_y}")
        return safe_x, safe_y
    
    def get_window_geometry_from_config(self, config: Dict) -> str:
        """
        Get tkinter geometry string from configuration.
        
        Args:
            config: Configuration dictionary
            
        Returns:
            Tkinter geometry string (e.g., "300x120+100+100")
        """
        pos = config.get("window_position", {"x": 100, "y": 100})
        size = config.get("window_size", {"width": 300, "height": 120})
        
        # Validate position
        x, y = self.validate_window_position(pos["x"], pos["y"], size["width"], size["height"])
        
        return f"{size['width']}x{size['height']}+{x}+{y}"
    
    def extract_geometry_from_string(self, geometry: str) -> Dict:
        """
        Extract position and size from tkinter geometry string.
        
        Args:
            geometry: Tkinter geometry string (e.g., "300x120+100+100")
            
        Returns:
            Dictionary with position and size information
        """
        try:
            # Parse geometry string: "WIDTHxHEIGHT+X+Y"
            parts = geometry.replace('x', '+').replace('+', ' ').split()
            if len(parts) >= 4:
                width, height, x, y = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
                return {
                    "window_position": {"x": x, "y": y},
                    "window_size": {"width": width, "height": height}
                }
        except (ValueError, IndexError) as e:
            print(f"Error parsing geometry string '{geometry}': {e}")
        
        # Return defaults if parsing fails
        return {
            "window_position": {"x": 100, "y": 100},
            "window_size": {"width": 300, "height": 120}
        }