"""
Main Timer Application — Cheat Engine Backend (v5)

Receives full game telemetry from Cheat Engine via a shared temp file
(%TEMP%\\alu_ce_bridge.dat).  All OCR / CNN / screen-capture code has
been removed — CE handles memory reading directly.

Data fields from CE bridge (pipe-delimited):
  timer | progress | rpm | gear | rpmRaw | checkpoint | visualTimer

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
        self.ce_client = CheatEngineClient(poll_interval=0.001)  # 1ms = 1000Hz

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

        # Finish detection — checkpoint method (from notebook)
        # At 99%+, checkpoint increments at the finish instant.
        # Fires twice ~1s apart; we only use the first.
        self._finish_locked: bool = False
        self._prev_checkpoint: int = 0
        self._final_timer_us: int = 0   # last timer while racing ("true final")

        # Guard against stale progress: CE memory keeps 100% from race N-1.
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

        # Start CE client
        self.ce_client.start()
        print("ALU Timing Tool (CE backend) initialised.")

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
    def _format_timer(timer_us: int, ms: bool=False) -> str:
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
            #print(f"Race start detected at {timer_raw_us}us and {progress_raw*100:.2f}% progress")
            return "racing"

    # ------------------------------------------------------------------
    # Finish detection (checkpoint-based, from notebook)
    # ------------------------------------------------------------------

    @staticmethod
    def _check_finish_trigger(
        checkpoint: int,
        prev_checkpoint: int,
        progress: float,
        timer_us: int,
    ) -> Optional[int]:
        """
        Detect the instant the race finishes using checkpoint data.
        (Matching notebook logic exactly)

        Trigger: progress > 99.0 AND (checkpoint increased OR wrapped to 0).
        Returns timer_us (microseconds) at that instant, or None.
        """
        if progress > .99:
            cp_increased = checkpoint > prev_checkpoint
            cp_wrapped = checkpoint == 0 and prev_checkpoint != 0
            if cp_increased or cp_wrapped:
                return timer_us
        return None
    
    @staticmethod
    def _check_finish_trigger_new(
        progress: float,
        prev_progress: float,
        timer_us: int,
        prev_timer_us: int,
    ) -> Optional[int]:
        """
        Detect the instant the race finishes using checkpoint data.
        (Matching notebook logic exactly)

        Trigger: progress > 99.0 AND (checkpoint increased OR wrapped to 0).
        Returns timer_us (microseconds) at that instant, or None.
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
        print(f"  FINISH ESTIMATE (checkpoint)     : {self._format_timer(estimate)}  ({estimate}us)")
        print(f"  TRUE FINAL (last raw timer)      : {self._format_timer(true_final)}  ({true_final}us)")
        diff = abs(true_final - estimate)
        print(f"  DIFFERENCE                       : {diff}us")
        print("═" * 55)

        # Use the checkpoint estimate as the recorded 100% time;
        # fall back to true final if checkpoint never fired.
        final_time = estimate if estimate > 0 else true_final
        self.estimated_finish_us = final_time
        self.current_timer_display = self._format_timer(final_time, ms=True)  # convert to ms for display
        self.ui.update_delta("−−.−−−")
        self.race_data_manager.record_final_time(final_time)

        mode_label = self.ui.get_current_mode()
        print(
            f"Race completed in {mode_label} mode! "
            f"Final: {self._format_timer(final_time)}"
        )

        #def prompt_save():
        #    systime.sleep(1)
        #    self.ui.prompt_save_race()

        #threading.Thread(target=prompt_save, daemon=True).start()

    def reset_race_state(self):
        """Reset all per-race tracking for a fresh race.

        Also zeros display values since CE memory retains stale
        timer/progress from the previous race until the car moves.
        """
        self.race_completed = False
        self.race_in_progress = False
        self.reached_high_progress = False
        self.last_captured_timer_us = 0
        self.estimated_finish_us = None
        self._finish_locked = False
        self._progress_legitimized = False  # Must see < 50% before finish detection
        # NOTE: Do NOT reset _prev_checkpoint here — track it continuously
        # like the notebook does (only reset finish_locked, not checkpoint)
        self._final_timer_us = 0
        self.last_valid_delta = "−−.−−−"
        self._prev_timer_us = 0
        self._prev_progress = 0
        # Zero display — CE memory still has stale values
        self.current_timer_us = 0
        #self.current_timer_display = "00:00.000"
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
            #print(f"Error: too much progress jump from 0% → {current_progress*100:.2f}% — likely stale CE memory. Ignoring percentage change.")
            return False
        # Record time at this percentage (first crossing only)
        # Skip 100% — that's handled by checkpoint finish detection
        if self.race_in_progress and timer_us > 0 and current_progress < 1.0:
            # Check if this percentage already has a recorded value
            existing = self.race_data_manager.current_progress_data[len(self.race_data_manager.current_progress_data) - 1] if len(self.race_data_manager.current_progress_data) > 0 else 0
            if existing != current_progress or current_progress == 0:
                self.race_data_manager.record_time_at_progress(current_progress, timer_us)
                #print(f"Recorded {current_progress*100:.2f}%: {timer_us}us")
            else:
                print(f"Skipping {current_progress*100:.2f}% — already recorded as {existing}us")
            self.ui.update_save_ghost_button_state()

        # Delta calculation
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
                # At 99%+, hold the last valid delta (avoids erratic final-second values)
                self.ui.update_delta(self.last_valid_delta)
        else:
            self.ui.update_delta("−−.−−−")
            self.ui.update_background_color("record")
        if prev_pct == 0.0: print(f'Initial progress jump at {timer_us}us to {current_progress*100:.2f}% — recording from 0% baseline')
        return True

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run_main_loop(self):
        """
        Main processing loop.

        Game state machine (from notebook ground truth):
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
        print("Starting main loop (CE backend)...")
        prev_game_state = "menus"
        _debug_log_interval = 3.0
        _last_debug_log = 0.0
        init = True

        while self.capturing:
            loop_start = systime.perf_counter()
            self.total_loops += 1

            # -- Read all values from CE -------------------------------
            vals = self.ce_client.get_all_values()
            timer_raw_us = vals["timer_raw"]        # microseconds
            progress_raw = vals["progress"]          # 0.0–1.0
            checkpoint = vals["checkpoint"]
            race_state_val = vals["visual_timer"]  # misnomer in CT; it's a race-state indicator
            gear = vals["gear"]
            rpm = vals["rpm"]

            #timer_us = timer_raw_us // 1000
            #if 0.0 <= progress_raw <= 1.0:
            #    current_pct = int(round(progress_raw * 100))
            #else:
            #    current_pct = int(round(progress_raw))

            # -- Periodic debug log ------------------------------------
            _now_mono = systime.perf_counter()
            if _now_mono - _last_debug_log >= _debug_log_interval:
                connected = self.ce_client.is_connected()
                print(
                    f"[DEBUG] CE: conn={connected} | "
                    f"timer={timer_raw_us}us pct={round(progress_raw*100,2)}% gear={gear} "
                    f"vt={race_state_val} cp={checkpoint} | "
                    f"state={prev_game_state} racing={self.race_in_progress} "
                    f"completed={self.race_completed}"
                )
                _last_debug_log = _now_mono

            # -- Game state detection ----------------------------------
            game_state = self._detect_race_state(
                race_state_val, timer_raw_us, progress_raw, gear, rpm, self.estimated_finish_us
            )

            # -- State transitions -------------------------------------

            # "starting" = countdown — reset for a fresh race.
            #if game_state == "starting" and prev_game_state != "starting":
            #    print("Race countdown — resetting for new race")
            #    self.reset_race_state()

            # Transition INTO racing — start recording.
            if game_state == "racing" and not self.race_in_progress:
                if self.race_completed or progress_raw > 0:
                    self.reset_race_state()
                self.race_in_progress = True
                self.ui.update_delta("=0.000")
                self.ui.update_background_color("race",0)
                self.ui.update_splits(timer_raw_us, progress_raw)
                print("Race active — recording")

            # Transition to "ended" — game says race finished.
            # Must also require race_in_progress to avoid ghost completions
            # from stale CE memory (bridge file retains data across sessions).
            if game_state == "ended" and prev_game_state == "racing":
                if not self.race_completed and self.race_in_progress:
                    print("Game state: Race Ended")
                    self._handle_race_completion()

            # Transition to "menus" — player left
            if game_state == "menus" and prev_game_state != "menus":
                if self.race_in_progress and not self.race_completed and not init:
                    # Quit mid-race — discard
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
                # CE memory retains stale timer/progress after race ends.
                # Zero our own interpretation so stale values aren't
                # shown or re-recorded when the next race starts.
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

            # -- Finish trigger (checkpoint-based, matching notebook EXACTLY) --
            # Reset finish state every tick when in menus/starting.
            # CRITICAL: Also sync prev_checkpoint to current checkpoint!
            # Otherwise stale prev_checkpoint from race N causes false
            # cp_wrapped detection early in race N+1.
            if game_state in ("menus", "starting"):
                self.estimated_finish_us = None
                self._finish_locked = False
                self._progress_legitimized = False  # Reset for new race
                self._prev_checkpoint = checkpoint

            # Uses float pct and timer in MICROSECONDS (like notebook)
            float_pct = round(progress_raw * 100, 2) if 0.0 <= progress_raw <= 1.0 else round(progress_raw, 2)
            # Track that progress legitimately dropped (proves it's not stale from race N-1).
            # CE memory retains 100% from previous race for several seconds after new race starts.
            if float_pct < 50.0 and self.race_in_progress:
                if not self._progress_legitimized:
                    print(f"Progress legitimized at {float_pct}%")
                self._progress_legitimized = True
            if actively_racing and not self.race_completed:
                # Always track the very last timer value while racing
                self._final_timer_us = timer_raw_us
            # Only trigger finish detection if progress has been legitimized.
            # This prevents false triggers when progress is stale at 100% from the previous race.
            if not self._finish_locked and self._progress_legitimized:
                #finish_us = self._check_finish_trigger(
                #    checkpoint, self._prev_checkpoint, progress_raw, timer_raw_us
                #)
                finish_us = self._check_finish_trigger_new(
                    progress_raw, self._prev_progress, timer_raw_us, self._prev_timer_us
                )
                if finish_us is not None:
                    # Store in us for consistency with rest of codebase
                    self.estimated_finish_us = finish_us
                    self._finish_locked = True
                    print(f"Finish detected via checkpoint — estimate: {self._format_timer(finish_us)}")
            
            self._prev_checkpoint = checkpoint

            # -- Percentage change -------------------------------------
            pct_changed = progress_raw != self._prev_progress
            if pct_changed and actively_racing and not self.race_completed:
                if self._process_percentage_change(progress_raw, self._prev_progress, timer_raw_us): self._prev_progress = progress_raw
                
                #print(f"Percentage: {prev_pct}% → {current_pct}%")
                

            if actively_racing:
                self.percentage = f"{round(progress_raw*100,2)}%"

            # -- Timer change ------------------------------------------
            if timer_raw_us != self._prev_timer_us and actively_racing and not self.race_completed:
                self._prev_timer_us = timer_raw_us
                self.current_timer_us = timer_raw_us
                self.last_captured_timer_us = timer_raw_us
                self.current_timer_display = f'{self._format_timer(timer_raw_us,ms=True)}' # convert to ms for display

            # -- Non-race UI reset -------------------------------------
            if not actively_racing and not self.race_completed:
                self.ui.update_delta("−−.−−−")
                self.ui.update_background_color("record")

            # -- Throttled UI updates ----------------------------------
            now = systime.time()
            if now - self.last_ui_update >= self.ui_update_interval:
                self.ui.update_timer(self.current_timer_display)
                if self.race_data_manager.is_new_split_available(): self.ui.update_splits(timer_raw_us, progress_raw)
                self.ui.update_percentage(self.percentage)
                self.last_ui_update = now

            # -- Loop timing -------------------------------------------
            elapsed_ms = (systime.perf_counter() - loop_start) * 1000
            self.loop_times.append(elapsed_ms)
            self.avg_loop_time = sum(self.loop_times) / len(self.loop_times)
            self.ui.update_loop_time(elapsed_ms, self.avg_loop_time)

            # Sleep to avoid busy-spinning (~1000 Hz)
            systime.sleep(0.001)

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
        stats.update(self.ce_client.get_stats())
        return stats
