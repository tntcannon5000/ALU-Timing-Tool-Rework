"""
Cheat Engine Client Module (File-based IPC)

Reads game telemetry values from a shared temp file
written by the Cheat Engine Lua bridge script.

File path: %TEMP%\\alu_ce_bridge.dat
Format:    "timer|progress|rpm|gear|rpmRaw|cp|visualTimer"
"""

import os
import threading
import time
from typing import Tuple, Optional


# Shared file location — must match ce_server.lua
_DATA_FILE = os.path.join(os.environ.get("TEMP", "."), "alu_ce_bridge.dat")


class CheatEngineClient:
    """
    Polls a shared temp file written by the CE Lua bridge and
    provides thread-safe access to the latest game values.
    """

    def __init__(self, data_file: str = _DATA_FILE, poll_interval: float = 0.002):
        """
        Args:
            data_file:     Path to the bridge file (default %TEMP%\\alu_ce_bridge.dat)
            poll_interval: Seconds between file reads (default 2 ms → 500 Hz)
        """
        self.data_file = data_file
        self.poll_interval = poll_interval

        # Thread control
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._stop_event = threading.Event()

        # Latest values (guarded by lock)
        self._lock = threading.Lock()
        self._timer_raw: int = 0
        self._progress_raw: float = 0.0
        self._rpm: int = 0
        self._gear: int = 0
        self._checkpoint: int = 0
        self._visual_timer: int = 0      # RSI-based timer (active outside race too)
        self._connected: bool = False        # True once we've read the file at least once
        self._last_receive_time: float = 0.0

        # Stats
        self.reads_ok: int = 0
        self.reads_failed: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self):
        """Start the background file-polling thread."""
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._thread.start()
        print(f"[CE Client] Started — polling {self.data_file}")

    def stop(self):
        """Stop the polling thread."""
        if not self._running:
            return
        self._running = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        print("[CE Client] Stopped")

    def get_values(self) -> Tuple[int, float]:
        """
        Thread-safe read of latest values.

        Returns:
            (timer_raw, progress_raw)
        """
        with self._lock:
            return self._timer_raw, self._progress_raw

    def get_visual_timer(self) -> int:
        """
        Return the visual timer value (ms).
        Active even outside of a race — useful for race-state detection.
        """
        with self._lock:
            return self._visual_timer

    def get_rpm(self) -> int:
        """Return the current RPM (integer)."""
        with self._lock:
            return self._rpm

    def get_gear(self) -> int:
        """Return the current gear."""
        with self._lock:
            return self._gear

    def get_checkpoint(self) -> int:
        """Return the current checkpoint value."""
        with self._lock:
            return self._checkpoint

    def get_all_values(self) -> dict:
        """Return all telemetry values as a dict."""
        with self._lock:
            return {
                "timer_raw": self._timer_raw,
                "progress": self._progress_raw,
                "rpm": self._rpm,
                "gear": self._gear,
                "checkpoint": self._checkpoint,
                "visual_timer": self._visual_timer,
            }

    def get_timer_ms(self) -> int:
        """Return the timer value converted to milliseconds (raw is microseconds)."""
        with self._lock:
            return self._timer_raw // 1000

    def get_progress_percent(self) -> int:
        """
        Return progress as an integer percentage 0-100.
        Handles both 0-1 and 0-100 ranges from the game.
        """
        with self._lock:
            val = self._progress_raw
        if 0.0 <= val <= 1.0:
            return int(round(val * 100))
        return int(round(val))

    def is_connected(self) -> bool:
        with self._lock:
            return self._connected

    def get_stats(self) -> dict:
        with self._lock:
            return {
                "ce_connected": self._connected,
                "ce_reads_ok": self.reads_ok,
                "ce_reads_failed": self.reads_failed,
                "visual_timer": self._visual_timer,
                "rpm": self._rpm,
                "gear": self._gear,
                "checkpoint": self._checkpoint,
            }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _reader_loop(self):
        """Background loop: poll the shared file."""
        warned = False
        while self._running and not self._stop_event.is_set():
            try:
                with open(self.data_file, "r") as f:
                    line = f.read().strip()

                if line:
                    self._parse_line(line)
                    if not warned:
                        pass  # all good
                    warned = False

            except FileNotFoundError:
                if not warned:
                    print("[CE Client] Waiting for CE bridge file...")
                    warned = True
                with self._lock:
                    self._connected = False
            except (OSError, PermissionError):
                # File being written to — skip this cycle
                self.reads_failed += 1

            self._stop_event.wait(timeout=self.poll_interval)

    def _parse_line(self, line: str):
        """Parse a 'timer|progress|rpm|gear|rpmRaw|cp|visualTimer' line."""
        try:
            parts = line.split("|")
            if len(parts) >= 2:
                timer_val = int(parts[0])
                progress_val = float(parts[1])
                rpm_val = int(parts[2]) if len(parts) >= 3 else 0
                gear_val = int(parts[3]) if len(parts) >= 4 else 0
                # parts[4] = rpmRaw (float) — skipped, we use integer RPM
                cp_val = int(parts[5]) if len(parts) >= 6 else 0
                vt_val = int(parts[6]) if len(parts) >= 7 else 0
                with self._lock:
                    self._timer_raw = timer_val
                    self._progress_raw = progress_val
                    self._rpm = rpm_val
                    self._gear = gear_val
                    self._checkpoint = cp_val
                    self._visual_timer = vt_val
                    self._connected = True
                    self._last_receive_time = time.time()
                self.reads_ok += 1
        except (ValueError, IndexError):
            self.reads_failed += 1
