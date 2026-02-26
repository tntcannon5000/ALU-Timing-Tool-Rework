"""
Main Timer Application — Direct Memory Backend (v5 pymem)

Reads game telemetry by directly hooking game memory via data_extractor.py.
No Cheat Engine required.

Compared to timer_v5_CE.py the only substantive differences are:
  1. CheatEngineClient → DataExtractor
  2. Main loop: vals = self.de_client.read()
                if vals is False: sleep + continue  (skip unchanged ticks)
     All race logic is identical.

Prerequisites:
  1. Asphalt 9 (Steam x64) running
  2. Run this app — it attaches to the process automatically
"""

import time as systime
import threading
from collections import deque
from typing import Optional

from src.modules import (
    TimingToolUI,
    RaceDataManager,
    DataExtractor,
)


class ALUTimingTool:
    """
    Main application class for the ALU Timing Tool (pymem direct-memory backend).

    Reads game telemetry by directly hooking and reading Asphalt 9 process
    memory via DataExtractor, then drives the full race-tracking pipeline:
    state detection, timing, ghost deltas, finish detection, and save prompts.
    """

    def __init__(self):
        """Initialize the ALU Timing Tool with direct memory reader."""
        # Core components
        self.race_data_manager = RaceDataManager()
        self.ui = TimingToolUI(self.race_data_manager)
        self.de_client = DataExtractor()

        # Lifecycle
        self.capturing: bool = True
        self.shutdown_in_progress: bool = False

        # Race state
        self.race_in_progress: bool = False
        self.race_completed: bool = False
        self.reached_high_progress: bool = False  # True once pct >= 98

        # Timer & progress
        self.current_timer_us: int = 0
        self.current_timer_display: str = "00:00.000"
        self.percentage: str = "0%"
        self.last_captured_timer_us: int = 0
        self.estimated_finish_us: Optional[int] = None
        self.last_valid_delta: str = "--.---"

        # Finish detection (progress/timer stall method)
        self._finish_locked: bool = False
        self._final_timer_us: int = 0   # last timer while racing ("true final")

        # Guard against stale progress: memory keeps 100% from race N-1.
        # Only allow finish detection once we've seen progress < 50% this race.
        self._progress_legitimized: bool = False

        # Change-detection trackers
        self._prev_timer_us: int = 0
        self._prev_progress: float = 0.0

        # Performance tracking
        self.loop_times: deque = deque(maxlen=30)
        self.avg_loop_time: float = 0.0
        self.total_loops: int = 0

        # UI throttling
        self.last_ui_update: float = 0.0
        self.ui_update_interval: float = 1.0 / 48.0  # ~48 fps

        # Setup UI callbacks
        self.ui.set_callbacks(
            on_mode_change=self._on_mode_change,
            on_load_ghost=self._on_load_ghost,
            on_load_split=self._on_load_split,
            on_configure_splits=self._on_configure_splits,
            on_save_ghost=self._on_save_ghost,
            on_save_race=self._on_save_race,
            on_close=self._shutdown_all_threads,
        )

        # Start UI thread
        self.ui_thread = self.ui.start_ui_thread()

        # Start DataExtractor (attempts eager attach + VT hook install)
        self.de_client.start()
        print("ALU Timing Tool (pymem backend) initialised.")

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _on_mode_change(self, mode: str):
        print(f"Race mode changed to: {mode}")

    def _on_load_split(self, filepath: str):
        success = self.race_data_manager.load_ghost_data(filepath)
        if success:
            filename = self.race_data_manager.get_ghost_filename()
            self.ui.update_ghost_filename(filename)
            print(f"Loaded split ghost: {filename}")
            try:
                self.ui.update_split_view()
            except Exception:
                pass
            try:
                if hasattr(self.ui, "toggle_split_view_button") and self.ui.toggle_split_view_button:
                    self.ui.toggle_split_view_button.config(state="normal", bg="#8e44ad")
            except Exception:
                pass
        else:
            self.ui.show_message("Error", "Failed to load split file.", is_error=True)

    def _on_configure_splits(self, normalized_splits):
        if normalized_splits and isinstance(normalized_splits, list):
            if hasattr(self.race_data_manager, "splits"):
                self.race_data_manager.splits = normalized_splits
                try:
                    self.ui.update_split_view()
                except Exception:
                    pass
            print(f"Configured {len(normalized_splits)} splits")

    def _on_load_ghost(self, filepath: str):
        success = self.race_data_manager.load_ghost_data(filepath)
        if success:
            filename = self.race_data_manager.get_ghost_filename()
            self.ui.update_ghost_filename(filename)
            print(f"Loaded ghost: {filename}")
        else:
            self.ui.show_message("Error", "Failed to load ghost file.", is_error=True)

    def _on_save_race(self, filename: str):
        success = self.race_data_manager.save_race_data(filename)
        if success:
            print(f"Saved race data: {filename}.json")
        else:
            self.ui.show_message("Error", "Failed to save race data.", is_error=True)

    def _on_save_ghost(self, filepath: str):
        success = self.race_data_manager.save_race_data(filepath.replace(".json", ""))
        if success:
            self.ui.show_ghost_saved_message()
            print(f"Saved ghost: {filepath}")
        else:
            self.ui.show_message("Error", "Failed to save ghost file.", is_error=True)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _shutdown_all_threads(self):
        if self.shutdown_in_progress:
            return
        self.shutdown_in_progress = True
        print("Shutting down all threads...")
        self.capturing = False
        self.de_client.stop()
        if hasattr(self, "ui_thread") and self.ui_thread and self.ui_thread.is_alive():
            self.ui_thread.join(timeout=1.0)
        print("All threads shutdown complete")

    def stop(self):
        if self.shutdown_in_progress:
            return
        self._shutdown_all_threads()

    # ------------------------------------------------------------------
    # Timer formatting
    # ------------------------------------------------------------------

    @staticmethod
    def _format_timer(timer_us: int, ms: bool = False) -> str:
        """Format raw timer microseconds as MM:SS.mmm"""
        if timer_us <= 0:
            return "00:00.000"
        minutes = timer_us // 60000000
        seconds = (timer_us % 60000000) // 1000000
        microseconds = (timer_us % 1000000)
        if ms:
            milliseconds = microseconds // 1000
            return f"{minutes:02d}:{seconds:02d}.{milliseconds:03d}"
        return f"{minutes:02d}:{seconds:02d}.{microseconds:06d}"

    # ------------------------------------------------------------------
    # Race state detection
    # ------------------------------------------------------------------
    # "visual_timer" is a misnomer from the CT — it's really a race-state
    # indicator that the game always increments.  Key behaviours:
    #   1,000,000  → player is in menus
    #   0          → race countdown / pre-race (gear == 0 confirms)
    #   diverges from timer_raw after finish (timer_raw freezes ~1s
    #     after the race ends, while this value keeps climbing)
    #
    # timer_raw is the ACTUAL race timer in µs.  It stops automatically
    # ~900-1100ms after race completion — we never need to stop it manually.
    # ------------------------------------------------------------------

    RACE_ENDED_THRESHOLD_US = 250000  # µs divergence before we confirm race ended

    @staticmethod
    def _detect_race_state(
        race_state_val: int,
        timer_raw_us: int,
        progress_raw: float,
        gear: int,
        rpm: int,
        estimated_finish_us: int
    ) -> str:
        """
        Detect current game state from telemetry values.

        Args:
            race_state_val: CE "VisualTimer" — actually a race-state indicator
            timer_raw_us:   Actual race timer in microseconds (freezes after finish)
            progress_raw:   Race progress 0.0–1.0
            gear:           Current gear (0 = neutral / pre-race)

        Returns one of: 'menus', 'starting', 'racing', 'ended'
        """
        if (race_state_val == 1000000 or race_state_val == 0) and (gear == 1 or gear == 0) and rpm == 1250:
            return "menus"
        elif (
            race_state_val != 0         # skip VT-divergence check when VT is disabled (always 0)
            and timer_raw_us > 0
            and progress_raw > 0.99
            and race_state_val % 33333 != 0
            and (race_state_val - timer_raw_us) > ALUTimingTool.RACE_ENDED_THRESHOLD_US
        ):
            return "ended"
        elif estimated_finish_us:
            return "ended"
        else:
            return "racing"

    @staticmethod
    def _check_finish_trigger_new(
        progress: float,
        prev_progress: float,
        timer_us: int,
        prev_timer_us: int,
    ) -> Optional[int]:
        """
        Detect the instant the race finishes using progress/timer stall.

        Trigger: progress > 99.0 AND timer is not advancing (timer stalled).
        Returns prev_timer_us (microseconds) at that instant, or None.
        """
        if progress > .99:
            timer_increased = timer_us > prev_timer_us
            progress_increased = progress > prev_progress
            if timer_increased and not progress_increased:
                return prev_timer_us
        return None

    # ------------------------------------------------------------------
    # Race state transitions
    # ------------------------------------------------------------------

    def _handle_race_completion(self):
        """Handle definitive race completion: record time and prompt save."""
        if self.race_completed:
            return
        self.race_completed = True

        estimate = self.estimated_finish_us or 0
        true_final = self._final_timer_us or self.last_captured_timer_us

        # --- Console comparison log ---
        print("═" * 55)
        print(f"  FINISH ESTIMATE                  : {self._format_timer(estimate)}  ({estimate}us)")
        print(f"  TRUE FINAL (last raw timer)      : {self._format_timer(true_final)}  ({true_final}us)")
        diff = abs(true_final - estimate)
        print(f"  DIFFERENCE                       : {diff}us")
        print("═" * 55)

        # Use the finish estimate if available; fall back to true final.
        final_time = estimate if estimate > 0 else true_final
        self.estimated_finish_us = final_time
        self.current_timer_display = self._format_timer(final_time, ms=True)
        self.ui.update_delta("−−.−−−")
        self.race_data_manager.record_final_time(final_time)

        mode_label = self.ui.get_current_mode()
        print(
            f"Race completed in {mode_label} mode! "
            f"Final: {self._format_timer(final_time)}"
        )

    def reset_race_state(self):
        """Reset all per-race tracking for a fresh race.

        Also zeros display values since memory retains stale timer/progress
        from the previous race until the car moves.
        """
        self.race_completed = False
        self.race_in_progress = False
        self.reached_high_progress = False
        self.last_captured_timer_us = 0
        self.estimated_finish_us = None
        self._finish_locked = False
        self._progress_legitimized = False  # Must see < 50% before finish detection
        self._final_timer_us = 0
        self.last_valid_delta = "−−.−−−"
        self._prev_timer_us = 0
        self._prev_progress = 0
        self.current_timer_us = 0
        self.percentage = "0%"
        self.race_data_manager.reset_race_data()
        self.ui.update_save_ghost_button_state()
        print("Race state reset")

    # ------------------------------------------------------------------
    # Per-tick processing helpers
    # ------------------------------------------------------------------

    def _process_percentage_change(self, current_progress: float, prev_pct: float, timer_us: int):
        """Handle a percentage change during a live race."""
        if prev_pct == 0.0 and current_progress > 0.01:
            return False
        if self.race_in_progress and timer_us > 0 and current_progress < 1.0:
            existing = self.race_data_manager.current_progress_data[len(self.race_data_manager.current_progress_data) - 1] if len(self.race_data_manager.current_progress_data) > 0 else 0
            if existing != current_progress or current_progress == 0:
                self.race_data_manager.record_time_at_progress(current_progress, timer_us)
            else:
                print(f"Skipping {current_progress*100:.2f}% — already recorded as {existing}us")
            self.ui.update_save_ghost_button_state()

        current_mode = self.ui.get_current_mode()
        ghost_loaded = self.race_data_manager.is_ghost_loaded()

        if current_mode == "race" and ghost_loaded and self.race_in_progress:
            if current_progress < 1:
                delta_seconds = self.race_data_manager.calculate_delta(current_progress, timer_us)
                if delta_seconds is not None:
                    sign = "+" if delta_seconds >= 0 else "−"
                    if abs(delta_seconds) < 10.0: delta_str = f"{sign}{abs(delta_seconds):.3f}"
                    elif abs(delta_seconds) < 100.0: delta_str = f"{sign}{abs(delta_seconds):.2f}"
                    else: delta_str = f"{sign}{abs(delta_seconds):.1f}"
                    self.last_valid_delta = delta_str
                    self.ui.update_delta(delta_str)
                    self.ui.update_background_color("race", delta_seconds)
                else:
                    self.ui.update_delta("−−.−−−")
                    self.ui.update_background_color("record")
            else:
                self.ui.update_delta(self.last_valid_delta)
        else:
            self.ui.update_delta("−−.−−−")
            self.ui.update_background_color("record")
        if prev_pct == 0.0:
            print(f"Initial progress jump at {timer_us}us to {current_progress*100:.2f}% — recording from 0% baseline")
        return True

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run_main_loop(self):
        """
        Main processing loop — synchronous DataExtractor edition.

        Each iteration calls de_client.read().  If read() returns False
        (nothing changed in game memory, or DataExtractor is not yet ready),
        the loop sleeps briefly and skips all processing.  When read()
        returns a dict, all values are guaranteed to have changed since the
        last non-False return.

        Game state machine (identical to timer_v5_CE.py):
          menus    → player in menus; nothing to do
          starting → race countdown; stale values still in memory — RESET here
          racing   → race active; record data, check finish
          ended    → race just finished; timer_raw frozen, race_state keeps going

        Transitions:
          menus/starting → racing  : race begins, start recording
          racing → ended           : finish detected via game state
          ended/racing → menus     : back to menus
          anything → starting      : new race countdown, reset stale data
        """
        print("Starting main loop (pymem backend)...")
        prev_game_state = "menus"
        _debug_log_interval = 3.0
        _last_debug_log = 0.0
        init = True

        while self.capturing:
            loop_start = systime.perf_counter()

            # ── Read from memory (synchronous) ────────────────────────
            vals = self.de_client.read()
            if vals is False:
                # Nothing changed in game memory (or not yet attached).
                # Sleep briefly to avoid busy-spinning, then skip this tick.
                systime.sleep(0.001)
                continue
            [print(f"[DEBUG] Memory read: {vals}")]  # Debug log for each memory read
            self.total_loops += 1

            timer_raw_us   = vals["timer_raw"]
            progress_raw   = vals["progress"]
            race_state_val = vals["visual_timer"]
            gear           = vals["gear"]
            rpm            = vals["rpm"]

            # -- Periodic debug log ------------------------------------
            _now_mono = systime.perf_counter()
            if _now_mono - _last_debug_log >= _debug_log_interval:
                connected = self.de_client.is_connected()
                print(
                    f"[DEBUG] pymem: conn={connected} | "
                    f"timer={timer_raw_us}us pct={round(progress_raw*100,2)}% gear={gear} "
                    f"vt={race_state_val} | "
                    f"state={prev_game_state} racing={self.race_in_progress} "
                    f"completed={self.race_completed}"
                )
                _last_debug_log = _now_mono

            # -- Game state detection ----------------------------------
            game_state = self._detect_race_state(
                race_state_val, timer_raw_us, progress_raw, gear, rpm, self.estimated_finish_us
            )

            # -- State transitions -------------------------------------

            # Transition INTO racing — start recording.
            if game_state == "racing" and not self.race_in_progress:
                if self.race_completed or progress_raw > 0:
                    self.reset_race_state()
                self.race_in_progress = True
                self.ui.update_delta("=0.000")
                self.ui.update_background_color("race", 0)
                self.ui.update_splits(timer_raw_us, progress_raw)
                print("Race active — recording")

            # Transition to "ended" — game says race finished.
            if game_state == "ended" and prev_game_state == "racing":
                if not self.race_completed and self.race_in_progress:
                    print("Game state: Race Ended")
                    self._handle_race_completion()

            # Transition to "menus" — player left
            if game_state == "menus" and prev_game_state != "menus":
                if self.race_in_progress and not self.race_completed and not init:
                    print("Returned to menus mid-race — discarding partial data")
                    self.current_timer_display = "Quit Race"
                    self.ui.update_delta("−−.−−−")
                    self.race_in_progress = False
                elif self.race_in_progress and not init:
                    self.race_in_progress = False
                    print("Returned to menus after race completion")
                elif init:
                    print("Initial state: Menus")
                    self.current_timer_display = "00:00.000"
                    self.ui.update_delta("−−.−−−")
                    self.reset_race_state()
                self._prev_timer_us = 0
                self._prev_progress = 0
                self.current_timer_us = 0
                self.percentage = "0%"
                self.last_captured_timer_us = 0
            if game_state == "menus":
                init = False
            prev_game_state = game_state

            # -- Only process data while actually racing ---------------
            actively_racing = game_state == "racing" and self.race_in_progress

            # -- Finish trigger ----------------------------------------
            if game_state in ("menus", "starting"):
                self.estimated_finish_us = None
                self._finish_locked = False
                self._progress_legitimized = False

            float_pct = round(progress_raw * 100, 2) if 0.0 <= progress_raw <= 1.0 else round(progress_raw, 2)
            if float_pct < 50.0 and self.race_in_progress:
                if not self._progress_legitimized:
                    print(f"Progress legitimized at {float_pct}%")
                self._progress_legitimized = True
            if actively_racing and not self.race_completed:
                self._final_timer_us = timer_raw_us
            if not self._finish_locked and self._progress_legitimized:
                finish_us = self._check_finish_trigger_new(
                    progress_raw, self._prev_progress, timer_raw_us, self._prev_timer_us
                )
                if finish_us is not None:
                    self.estimated_finish_us = finish_us
                    self._finish_locked = True
                    print(f"Finish detected — estimate: {self._format_timer(finish_us)}")

            # -- Percentage change -------------------------------------
            pct_changed = progress_raw != self._prev_progress
            if pct_changed and actively_racing and not self.race_completed:
                if self._process_percentage_change(progress_raw, self._prev_progress, timer_raw_us):
                    self._prev_progress = progress_raw

            if actively_racing:
                self.percentage = f"{round(progress_raw*100,2)}%"

            # -- Timer change ------------------------------------------
            if timer_raw_us != self._prev_timer_us and actively_racing and not self.race_completed:
                self._prev_timer_us = timer_raw_us
                self.current_timer_us = timer_raw_us
                self.last_captured_timer_us = timer_raw_us
                self.current_timer_display = self._format_timer(timer_raw_us, ms=True)

            # -- Non-race UI reset -------------------------------------
            if not actively_racing and not self.race_completed:
                self.ui.update_delta("−−.−−−")
                self.ui.update_background_color("record")

            # -- Throttled UI updates ----------------------------------
            now = systime.time()
            if now - self.last_ui_update >= self.ui_update_interval:
                self.ui.update_timer(self.current_timer_display)
                if self.race_data_manager.is_new_split_available():
                    self.ui.update_splits(timer_raw_us, progress_raw)
                self.ui.update_percentage(self.percentage)
                self.last_ui_update = now

            # -- Loop timing -------------------------------------------
            elapsed_ms = (systime.perf_counter() - loop_start) * 1000
            self.loop_times.append(elapsed_ms)
            self.avg_loop_time = sum(self.loop_times) / len(self.loop_times)
            self.ui.update_loop_time(elapsed_ms, self.avg_loop_time)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        stats = {
            "total_loops": self.total_loops,
            "avg_loop_time": self.avg_loop_time,
            "current_percentage": self.percentage,
            "current_timer": self.current_timer_display,
            "timer_us": self.current_timer_us,
            "race_in_progress": self.race_in_progress,
            "race_completed": self.race_completed,
            "race_mode": self.ui.get_current_mode() if self.ui else "record",
            "ghost_loaded": self.race_data_manager.is_ghost_loaded(),
            "ghost_filename": self.race_data_manager.get_ghost_filename(),
        }
        stats.update(self.de_client.get_stats())
        return stats


if __name__ == "__main__":
    tool = ALUTimingTool()
    try:
        tool.run_main_loop()
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    finally:
        tool.stop()
