"""
Race Data Management Module

This module handles saving and loading race ghost data for timing comparisons.
"""

import json
import os
from typing import Dict, Optional, List


class RaceDataManager:
    """
    Manages race timing data for recording and racing against ghosts.
    """
    
    def __init__(self):
        """Initialize the race data manager."""
        self.current_race_data: Dict[str, int] = {}
        self.ghost_data: Optional[Dict[str, int]] = None
        self.ghost_filename: Optional[str] = None
        
        # Initialize empty race data for all percentages (0-100)
        self.reset_race_data()
    
    def reset_race_data(self):
        """Reset the current race data to empty."""
        self.current_race_data = {str(i): "0000000" for i in range(101)}
    
    def is_race_complete(self) -> bool:
        """
        Check if race data is complete (has valid time at 100%).
        
        Returns:
            True if race has reached 100% with valid time data
        """
        return (self.current_race_data.get("100", "0000000") != "0000000")
    
    def record_time_at_percentage(self, percentage: int, time_ms: int):
        """
        Record a time at a specific percentage.
        
        Args:
            percentage: Percentage point (0-100)
            time_ms: Time in milliseconds (7 digits, padded with zeros)
        """
        if 0 <= percentage <= 100:
            # Ensure time is always 7 digits, padded with leading zeros
            formatted_time = f"{time_ms:07d}"
            
            # Validate: 00.00.000 (0000000) can only be at 0%
            if formatted_time == "0000000" and percentage != 0:
                print(f"Warning: Ignoring invalid time 00.00.000 at {percentage}% (can only be at 0%)")
                return
            
            # Validate and correct anomalous readings
            corrected_time = self._validate_and_correct_time(percentage, time_ms)
            if corrected_time != time_ms:
                print(f"Corrected anomalous time at {percentage}%: {time_ms}ms -> {corrected_time}ms")
                formatted_time = f"{corrected_time:07d}"
            
            # Special handling for 99% - only set it once (first time we reach 99%)
            if percentage == 99:
                existing_99_time = self.current_race_data.get("99", "0000000")
                if existing_99_time != "0000000":
                    print(f"99% time already set to {existing_99_time}ms, ignoring new time {formatted_time}ms")
                    return
                else:
                    print(f"Setting 99% time for the first time: {formatted_time}ms")
            
            self.current_race_data[str(percentage)] = formatted_time
            
            # Handle percentage skips (out-of-bounds scenarios)
            self._handle_percentage_skip(percentage, formatted_time)
    
    def _handle_percentage_skip(self, current_percentage: int, current_time: str):
        """
        Handle large percentage jumps by filling intermediate percentages.
        
        When player goes out of bounds, they can skip from e.g. 31% to 74%.
        We fill all intermediate percentages (32%-73%) with the same time as 31%.
        
        Args:
            current_percentage: The current percentage reached (0-99)
            current_time: The time at current percentage
        """
        # Find the last recorded non-zero percentage
        last_recorded_percentage = None
        for i in range(current_percentage - 1, -1, -1):
            if (self.current_race_data.get(str(i), "0000000") != "0000000"):
                last_recorded_percentage = i
                break
        
        if last_recorded_percentage is not None:
            # Check if there's a significant skip (more than 1% gap)
            gap = current_percentage - last_recorded_percentage
            if gap > 1:
                # Fill all intermediate percentages with the last recorded time
                last_time = self.current_race_data[str(last_recorded_percentage)]
                for i in range(last_recorded_percentage + 1, current_percentage):
                    if self.current_race_data.get(str(i), "0000000") == "0000000":
                        self.current_race_data[str(i)] = last_time
    
    def record_final_time(self, time_ms: int):
        """
        Record the final time at 100% when race completes.
        Ensures the 100% time is never lower than the 99% time.
        
        Args:
            time_ms: Final time in milliseconds (7 digits, padded with zeros)
        """
        formatted_time = f"{time_ms:07d}"
        
        # Get the time at 99% to ensure 100% time is not lower
        time_99 = self.current_race_data.get("99", "0000000")
        if time_99 != "0000000":
            time_99_ms = int(time_99)
            if time_ms < time_99_ms:
                print(f"Warning: Final time {time_ms}ms is less than 99% time {time_99_ms}ms. Using 99% time for 100%.")
                formatted_time = time_99
                time_ms = time_99_ms
        
        self.current_race_data["100"] = formatted_time
        print(f"Recorded final time at 100%: {time_ms}ms")
    
    def _validate_and_correct_time(self, percentage: int, time_ms: int) -> int:
        """
        Validate timer reading and correct anomalous values.
        
        Args:
            percentage: Current percentage (0-100)
            time_ms: Proposed time in milliseconds
            
        Returns:
            Corrected time in milliseconds
        """
        if percentage <= 0:
            return time_ms  # No validation needed for 0%
        
        # Get surrounding valid times for analysis
        valid_times = []
        valid_percentages = []
        
        # Look at previous few percentages to establish trend
        for i in range(max(0, percentage - 5), percentage):
            time_str = self.current_race_data.get(str(i), "0000000")
            if time_str != "0000000":
                valid_times.append(int(time_str))
                valid_percentages.append(i)
        
        if len(valid_times) < 2:
            return time_ms  # Not enough data to validate
        
        # Calculate expected time based on recent trend
        expected_time = self._calculate_expected_time(percentage, valid_times, valid_percentages)
        
        # Check if current reading is anomalous
        if self._is_anomalous_reading(time_ms, expected_time, valid_times):
            print(f"Detected anomalous reading at {percentage}%: {time_ms}ms (expected ~{expected_time}ms)")
            return expected_time
        
        # Check if time decreased (should never happen)
        if percentage > 0:
            prev_time_str = self.current_race_data.get(str(percentage - 1), "0000000")
            if prev_time_str != "0000000":
                prev_time = int(prev_time_str)
                if time_ms < prev_time:
                    print(f"Time decreased at {percentage}%: {time_ms}ms < {prev_time}ms. Using interpolated value.")
                    return max(prev_time + 500, expected_time)  # Add minimum 0.5s progression
        
        return time_ms
    
    def _calculate_expected_time(self, percentage: int, valid_times: List[int], valid_percentages: List[int]) -> int:
        """Calculate expected time based on recent progression."""
        if len(valid_times) < 2:
            return valid_times[-1] if valid_times else 0
        
        # Calculate average time per percentage point from recent data
        time_diffs = []
        for i in range(1, len(valid_times)):
            time_diff = valid_times[i] - valid_times[i-1]
            percentage_diff = valid_percentages[i] - valid_percentages[i-1]
            if percentage_diff > 0:
                time_diffs.append(time_diff / percentage_diff)
        
        if not time_diffs:
            return valid_times[-1]
        
        # Use average rate of change
        avg_time_per_percent = sum(time_diffs) / len(time_diffs)
        last_time = valid_times[-1]
        last_percentage = valid_percentages[-1]
        
        percentage_gap = percentage - last_percentage
        expected_time = last_time + (avg_time_per_percent * percentage_gap)
        
        return int(expected_time)
    
    def _is_anomalous_reading(self, reading: int, expected: int, valid_times: List[int]) -> bool:
        """Determine if a reading is anomalous based on expected value and historical data."""
        if not valid_times:
            return False
        
        # Calculate tolerance based on recent variability
        recent_diffs = []
        for i in range(1, len(valid_times)):
            recent_diffs.append(abs(valid_times[i] - valid_times[i-1]))
        
        if recent_diffs:
            avg_diff = sum(recent_diffs) / len(recent_diffs)
            tolerance = max(5000, avg_diff * 3)  # At least 5 seconds, or 3x average difference
        else:
            tolerance = 5000  # Default 5 second tolerance
        
        deviation = abs(reading - expected)
        
        # Check for massive jumps (like the 0069729 case)
        if deviation > tolerance:
            print(f"Anomaly detected: deviation {deviation}ms > tolerance {tolerance}ms")
            return True
        
        return False
    
    def get_time_at_percentage(self, percentage: int) -> Optional[str]:
        """
        Get the recorded time at a specific percentage.
        
        Args:
            percentage: Percentage point (0-100)
            
        Returns:
            Time string (7 digits) or None if not recorded
        """
        if 0 <= percentage <= 100:
            return self.current_race_data.get(str(percentage))
        return None
    
    def save_race_data(self, filename: str) -> bool:
        """
        Save current race data to a JSON file.
        
        Args:
            filename: Name of the file to save (without extension)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Create the data structure
            race_data = {
                "fingerprint": "ALU_TOOL",
                "times": self.current_race_data.copy()
            }
            
            # Ensure filename has .json extension
            if not filename.endswith('.json'):
                filename += '.json'
            
            # Save to file
            with open(filename, 'w') as f:
                json.dump(race_data, f, indent=2)
            
            return True
        except Exception as e:
            print(f"Error saving race data: {e}")
            return False
    
    def load_ghost_data(self, filepath: str) -> bool:
        """
        Load ghost data from a JSON file.
        
        Args:
            filepath: Path to the JSON file
            
        Returns:
            True if loaded successfully, False otherwise
        """
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            
            # Validate the file
            if not self._validate_ghost_file(data):
                return False
            
            self.ghost_data = data['times']
            self.ghost_filename = os.path.splitext(os.path.basename(filepath))[0]
            return True
            
        except Exception as e:
            print(f"Error loading ghost data: {e}")
            return False
    
    def _validate_ghost_file(self, data: dict) -> bool:
        """
        Validate that a ghost file has the correct format.
        
        Args:
            data: Loaded JSON data
            
        Returns:
            True if valid, False otherwise
        """
        # Check for fingerprint
        if data.get('fingerprint') != 'ALU_TOOL':
            print("Invalid file: Missing or incorrect fingerprint")
            return False
        
        # Check for times data
        times = data.get('times', {})
        if not isinstance(times, dict):
            print("Invalid file: Times data must be a dictionary")
            return False
        
        # Check that all percentage points (0-100) have values
        for i in range(101):
            if str(i) not in times:
                print(f"Invalid file: Missing time for {i}%")
                return False
            
            # Validate that the time is a valid string or number
            time_value = times[str(i)]
            if not isinstance(time_value, (str, int)):
                print(f"Invalid file: Invalid time format at {i}%")
                return False
        
        return True
    
    def get_ghost_time_at_percentage(self, percentage: int) -> Optional[str]:
        """
        Get the ghost time at a specific percentage.
        
        Args:
            percentage: Percentage point (0-100)
            
        Returns:
            Ghost time string or None if not available
        """
        if self.ghost_data and 0 <= percentage <= 100:
            return str(self.ghost_data.get(str(percentage), "0000000"))
        return None
    
    def calculate_delta(self, percentage: int, current_time_ms: int) -> Optional[float]:
        """
        Calculate the time delta against the ghost at a specific percentage.
        
        Args:
            percentage: Percentage point (0-99)
            current_time_ms: Current time in milliseconds
            
        Returns:
            Delta in seconds (positive = behind ghost, negative = ahead of ghost) or None
        """
        if not self.ghost_data:
            return None
        
        ghost_time_str = self.get_ghost_time_at_percentage(percentage)
        if not ghost_time_str:
            return None
        
        try:
            ghost_time_ms = int(ghost_time_str)
            delta_ms = current_time_ms - ghost_time_ms
            return delta_ms / 1000.0  # Convert to seconds
        except (ValueError, TypeError):
            return None
    
    def is_ghost_loaded(self) -> bool:
        """Check if a ghost is currently loaded."""
        return self.ghost_data is not None
    
    def get_ghost_filename(self) -> Optional[str]:
        """Get the filename of the currently loaded ghost."""
        return self.ghost_filename
    
    def unload_ghost(self):
        """Unload the current ghost data."""
        self.ghost_data = None
        self.ghost_filename = None