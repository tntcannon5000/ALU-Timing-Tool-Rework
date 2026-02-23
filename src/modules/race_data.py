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
        self.split_filepath: Optional[str] = None
        # Split-file related data
        self.splits: Optional[list] = None  # normalized list of {'name':str,'percent':int}
        self.split_times: Optional[Dict[str, int]] = None
        self.is_split_loaded: bool = False
        
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
            # 0% is always 0ms by definition
            if percentage == 0:
                self.current_race_data["0"] = "0000000"
                return
            # Ensure time is always 7 digits, padded with leading zeros
            formatted_time = f"{time_ms:07d}"
            
            # Validate: 00.00.000 (0000000) can only be at 0%
            if formatted_time == "0000000" and percentage != 0:
                print(f"Warning: Ignoring invalid time 00.00.000 at {percentage}% (can only be at 0%)")
                return
            
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
    
    def record_final_time(self, time_ms: int, true_final_ms: int = 0):
        """
        Record the final time at 100% when race completes.
        If the checkpoint-based estimate is invalid (less than 99% time),
        falls back to true_final_ms - 1000ms.
        
        Args:
            time_ms: Final time in milliseconds (checkpoint estimate)
            true_final_ms: The actual last raw timer value (fallback source)
        """
        formatted_time = f"{time_ms:07d}"
        
        # Get the time at 99% to validate the checkpoint estimate
        time_99 = self.current_race_data.get("99", "0000000")
        if time_99 != "0000000":
            time_99_ms = int(time_99)
            if time_ms < time_99_ms:
                # Checkpoint estimate is invalid; use true_final - 1000ms
                fallback_ms = max(true_final_ms - 1000, time_99_ms) if true_final_ms > 0 else time_99_ms
                print(f"Warning: Checkpoint estimate {time_ms}ms is invalid. Using fallback: {fallback_ms}ms (true_final - 1s)")
                formatted_time = f"{fallback_ms:07d}"
                time_ms = fallback_ms
        
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
            
            # 0% is always 0ms by definition
            race_data["times"]["0"] = "0000000"
            
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

    # --- Split file support ---
    def _normalize_splits(self, raw_splits) -> Optional[list]:
        """
        Normalize various allowed splits formats into a list of dicts:
        - list of percentages: [25,50,75,99]
        - dict mapping keys->percent: {"1":25,...}
        - list of pairs [name,percent]: [["first",50],["second",99]]

        Returns list of {'name': str, 'percent': int} or None if invalid.
        """
        if raw_splits is None:
            return None

        normalized = []
        # List of pairs with names
        if isinstance(raw_splits, list):
            for item in raw_splits:
                if isinstance(item, list) and len(item) == 2:
                    name, percent = item[0], item[1]
                    try:
                        p = int(percent)
                    except Exception:
                        return None
                    normalized.append({"name": str(name), "percent": p})
                elif isinstance(item, int) or (isinstance(item, str) and item.isdigit()):
                    # simple percentage list
                    p = int(item)
                    normalized.append({"name": f"split_{p}", "percent": p})
                else:
                    return None

        elif isinstance(raw_splits, dict):
            # dict mapping index->percent
            try:
                # sort by key to keep deterministic order
                for k in sorted(raw_splits.keys(), key=lambda x: int(x) if str(x).isdigit() else x):
                    p = int(raw_splits[k])
                    normalized.append({"name": str(k), "percent": p})
            except Exception:
                return None
        else:
            return None

        return normalized

    def _validate_split_file(self, data: dict) -> bool:
        """
        Validate split file structure. Requires same fingerprint and times as ghost file,
        plus `splits` and `split_times` fields. Enforces 1-20 splits and last split == 99.
        """
        # Must be a valid ghost file at minimum
        if data.get('fingerprint') != 'ALU_TOOL':
            print("Invalid split file: Missing or incorrect fingerprint")
            return False

        times = data.get('times')
        if not isinstance(times, dict):
            print("Invalid split file: times must be a dict")
            return False

        raw_splits = data.get('splits')
        normalized = self._normalize_splits(raw_splits)
        if not normalized:
            print("Invalid split file: splits format not recognized")
            return False

        if not (2 <= len(normalized) <= 10):
            print("Invalid split file: splits count must be between 2 and 10")
            return False

        # Last percent must be 99
        last_percent = normalized[-1]['percent']
        if last_percent != 99:
            print("Invalid split file: last split must be 99")
            return False

        split_times = data.get('split_times')
        if not isinstance(split_times, dict):
            print("Invalid split file: split_times must be a dict")
            return False

        # Quick check that split_times contains keys 0..100
        for i in range(101):
            if str(i) not in split_times:
                print(f"Invalid split file: Missing split_times for {i}%")
                return False

        return True

    def load_split_data(self, filepath: str) -> bool:
        """
        Load a split file from JSON. On success, sets `ghost_data`, `split_times`, `splits` and flags.
        Returns True on success, False otherwise.
        """
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)

            if not self._validate_split_file(data):
                return False

            # Load base times as ghost_data for compatibility
            self.ghost_data = data['times']
            self.split_times = data['split_times'].copy()
            self.splits = self._normalize_splits(data['splits'])
            self.ghost_filename = os.path.splitext(os.path.basename(filepath))[0]
            self.split_filepath = filepath
            self.is_split_loaded = True
            return True
        except Exception as e:
            print(f"Error loading split file: {e}")
            return False

    def is_split_file_loaded(self) -> bool:
        """Return True if a split file is currently loaded."""
        return self.is_split_loaded

    def get_splits(self) -> Optional[list]:
        """Return normalized splits list or None."""
        return self.splits

    def save_split_data(self, filepath: Optional[str] = None) -> bool:
        """
        Save the current split ghost back to JSON. If filepath is None, uses the
        last-loaded split filepath. Returns True on success.
        """
        try:
            target = filepath if filepath else self.split_filepath
            if not target:
                print("No target filepath provided to save split data")
                return False

            data = {
                "fingerprint": "ALU_TOOL",
                "times": self.ghost_data if self.ghost_data is not None else self.current_race_data.copy(),
                "splits": self.splits if self.splits is not None else [],
                "split_times": self.split_times if self.split_times is not None else {}
            }

            with open(target, 'w') as f:
                json.dump(data, f, indent=2)

            return True
        except Exception as e:
            print(f"Error saving split data: {e}")
            return False

    def update_split_times_with_current_race(self) -> bool:
        """
        Combine the current race into `self.split_times` by replacing any section (between splits)
        where the current race was faster than the stored section. Integration method:
        - For a faster section, replace the percentages within that section with the current race's
          recorded times shifted so the section start time equals the stored split start time.
        - After replacing the section, shift all subsequent times to preserve a continuous timeline.

        Returns True if any changes were made, False otherwise.
        """
        if not self.is_split_loaded or not self.split_times or not self.splits:
            print("No split file loaded to update")
            return False

        changed = False

        # Work on integer-based times for calculations
        split_times_int = {k: int(v) for k, v in self.split_times.items()}

        # Iterate through split sections
        # Start of first section is 0
        starts = [0] + [s['percent'] for s in self.splits]
        # If splits list contains 99 as last, ensure we treat sections appropriately
        for i in range(len(starts) - 1):
            S = starts[i]
            E = starts[i+1]

            # Guard: ensure S < E
            if S >= E:
                continue

            # Existing stored section duration
            ghost_start = split_times_int.get(str(S), None)
            ghost_end = split_times_int.get(str(E), None)
            if ghost_start is None or ghost_end is None:
                continue
            ghost_dur = ghost_end - ghost_start

            # Current race data for this section
            try:
                curr_start = int(self.current_race_data.get(str(S), "0000000"))
                curr_end = int(self.current_race_data.get(str(E), "0000000"))
            except Exception:
                continue

            # If current race doesn't have valid times for both ends, skip
            if curr_start == 0 or curr_end == 0:
                # treat "0000000" as missing
                continue

            curr_dur = curr_end - curr_start
            if curr_dur < 0:
                continue

            # If current section is faster than stored ghost section, incorporate it
            if curr_dur < ghost_dur:
                # Compute offset so the section's start aligns to stored ghost start
                offset = ghost_start - curr_start

                # Build new times for p in (S..E]
                new_section_times = {}
                for p in range(S + 1, E + 1):
                    curr_val = self.current_race_data.get(str(p), "0000000")
                    if curr_val == "0000000":
                        # If current race missing this percent, try to interpolate linearly within section
                        # fallback to previous value in new_section_times or to ghost value
                        if new_section_times:
                            last_p = max(new_section_times.keys())
                            new_section_times[p] = new_section_times[last_p]
                        else:
                            new_section_times[p] = split_times_int.get(str(p), split_times_int.get(str(S)))
                    else:
                        new_section_times[p] = int(curr_val) + offset

                new_section_end = new_section_times.get(E, None)
                if new_section_end is None:
                    continue

                # Amount we will reduce later times by
                time_reduction = ghost_end - new_section_end

                # Apply new section times into split_times_int
                for p, t in new_section_times.items():
                    split_times_int[str(p)] = t

                # Shift all subsequent times (percent > E) by subtracting time_reduction
                if time_reduction != 0:
                    for p in range(E + 1, 101):
                        if str(p) in split_times_int:
                            split_times_int[str(p)] = max(0, split_times_int[str(p)] - time_reduction)

                changed = True

        if changed:
            # Save back into self.split_times as zero-padded 7-digit strings
            for k in split_times_int:
                self.split_times[k] = f"{split_times_int[k]:07d}"
            print("Split times updated with current race best sections")
            return True

        return False
    
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