"""
Cheat Engine Client — File-Based IPC Reader (v2)

Reads game telemetry from a shared bridge file written by the
Cheat Engine Lua bridge (ALU_Trainer_v2.4.CT).

File:   %TEMP%\\alu_ce_bridge.dat
Format: Fixed-size 128-byte null-padded payload containing:
        "timer|progress|rpm|gear|rpmRaw|cp|visualTimer"

The CE side writes in-place (no truncation after initial creation)
so this reader never sees an empty file during normal operation.
Transient read failures (locked file, partial read) are silently
tolerated — the last good values are retained.
"""

import os
import time
import threading
from typing import Optional, Tuple


_DATA_FILE = os.path.join(os.environ.get("TEMP", "."), "alu_ce_bridge.dat")
_READ_SIZE = 128  # Must match ALU_PAD_SIZE in CT Lua bridge


class CheatEngineClient:
    """
    Polls the CE bridge file and exposes the latest telemetry values
    via thread-safe accessors.
    """

    def __init__(self, data_file: str = _DATA_FILE, poll_interval: float = 0.001):
        self.data_file = data_file
        self.poll_interval = poll_interval

        # Thread control
        self._thread: Optional[threading.Thread] = None
        self._running = False

        # Latest values (protected by _lock)
        self._lock = threading.Lock()
        self._timer_raw: int = 0
        self._progress_raw: float = 0.0
        self._rpm: int = 0
        self._gear: int = 0
        self._checkpoint: int = 0
        self._visual_timer: int = 0
        self._connected: bool = False
        self._last_ok: float = 0.0

        # Counters
        self.reads_ok: int = 0
        self.reads_failed: int = 0
        self._last_fail_reason: str = ""

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        """Start the background polling thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        print(f"[CE Client] Started — polling {self.data_file}")

    def stop(self):
        """Stop the polling thread."""
        if not self._running:
            return
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None
        print("[CE Client] Stopped")

    # ------------------------------------------------------------------
    # Accessors (thread-safe)
    # ------------------------------------------------------------------

    def get_values(self) -> Tuple[int, float]:
        with self._lock:
            return self._timer_raw, self._progress_raw

    def get_all_values(self) -> dict:
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
        with self._lock:
            return self._timer_raw // 1000

    def get_progress_percent(self) -> int:
        with self._lock:
            v = self._progress_raw
        return int(round(v * 100)) if 0.0 <= v <= 1.0 else int(round(v))

    def get_visual_timer(self) -> int:
        with self._lock:
            return self._visual_timer

    def get_rpm(self) -> int:
        with self._lock:
            return self._rpm

    def get_gear(self) -> int:
        with self._lock:
            return self._gear

    def get_checkpoint(self) -> int:
        with self._lock:
            return self._checkpoint

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
    # Internal — polling loop
    # ------------------------------------------------------------------

    def _poll_loop(self):
        """
        Background reader.

        Key design choices:
          - Opens the file in shared binary mode ("rb"), reads exactly
            _READ_SIZE bytes, strips null padding, parses the payload.
          - On ANY failure (file missing, OS lock, empty, partial,
            parse error) the loop simply retains the last good values
            and goes to the next cycle — no logging, no state change.
          - Only logs a warning after 2+ consecutive seconds of failure
            so the console isn't flooded.
          - Logs recovery once after a warning clears.
        """
        warned = False
        last_good = time.monotonic()
        first_read_logged = False
        log_interval = 5.0  # periodic status every 5s
        last_status_log = time.monotonic()

        # Check if file exists at startup
        if os.path.exists(self.data_file):
            sz = os.path.getsize(self.data_file)
            print(f"[CE Client] Bridge file exists ({sz} bytes)")
        else:
            print(f"[CE Client] Bridge file not found — waiting for CE to create it")

        while self._running:
            ok = self._try_read()

            if ok:
                last_good = time.monotonic()
                if not first_read_logged:
                    with self._lock:
                        vals = (f"timer={self._timer_raw}, progress={self._progress_raw}, "
                                f"gear={self._gear}, vt={self._visual_timer}, "
                                f"cp={self._checkpoint}, rpm={self._rpm}")
                    print(f"[CE Client] First successful read: {vals}")
                    first_read_logged = True
                if warned:
                    print("[CE Client] Bridge file recovered — connected")
                    warned = False
            else:
                gap = time.monotonic() - last_good
                if gap > 2.0 and not warned:
                    print("[CE Client] Waiting for CE bridge file...")
                    warned = True
                    with self._lock:
                        self._connected = False

            # Periodic status log
            now = time.monotonic()
            if now - last_status_log >= log_interval:
                with self._lock:
                    conn = self._connected
                print(f"[CE Client] Status: connected={conn}, reads_ok={self.reads_ok}, reads_failed={self.reads_failed}")
                last_status_log = now

            time.sleep(self.poll_interval)

    def _try_read(self) -> bool:
        """
        Attempt one read cycle.  Returns True if a valid payload was parsed.
        """
        try:
            with open(self.data_file, "rb") as fh:
                raw = fh.read(_READ_SIZE)
        except FileNotFoundError:
            self._last_fail_reason = "file_not_found"
            return False
        except (OSError, PermissionError) as e:
            self._last_fail_reason = f"os_error: {e}"
            return False

        if not raw:
            self._last_fail_reason = "empty_read"
            return False

        # Strip null-padding bytes from fixed-size payload
        raw = raw.rstrip(b"\x00")
        if not raw:
            self._last_fail_reason = "all_nulls"
            return False

        try:
            line = raw.decode("utf-8", errors="replace").strip()
        except Exception:
            self._last_fail_reason = "decode_error"
            return False

        if not line:
            self._last_fail_reason = "empty_line"
            return False

        return self._parse(line)

    def _parse(self, line: str) -> bool:
        """Parse 'timer|progress|rpm|gear|rpmRaw|cp|visualTimer'."""
        try:
            parts = line.split("|")
            if len(parts) < 2:
                return False
            t = int(parts[0])
            p = float(parts[1])
            rpm = int(parts[2]) if len(parts) >= 3 else 0
            gear = int(parts[3]) if len(parts) >= 4 else 0
            # parts[4] = rpmRaw (float) — unused, we use integer RPM
            cp = int(parts[5]) if len(parts) >= 6 else 0
            vt = int(parts[6]) if len(parts) >= 7 else 0

            with self._lock:
                self._timer_raw = t
                self._progress_raw = p
                self._rpm = rpm
                self._gear = gear
                self._checkpoint = cp
                self._visual_timer = vt
                self._connected = True
                self._last_ok = time.time()

            self.reads_ok += 1
            return True
        except (ValueError, IndexError):
            self.reads_failed += 1
            return False
