"""
Race Data Management Module

This module handles saving and loading race ghost data for timing comparisons.
"""

import json
import os
import numpy as np
from typing import Dict, Optional, List
from .utils.paths import get_app_root


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
        # Velocity data (recorded alongside progress/time)
        self.current_velocity_data: Optional[np.ndarray] = None
        self.ghost_velocity_data: Optional[np.ndarray] = None
        self.split_velocities: Optional[list] = None  # parallel to split_progress, may contain NaN
        # Split-file related data
        self.current_splits: Optional[list] = None # contains the RAW time values at which each of the current splits are recorded
        self.best_splits: Optional[list] = None # contains the DURATION of the best splits in the loaded ghost
        self.ghost_splits: Optional[list] = None # contains the DURATION of the splits in the loaded ghost
        self.splits: Optional[list] = None  # list of [string name, float progress] lists
        self.split_progress: Optional[np.ndarray] = None
        self.split_times: Optional[np.ndarray] = None
        self.is_split_loaded: bool = False
        self.next_split_index: Optional[float] = None  # index of the next split
        self.new_split_available: bool = False
        # Ensure runs/ directory exists
        self.runs_dir = os.path.join(get_app_root(), "runs")
        os.makedirs(self.runs_dir, exist_ok=True)
        # Initialize empty race data for all percentages (0-100)
        self.reset_race_data()
    
    def reset_race_data(self):
        """Reset the current race data to empty."""
        self.current_progress_data = np.array([0.0])
        self.current_time_data = np.array([0])
        self.current_velocity_data = np.array([0.0])
        self.current_splits = []
        self.next_split_index = 0

    
    def data_exists(self) -> bool:
        """Check if any race data has been recorded for the current race."""
        return self.current_time_data is not None and len(self.current_time_data) > 1 and not self.no_new_data
    
    def record_time_at_progress(self, progress: float, time_us: int, velocity: float = 0.0):
        """
        Record a time at a specific percentage.
        
        Args:
            progress: Race progress 0.0-1.0
            time_us: Time in microseconds
            velocity: Raw velocity in m/s at this point
        """
        if 0 <= progress <= 1:
            # 0% is always 0ms by definition
            
            # Validate: 00.00.000 (0000000) can only be at 0%
            if time_us == 0 and progress != 0:
                print(f"Warning: Ignoring invalid time 00.00.000 at {round(progress*100,2)}% (can only be at 0%)")
                return
            if self.splits is not None and progress >= self.splits[self.next_split_index][1]:
                self.handle_split_reached(progress, time_us, velocity)
            self.current_progress_data = np.append(self.current_progress_data, progress)
            self.current_time_data = np.append(self.current_time_data, time_us)
            self.current_velocity_data = np.append(self.current_velocity_data, velocity)
            self.no_new_data = False
    
    def record_final_time(self, time_us: int, velocity: float = 0.0):
        """
        Record the final time at 100% when race completes.
        Ensures the 100% time is never lower than the 99% time.
        
        Args:
            time_us: Final time in microseconds (10 digits, padded with zeros)
            velocity: Raw velocity in m/s at finish
        """
        
        if self.splits is not None:
            self.handle_split_reached(1.0, time_us, velocity)
        else:
            self.current_progress_data = np.append(self.current_progress_data, 1.0)
            self.current_time_data = np.append(self.current_time_data, time_us)
            self.current_velocity_data = np.append(self.current_velocity_data, velocity)
        print(f"Recorded final time at 100%: {time_us}us")
        self.best_splits = self.get_ghost_splits()
        self.new_split_available = True
        self.no_new_data = False
    
    def save_split_data(self) -> bool:
        """
        Save the current split ghost back to JSON. Only updates the
        'split_progress', 'split_times', and 'split_velocities' fields,
        leaving everything else in the file exactly as it was saved before.
        Returns True on success.
        """
        try:
            target = self.ghost_filename
            if not target:
                print("No target filepath provided to save split data")
                return False

            # Read the existing file so we preserve all other fields
            try:
                with open(target, 'r') as f:
                    existing = json.load(f)
            except Exception:
                existing = {}

            def _nan_to_none(lst):
                return [None if (isinstance(v, float) and v != v) else v for v in lst]

            # Only overwrite the three split fields
            existing["split_progress"] = self.split_progress.tolist() if self.split_progress is not None else self.current_progress_data.tolist()
            existing["split_times"] = self.split_times.tolist() if self.split_times is not None else self.current_time_data.tolist()
            existing["split_velocities"] = _nan_to_none(self.split_velocities) if self.split_velocities is not None else None

            with open(target, 'w') as f:
                json.dump(existing, f, indent=2)

            return True
        except Exception as e:
            print(f"Error saving split data: {e}")
            return False

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
            def _nan_to_none(lst):
                return [None if (isinstance(v, float) and v != v) else v for v in lst]
            cur_vels = self.current_velocity_data.tolist() if self.current_velocity_data is not None else None
            race_data = {
                "fingerprint": "ALU_TOOL",
                "progress": self.current_progress_data.tolist(),
                "times": self.current_time_data.tolist(),
                "velocities": cur_vels,
                "split_progress": self.split_progress.tolist() if self.is_split_loaded else self.current_progress_data.tolist(),
                "split_times": self.split_times.tolist() if self.is_split_loaded else self.current_time_data.tolist(),
                "split_velocities": (_nan_to_none(self.split_velocities) if self.is_split_loaded and self.split_velocities is not None else cur_vels),
                "splits": self.splits if self.splits is not None else None,
            }
            
            # Ensure filename has .json extension
            if not filename.endswith('.json'):
                filename += '.json'
            
            # Build full path in runs/ folder
            filepath = os.path.join(self.runs_dir, os.path.basename(filename))

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
            if not self._validate_split_file(data):
                return False
            
            self.ghost_progress_data = np.array(data['progress'])
            self.ghost_time_data = np.array(data['times'])
            # Velocity data — non-fatal if absent (older ghost files)
            raw_vel = data.get('velocities')
            if raw_vel is not None and isinstance(raw_vel, list):
                self.ghost_velocity_data = np.array(
                    [float('nan') if v is None else float(v) for v in raw_vel], dtype=float
                )
            else:
                self.ghost_velocity_data = None
            self.split_progress = np.array(data['split_progress']) if 'split_progress' in data else None
            self.split_times = np.array(data['split_times']) if 'split_times' in data else None
            raw_split_vel = data.get('split_velocities')
            if raw_split_vel is not None and isinstance(raw_split_vel, list):
                self.split_velocities = [float('nan') if v is None else float(v) for v in raw_split_vel]
            else:
                self.split_velocities = None
            self.splits = data['splits'] if 'splits' in data else None
            self.is_split_loaded = self.split_progress is not None and self.split_times is not None
            self.best_splits =  self.get_ghost_splits()
            self.ghost_splits = self.get_ghost_splits(False)
            self.ghost_filename = filepath
            if self.best_splits is not None:
                self.new_split_available = True
            return True
            
        except Exception as e:
            print(f"Error loading ghost data: {e}")
            return False
    
    def get_ghost_splits(self, best: bool = True) -> Optional[list]:
        """
        Return the list of ghost splits for this race.
        """
        times = self.split_times if best else self.ghost_time_data
        progress = self.split_progress if best else self.ghost_progress_data
        try:
            ghost_split_times = []
            ghost_split_times.append(int(times[progress == self.splits[0][1]][0]))
            print(self.splits)
            print("First ghost split time:", ghost_split_times[0])
            for i in range(len(self.splits)-1):
                prev = self.splits[i]
                current = self.splits[i+1]
                timestart = int(times[progress == prev[1]][0])
                timeend = int(times[progress == current[1]][0])
                ghost_split_times.append(timeend - timestart)
            print("Calculated ghost splits:", ghost_split_times)
            return ghost_split_times
        except Exception as e:
            print(f"Error calculating ghost splits: {e}")
            return None

    def save_current_split(self):
        """
        Save the current split times into the split_times array, replacing the old split time for the split that was just reached.
        Also updates the split_progress and splits arrays to ensure they are consistent with the new split times.
        """
        new_split = self.splits[self.next_split_index][1]
        if self.next_split_index == 0:
            prog_beginning = [0.0]
            times_beginning = [0]
            vels_beginning = [0.0]
            prev_split = 0.0
        else:
            prev_split = self.splits[self.next_split_index-1][1]
            prog_beginning = self.split_progress[(self.split_progress <= prev_split)]
            times_beginning = self.split_times[(self.split_progress <= prev_split)]
            if self.split_velocities is not None:
                sv = np.array(self.split_velocities, dtype=float)
                vels_beginning = list(sv[self.split_progress <= prev_split])
            else:
                vels_beginning = [float('nan')] * len(prog_beginning)
        # set prog_middle to the progress values between the previous split and the new split, and times_middle to the corresponding times from current_time_data, offset by the difference between the old split time and the new split time
        mask_mid = (self.current_progress_data > prev_split) & (self.current_progress_data <= new_split)
        prog_middle = self.current_progress_data[mask_mid]
        times_middle = self.current_time_data[mask_mid]
        vels_middle = self.current_velocity_data[mask_mid] if self.current_velocity_data is not None else np.full(len(prog_middle), float('nan'))
        print(prev_split,new_split,len(prog_middle), len(times_middle), len(self.current_progress_data), len(self.current_time_data))
        offset = times_beginning[len(prog_beginning)-1] - self.current_splits[self.next_split_index-1] if self.next_split_index > 0 else 0
        times_middle = np.add(times_middle, offset)
        # velocities don't need the time offset — they are instantaneous values
        if self.next_split_index == len(self.splits) - 1:
            prog_end = []
            times_end = []
            vels_end = []
        else:
            prog_end = self.split_progress[(self.split_progress > new_split)]
            times_end = self.split_times[(self.split_progress > new_split)]
            offset = times_middle[len(times_middle)-1] - self.split_times[(self.split_progress == new_split)][0]
            times_end = np.add(times_end, offset)
            if self.split_velocities is not None:
                sv = np.array(self.split_velocities, dtype=float)
                vels_end = list(sv[self.split_progress > new_split])
            else:
                vels_end = [float('nan')] * len(prog_end)
        self.split_times = np.concatenate((times_beginning, times_middle, times_end))
        self.split_progress = np.concatenate((prog_beginning, prog_middle, prog_end))
        self.split_velocities = list(vels_beginning) + list(vels_middle) + list(vels_end)
        self.save_split_data()
        self.best_splits = self.get_ghost_splits()

    def handle_split_reached(self, progress: float, time_us: int, velocity: float = 0.0):
        """
        Handle logic for when the next split is reached during a race.
        """
        split_prog = self.splits[self.next_split_index][1]
        prev_progress = float(self.current_progress_data[-1])
        prev_time = float(self.current_time_data[-1])
        prev_velocity = float(self.current_velocity_data[-1]) if self.current_velocity_data is not None else 0.0
        # Interpolate time at exact split position
        time_at_new_split = round(np.interp(split_prog,
                                            np.array([prev_progress, progress]),
                                            np.array([prev_time, float(time_us)])))
        # Linearly interpolate velocity at exact split position
        if progress != prev_progress:
            frac = (split_prog - prev_progress) / (progress - prev_progress)
            vel_at_split = prev_velocity + frac * (velocity - prev_velocity)
        else:
            vel_at_split = velocity
        self.current_progress_data = np.append(self.current_progress_data, split_prog)
        self.current_time_data = np.append(self.current_time_data, time_at_new_split)
        self.current_velocity_data = np.append(self.current_velocity_data, vel_at_split)
        try: total_time = time_at_new_split - self.current_splits[self.next_split_index-1]
        except: total_time = time_at_new_split
        self.current_splits.append(time_at_new_split)
        if self.is_split_loaded:
            if total_time < self.best_splits[self.next_split_index]:
                self.save_current_split()
        self.new_split_available = True
        self.next_split_index += 1

    def _validate_split_file(self, data: dict) -> bool:
        """
        Validate split file structure. Requires same fingerprint and times as ghost file,
        plus `splits` and `split_times` fields. Enforces 1-20 splits and last split == 99.
        """
        # Must be a valid ghost file at minimum
        if data.get('fingerprint') != 'ALU_TOOL':
            print("Invalid split file: Missing or incorrect fingerprint")
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
        
        raw_splits = data.get('splits')
        if raw_splits is not None and not (2 <= len(raw_splits) <= 10):
            print("File does not contain split configuration with 2-10 splits")
            return False
        
        split_progress = data.get('split_progress')
        if not isinstance(split_progress, list):
            print("File does not contain split_progress")
            return True

        split_times = data.get('split_times')
        if not isinstance(split_times, list):
            print("File does not contain split_times")
            return True

        return True

    def is_split_file_loaded(self) -> bool:
        """Return True if a split file is currently loaded."""
        return self.is_split_loaded

    def get_splits(self) -> Optional[list]:
        """Return normalized splits list or None."""
        return self.splits, self.current_splits, self.best_splits, self.ghost_splits
    
    def get_split_sums(self) -> tuple:
        """Return the cumulative sums of the current splits and best splits."""
        ghost_sum = self.ghost_time_data[-1] if self.ghost_time_data is not None and len(self.ghost_time_data) > 0 else None
        best_sum = self.split_times[-1] if self.split_times is not None and len(self.split_times) > 0 else None
        return ghost_sum, best_sum

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
        Uses Hermite spline interpolation when ghost velocity data is available,
        otherwise falls back to linear interpolation.
        
        Returns:
            Delta in seconds (positive = behind ghost, negative = ahead of ghost) or None
        """
        if not self.ghost_time_data.any() or not self.ghost_progress_data.any():
            return None
        max_prog = float(self.ghost_progress_data[-1])
        if not (0 <= progress <= max_prog):
            return None
        try:
            if (self.ghost_velocity_data is not None
                    and len(self.ghost_velocity_data) == len(self.ghost_progress_data)):
                ghost_time = self._hermite_interp_time(
                    progress, self.ghost_progress_data, self.ghost_time_data, self.ghost_velocity_data
                )
            else:
                ghost_time = float(np.interp(progress, self.ghost_progress_data, self.ghost_time_data))
            delta_us = current_time_us - ghost_time
            return delta_us / 1_000_000.0
        except (ValueError, TypeError):
            return None
    
    def is_new_split_available(self, override: bool = False) -> bool:
        """Check if a new split has been reached that hasn't been recorded yet."""
        if self.new_split_available:
            self.new_split_available = False
            return True
        elif override:
            return True
        return False
    def get_ghost_velocity_at_progress(self, progress: float) -> Optional[float]:
        """Return the ghost velocity (m/s) linearly interpolated at the given progress.
        Returns None if no velocity data is available or progress is out of range.
        """
        if self.ghost_velocity_data is None or self.ghost_progress_data is None:
            return None
        if len(self.ghost_velocity_data) != len(self.ghost_progress_data):
            return None
        valid = ~np.isnan(self.ghost_velocity_data)
        if not valid.any():
            return None
        prog_v = self.ghost_progress_data[valid]
        vel_v = self.ghost_velocity_data[valid]
        if len(prog_v) < 1 or progress < float(prog_v[0]) or progress > float(prog_v[-1]):
            return None
        return float(np.interp(progress, prog_v, vel_v))

    def _hermite_interp_time(
        self,
        progress: float,
        prog_arr: np.ndarray,
        time_arr: np.ndarray,
        vel_arr: np.ndarray,
    ) -> float:
        """Estimate time at progress using a Hermite cubic spline.

        Velocity is used as the tangent slope proxy: dt/dp ∝ 1/velocity,
        meaning faster sections advance through progress more quickly.
        Falls back to linear interpolation for segments where velocity data is
        invalid (NaN) or too close to zero.
        """
        if len(prog_arr) < 2:
            return float(np.interp(progress, prog_arr, time_arr))

        # Find enclosing segment [idx, idx+1]
        idx = int(np.searchsorted(prog_arr, progress, side='right')) - 1
        idx = max(0, min(idx, len(prog_arr) - 2))

        p0, p1 = float(prog_arr[idx]), float(prog_arr[idx + 1])
        t0, t1 = float(time_arr[idx]), float(time_arr[idx + 1])
        v0 = float(vel_arr[idx])
        v1 = float(vel_arr[idx + 1])

        dp = p1 - p0
        if dp <= 0:
            return t0

        # Fall back to linear for NaN or near-zero velocities
        if v0 != v0 or v1 != v1 or v0 < 0.1 or v1 < 0.1:  # v != v is True only for NaN
            return float(np.interp(progress, prog_arr, time_arr))

        # Tangents: dt/dp ∝ 1/v, scaled so ∫dt ≈ t1-t0 over [p0, p1]
        # Trapezoidal estimate: (1/v0 + 1/v1)/2 * k * dp = t1-t0
        #   => k = (t1-t0) * 2 / ((1/v0 + 1/v1) * dp)
        inv_sum = 1.0 / v0 + 1.0 / v1
        k = (t1 - t0) * 2.0 / (inv_sum * dp)
        m0 = k / v0   # tangent (dt/dp) at p0
        m1 = k / v1   # tangent (dt/dp) at p1

        u = (progress - p0) / dp
        u2 = u * u
        u3 = u2 * u

        # Cubic Hermite basis
        h00 =  2*u3 - 3*u2 + 1
        h10 =    u3 - 2*u2 + u
        h01 = -2*u3 + 3*u2
        h11 =    u3 -   u2

        return h00*t0 + h10*m0*dp + h01*t1 + h11*m1*dp

    def is_ghost_loaded(self) -> bool:
        """Check if a ghost is currently loaded."""
        return self.ghost_time_data is not None and self.ghost_progress_data is not None
    
    def get_ghost_filename(self) -> Optional[str]:
        """Get the filename of the currently loaded ghost."""
        return os.path.splitext(os.path.basename(self.ghost_filename))[0]
    
    def unload_ghost(self):
        """Unload the current ghost data and all associated split configuration."""
        self.ghost_time_data = None
        self.ghost_progress_data = None
        self.ghost_velocity_data = None
        self.ghost_filename = None
        self.splits = None
        self.split_progress = None
        self.split_times = None
        self.split_velocities = None
        self.best_splits = None
        self.ghost_splits = None
        self.is_split_loaded = False