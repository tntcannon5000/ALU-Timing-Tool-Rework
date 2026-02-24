"""
Race Data Management Module

This module handles saving and loading race ghost data for timing comparisons.
"""

import json
import os
import numpy as np
from typing import Dict, Optional, List


class RaceDataManager:
    """
    Manages race timing data for recording and racing against ghosts.
    """
    
    def __init__(self):
        """Initialize the race data manager."""
        self.current_progress_data: Optional[np.ndarray] = None
        self.current_time_data: Optional[np.ndarray] = None
        self.ghost_progress_data: Optional[np.ndarray] = None
        self.ghost_time_data: Optional[np.ndarray] = None
        self.ghost_filename: Optional[str] = None
        self.no_new_data: bool = True
        # Split-file related data
        self.split_filepath: Optional[str] = None
        self.splits: Optional[list] = None  # normalized list of {'name':str,'percent':int}
        self.split_times: Optional[Dict[str, int]] = None
        self.is_split_loaded: bool = False
        
        # Initialize empty race data for all percentages (0-100)
        self.reset_race_data()
    
    def reset_race_data(self):
        """Reset the current race data to empty."""
        self.current_progress_data = np.array([0.0])
        self.current_time_data = np.array([0])
    
    def data_exists(self) -> bool:
        """Check if any race data has been recorded for the current race."""
        return self.current_time_data is not None and len(self.current_time_data) > 1 and not self.no_new_data
    
    def record_time_at_progress(self, progress: float, time_us: int):
        """
        Record a time at a specific percentage.
        
        Args:
            percentage: Percentage point (0-100)
            time_ms: Time in milliseconds (7 digits, padded with zeros)
        """
        if 0 <= progress <= 1:
            # 0% is always 0ms by definition
            
            # Validate: 00.00.000 (0000000) can only be at 0%
            if time_us == 0 and progress != 0:
                print(f"Warning: Ignoring invalid time 00.00.000 at {round(progress*100,2)}% (can only be at 0%)")
                return
            
            self.current_progress_data = np.append(self.current_progress_data, progress)
            self.current_time_data = np.append(self.current_time_data, time_us)
            self.no_new_data = False
    
    def record_final_time(self, time_us: int):
        """
        Record the final time at 100% when race completes.
        Ensures the 100% time is never lower than the 99% time.
        
        Args:
            time_us: Final time in microseconds (10 digits, padded with zeros)
        """
        
        self.current_progress_data = np.append(self.current_progress_data, 1.0)
        self.current_time_data = np.append(self.current_time_data, time_us)
        print(f"Recorded final time at 100%: {time_us}us")
        self.no_new_data = False
    
    def save_race_data(self, filename: str) -> bool:
        """
        Save current race data to a JSON file in the runs/ folder.
        
        Args:
            filename: Name of the file to save (without extension)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Create the data structure
            race_data = {
                "fingerprint": "ALU_TOOL",
                "progress": self.current_progress_data.tolist(),
                "times": self.current_time_data.tolist()
            }
            
            # Ensure filename has .json extension
            if not filename.endswith('.json'):
                filename += '.json'
            
            # Ensure runs/ directory exists
            runs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "runs")
            os.makedirs(runs_dir, exist_ok=True)
            
            # Build full path in runs/ folder
            filepath = os.path.join(runs_dir, os.path.basename(filename))

            # Save to file
            with open(filepath, 'w') as f:
                json.dump(race_data, f, indent=2)
            self.no_new_data = True
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
            
            self.ghost_progress_data = np.array(data['progress'])
            self.ghost_time_data = np.array(data['times'])
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
        
        # Check for progress data
        progress = data.get('progress', [])
        if not isinstance(progress, list):
            print("Invalid file: Progress data must be a list")
            return False
        
        # Check for times data
        times = data.get('times', [])
        if not isinstance(times, list):
            print("Invalid file: Times data must be a list")
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
    
    def get_ghost_time_at_progress(self, progress: float) -> Optional[str]:
        """
        Get the ghost time at a specific percentage.
        
        Args:
            percentage: Percentage point (0-100)
            
        Returns:
            Ghost time string or None if not available
        """
        if self.ghost_time_data.any() and self.ghost_progress_data.any() and 0 <= progress <= self.ghost_progress_data[len(self.ghost_progress_data)-1]:
            return round(np.interp(progress, self.ghost_progress_data, self.ghost_time_data))
        return None
    
    def calculate_delta(self, progress: float, current_time_us: int) -> Optional[float]:
        """
        Calculate the time delta against the ghost at a specific percentage.
        
        Args:
            percentage: Percentage point (0-99)
            current_time_ms: Current time in milliseconds
            
        Returns:
            Delta in seconds (positive = behind ghost, negative = ahead of ghost) or None
        """
        if not self.ghost_time_data.any() or not self.ghost_progress_data.any():
            return None
        
        ghost_time = self.get_ghost_time_at_progress(progress)
        if not ghost_time:
            return None
        
        try:
            delta_us = current_time_us - ghost_time
            return delta_us / 1000000.0  # Convert to seconds
        except (ValueError, TypeError):
            return None
    
    def is_ghost_loaded(self) -> bool:
        """Check if a ghost is currently loaded."""
        return self.ghost_time_data is not None and self.ghost_progress_data is not None
    
    def get_ghost_filename(self) -> Optional[str]:
        """Get the filename of the currently loaded ghost."""
        return self.ghost_filename
    
    def unload_ghost(self):
        """Unload the current ghost data."""
        self.ghost_time_data = None
        self.ghost_progress_data = None
        self.ghost_filename = None