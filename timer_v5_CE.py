"""
Main Timer Application — Cheat Engine Backend (v5)

Receives full game telemetry from Cheat Engine via a shared temp file
(%TEMP%\\alu_ce_bridge.dat).  All OCR / CNN / screen-capture code has
been removed — CE handles memory reading directly.

Data fields from CE bridge (pipe-delimited):
  timer | progress | rpm | gear | rpmRaw | checkpoint

Prerequisites:
  1. ALU_Trainer_v2.CT open in Cheat Engine (auto-attaches)
     OR: the generated ALU_Trainer_v2.exe trainer running
  2. Run this app — it reads the bridge file written by CE
"""

import time as systime
import threading
from collections import deque
from typing import Optional

from src.modules import (
    TimingToolUI,
    RaceDataManager,
    CheatEngineClient,
)


class ALUTimingTool:
    """
    Main application class for the ALU Timing Tool (CE backend).

    Reads game telemetry from the CE bridge file and drives the full
    race-tracking pipeline: state detection, timing, ghost deltas,
    finish detection, and save prompts.
    """

    def __init__(self):
        """Initialize the ALU Timing Tool with CE file bridge."""
        # Core components
        self.race_data_manager = RaceDataManager()
        self.ui = TimingToolUI(self.race_data_manager)
        self.ce_client = CheatEngineClient()

        # Lifecycle
        self.capturing: bool = True
        self.shutdown_in_progress: bool = False

        # Race state
        self.race_in_progress: bool = False
        self.race_completed: bool = False
        self.reached_high_progress: bool = False  # True once pct >= 98

        # Timer & progress
        self.current_timer_ms: int = 0
        self.current_timer_display: str = "00:00.000"
        self.percentage: str = "0%"
        self.last_percentage: int = 0
        self.max_percentage_reached: int = 0
        self.last_captured_timer_ms: int = 0
        self.estimated_finish_ms: Optional[int] = None
        self.last_valid_delta: str = "--.---"

        # Change-detection trackers
        self._prev_timer_ms: int = 0
        self._prev_progress_pct: int = 0
        self._prev_checkpoint: int = 0

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

        # Start CE client
        self.ce_client.start()
        print("ALU Timing Tool (CE backend) initialised.")

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _on_mode_change(self, mode: str):
        print(f"Race mode changed to: {mode}")

    def _on_load_split(self, filepath: str):
        success = self.race_data_manager.load_split_data(filepath)
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
        self.ce_client.stop()
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
    def _format_timer(timer_ms: int) -> str:
        """Format raw timer milliseconds as MM:SS.mmm"""
        if timer_ms <= 0:
            return "00:00.000"
        minutes = timer_ms // 60000
        seconds = (timer_ms % 60000) // 1000
        milliseconds = timer_ms % 1000
        return f"{minutes:02d}:{seconds:02d}.{milliseconds:03d}"

    # ------------------------------------------------------------------
    # Finish detection (checkpoint-based, from notebook)
    # ------------------------------------------------------------------

    @staticmethod
    def _check_finish_trigger(
        checkpoint: int,
        prev_checkpoint: int,
        progress_pct: int,
        timer_ms: int,
    ) -> Optional[int]:
        """
        Detect the instant the race finishes using checkpoint data.

        Trigger: progress >= 99 AND (checkpoint increased OR wrapped to 0).
        Returns the timer_ms at that instant, or None.
        """
        if progress_pct >= 99:
            cp_increased = checkpoint > prev_checkpoint
            cp_wrapped = checkpoint == 0 and prev_checkpoint != 0
            if cp_increased or cp_wrapped:
                return timer_ms
        return None

    # ------------------------------------------------------------------
    # Race state transitions
    # ------------------------------------------------------------------

    def _handle_race_completion(self):
        """Handle definitive race completion: record time and prompt save."""
        if self.race_completed:
            return
        self.race_completed = True

        # Best finish time: checkpoint-trigger estimate > last captured
        final_time = self.estimated_finish_ms or self.last_captured_timer_ms
        if final_time > 0:
            self.race_data_manager.record_final_time(final_time)

        mode_label = self.ui.get_current_mode()
        print(
            f"Race completed in {mode_label} mode! "
            f"Final: {self._format_timer(final_time)}"
        )

        def prompt_save():
            systime.sleep(1)
            self.ui.prompt_save_race()

        threading.Thread(target=prompt_save, daemon=True).start()

    def _handle_race_end(self):
        """Transition from racing to menus. Trigger completion if appropriate."""
        if self.race_in_progress:
            # If we were deep enough into the race, treat it as completed
            if self.reached_high_progress and not self.race_completed:
                print("Race completed — reached 98%+ then returned to menus")
                self._handle_race_completion()
            self.race_in_progress = False
            print("Race ended — returned to menus")

    def _handle_potential_race_start(self):
        """Prepare for a new race; reset if previous race was completed."""
        if self.race_completed:
            print("New race detected — resetting state")
            self.reset_race_state()

    def reset_race_state(self):
        """Reset all per-race tracking for a fresh race."""
        self.race_completed = False
        self.race_in_progress = False
        self.reached_high_progress = False
        self.max_percentage_reached = 0
        self.last_percentage = 0
        self.last_captured_timer_ms = 0
        self.estimated_finish_ms = None
        self.last_valid_delta = "--.---"
        self._prev_timer_ms = 0
        self._prev_progress_pct = 0
        self._prev_checkpoint = 0
        self.race_data_manager.reset_race_data()
        self.ui.update_save_ghost_button_state()
        print("Race state reset")

    # ------------------------------------------------------------------
    # Per-tick processing helpers
    # ------------------------------------------------------------------

    def _process_percentage_change(self, current_pct: int, prev_pct: int, timer_ms: int):
        """Handle a percentage change during a live race."""
        self.last_percentage = current_pct

        if current_pct >= 98:
            self.reached_high_progress = True
        if current_pct > self.max_percentage_reached:
            self.max_percentage_reached = current_pct

        # Record time at this percentage
        if self.race_in_progress and timer_ms > 0:
            self.race_data_manager.record_time_at_percentage(current_pct, timer_ms)
            print(f"Recorded {current_pct}%: {timer_ms}ms")
            self.ui.update_save_ghost_button_state()

        # Delta calculation
        current_mode = self.ui.get_current_mode()
        ghost_loaded = self.race_data_manager.is_ghost_loaded()

        if current_mode == "race" and ghost_loaded and self.race_in_progress:
            if current_pct < 99:
                delta_seconds = self.race_data_manager.calculate_delta(current_pct, timer_ms)
                if delta_seconds is not None:
                    sign = "+" if delta_seconds >= 0 else ""
                    delta_str = f"{sign}{delta_seconds:.3f}"
                    self.last_valid_delta = delta_str
                    self.ui.update_delta(delta_str)
                    self.ui.update_background_color("race", delta_seconds)
                else:
                    self.ui.update_delta("--.---")
            else:
                # At 99%+, hold the last valid delta (avoids erratic final-second values)
                self.ui.update_delta(self.last_valid_delta)
        else:
            self.ui.update_delta("--.---")
            self.ui.update_background_color("record")

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run_main_loop(self):
        """
        Main processing loop.

        Each tick:
          1. Read all telemetry from CE client
          2. Detect race state transitions
          3. Check for finish trigger (checkpoint-based)
          4. Process percentage / timer changes
          5. Update UI (throttled)
        """
        print("Starting main loop (CE backend)...")

        while self.capturing:
            loop_start = systime.perf_counter()
            self.total_loops += 1

            # -- Read all values from CE -------------------------------
            vals = self.ce_client.get_all_values()
            timer_raw_us = vals["timer_raw"]        # microseconds
            progress_raw = vals["progress"]          # 0.0–1.0
            checkpoint = vals["checkpoint"]
            # gear and rpm available in vals but not needed for core logic

            timer_ms = timer_raw_us // 1000
            if 0.0 <= progress_raw <= 1.0:
                current_pct = int(round(progress_raw * 100))
            else:
                current_pct = int(round(progress_raw))

            # -- Race state detection ----------------------------------
            in_race_now = timer_ms > 0 or current_pct > 0

            if not in_race_now and self.race_in_progress:
                self._handle_race_end()
            elif in_race_now and not self.race_in_progress:
                self._handle_potential_race_start()
                self.race_in_progress = True
                print(f"Race detected at {current_pct}%")

            # -- Finish trigger (checkpoint-based) ---------------------
            if self.race_in_progress and not self.race_completed:
                finish_ms = self._check_finish_trigger(
                    checkpoint, self._prev_checkpoint, current_pct, timer_ms
                )
                if finish_ms is not None:
                    self.estimated_finish_ms = finish_ms
                    print(f"Finish detected via checkpoint! Timer: {finish_ms}ms")
                    self._handle_race_completion()

            self._prev_checkpoint = checkpoint

            # -- Percentage change -------------------------------------
            pct_changed = current_pct != self._prev_progress_pct
            if pct_changed and in_race_now:
                prev_pct = self._prev_progress_pct
                self._prev_progress_pct = current_pct
                print(f"Percentage: {prev_pct}% → {current_pct}%")
                self._process_percentage_change(current_pct, prev_pct, timer_ms)

            self.percentage = f"{current_pct}%"

            # -- Timer change ------------------------------------------
            if timer_ms != self._prev_timer_ms and in_race_now:
                self._prev_timer_ms = timer_ms
                self.current_timer_ms = timer_ms
                self.last_captured_timer_ms = timer_ms
                self.current_timer_display = self._format_timer(timer_ms)

            # -- Non-race UI reset -------------------------------------
            if not in_race_now:
                self.ui.update_delta("--.---")
                self.ui.update_background_color("record")

            # -- Throttled UI updates ----------------------------------
            now = systime.time()
            if now - self.last_ui_update >= self.ui_update_interval:
                self.ui.update_timer(self.current_timer_display)
                self.ui.update_percentage(self.percentage)
                self.last_ui_update = now

            # -- Loop timing -------------------------------------------
            elapsed_ms = (systime.perf_counter() - loop_start) * 1000
            self.loop_times.append(elapsed_ms)
            self.avg_loop_time = sum(self.loop_times) / len(self.loop_times)
            self.ui.update_loop_time(elapsed_ms, self.avg_loop_time)

            # Sleep to avoid busy-spinning (~500 Hz is plenty)
            systime.sleep(0.002)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        stats = {
            "total_loops": self.total_loops,
            "avg_loop_time": self.avg_loop_time,
            "current_percentage": self.percentage,
            "current_timer": self.current_timer_display,
            "timer_ms": self.current_timer_ms,
            "race_in_progress": self.race_in_progress,
            "race_completed": self.race_completed,
            "max_percentage_reached": self.max_percentage_reached,
            "race_mode": self.ui.get_current_mode() if self.ui else "record",
            "ghost_loaded": self.race_data_manager.is_ghost_loaded(),
            "ghost_filename": self.race_data_manager.get_ghost_filename(),
        }
        stats.update(self.ce_client.get_stats())
        return stats
