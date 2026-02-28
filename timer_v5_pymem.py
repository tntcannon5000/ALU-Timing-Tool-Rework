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

import os
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

        # Delta tracking (for vdelta ratio when ghost has no velocity data)
        self.last_delta_s: Optional[float] = None

        # Race state
        self.race_in_progress: bool = False
        self.race_completed: bool = False
        self.reached_high_progress: bool = False  # True once pct >= 98
        self.init: bool = True  # True until we see the first "menus" state, to ignore stale initial memory
        self.starting: bool = False  # True during countdown, to show overlays

        # VT false-positive handling: the game sometimes pulses VT=0 briefly
        # before the real countdown, then returns to 1000000 for a moment.
        # A 5-second clock arms the moment "starting" is first detected.
        # Any "menus" transition that arrives while the clock is still running
        # is ignored for overlay purposes — all race displays stay visible.
        # Only after the clock expires AND the game is still in "menus" do we
        # tear down the overlays.  Seeing "starting" again resets the clock.
        self._last_starting_ts: Optional[float] = None  # perf_counter() of last "starting" detection; None = not armed
        self._starting_display_shown: bool = False

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
        self.last_velocity_raw: float = 0.0  # latest raw velocity for recording

        # Performance tracking
        self.loop_times: deque = deque(maxlen=30)
        self.avg_loop_time: float = 0.0
        self.total_loops: int = 0

        # UI throttling
        self.last_ui_update: float = 0.0
        self.ui_update_interval: float = 1.0 / 10.0  # ~10 fps

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
            display_name = os.path.basename(filepath)
            self.ui.update_ghost_filename(display_name)
            print(f"Loaded split ghost: {display_name}")
            self.ui.update_splits_checkbox_state()
            self.ui.show_splits_if_enabled()
        else:
            self.ui.show_message("Error", "Failed to load split file.", is_error=True)

    def _on_configure_splits(self, normalized_splits):
        if normalized_splits and isinstance(normalized_splits, list):
            if hasattr(self.race_data_manager, "splits"):
                self.race_data_manager.splits = normalized_splits
            self.ui.update_splits_checkbox_state()
            self.ui.show_splits_if_enabled()
            print(f"Configured {len(normalized_splits)} splits")

    def _on_load_ghost(self, filepath: str):
        success = self.race_data_manager.load_ghost_data(filepath)
        if success:
            display_name = os.path.basename(filepath)
            self.ui.update_ghost_filename(display_name)
            print(f"Loaded ghost: {display_name}")
            self.ui.update_splits_checkbox_state()
            self.ui.show_splits_if_enabled()
        else:
            self.ui.show_message("Error", "Failed to load ghost file.", is_error=True)

    def _on_save_race(self, filename: str):
        success = self.race_data_manager.save_race_data(filename)
        if success:
            print(f"Saved race data: {filename}.json")
        else:
            self.ui.show_message("Error", "Failed to save race data.", is_error=True)

    def _on_save_ghost(self, filepath: str):
        # Capture current loaded ghost name BEFORE saving.
        prev_ghost_name = self.ui._current_ghost_name
        success = self.race_data_manager.save_race_data(filepath.replace(".json", ""))
        if success:
            self.ui.show_ghost_saved_message()
            print(f"Saved ghost: {filepath}")
            # If the user overwrote the currently loaded ghost, auto-reload it
            # so the ghost data reflects the just-saved race.  Do NOT show the
            # split panel on auto-reload (the user didn't explicitly load it).
            if prev_ghost_name and os.path.splitext(os.path.basename(filepath))[0] == os.path.splitext(prev_ghost_name)[0]:
                reload_ok = self.race_data_manager.load_ghost_data(filepath)
                if reload_ok:
                    display_name = os.path.basename(filepath)
                    self.ui.update_ghost_filename(display_name)
                    self.ui.update_splits_checkbox_state()
                    print(f"Auto-reloaded updated ghost: {display_name}")
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

    def end_init(self):
        """Call once we've seen the first 'menus' state to end init phase."""
        if self.init:
            self.init = False
            print("Initial memory state observed — exiting init phase")

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
            milliseconds = microseconds / 1000
            return f"{minutes:02d}:{seconds:02d}.{round(milliseconds):03d}"
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
    HIDE_DEBOUNCE_S = 5             # seconds to wait before hiding overlays after a starting→menus transition

    @staticmethod
    def _detect_race_state(
        race_state_val: int,
        timer_raw_us: int,
        progress_raw: float,
        gear: int,
        rpm: int,
        estimated_finish_us: int,
        init: bool,
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
        # Guard: if all physics/timer values are at idle (timer stopped, no
        # progress, neutral gear, idle RPM) it cannot be a live race regardless
        # of what VT says.  This catches the brief VT glitch that can occur
        # immediately after returning to menus, where the VT stub still holds
        # the last in-race value instead of 1,000,000.
        if timer_raw_us == 0 and progress_raw == 0.0 and rpm == 1250 and gear == 0:
            return "menus" if race_state_val != 0 or init else "starting"
        if (race_state_val == 1000000 or race_state_val == 0) and (gear == 1 or gear == 0) and rpm == 1250 and timer_raw_us == 0 and progress_raw == 0.0:
            return "menus" if race_state_val == 1000000 or init else "starting"
        elif (
            race_state_val != 0         # skip VT-divergence check when VT is disabled (always 0)
            and timer_raw_us > 0
            and progress_raw > 0.99
            and race_state_val % 33333 != 0
            and (race_state_val - timer_raw_us) > ALUTimingTool.RACE_ENDED_THRESHOLD_US
        ):
            return "ended_sp"
        elif estimated_finish_us:
            return "ended_pl"
        else:
            return "racing_pl" if race_state_val % 33333 == 0 else "racing_sp"

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

    def _handle_race_completion(self, from_pl_finish=False):
        """Handle definitive race completion: record time and prompt save."""
        if self.race_completed:
            return
        self.race_completed = True

        estimate = self.estimated_finish_us or 0
        true_final = self._final_timer_us or self.last_captured_timer_us

        # --- Console comparison log ---
        print("═" * 55)
        print("FROM PL FINISH DETECTION" if from_pl_finish else "FROM SINGLEPLAYER DETECTION")
        print(f"  FINISH ESTIMATE                  : {self._format_timer(estimate)}  ({estimate}us)")
        print(f"  TRUE FINAL (last raw timer)      : {self._format_timer(true_final)}  ({true_final}us)")
        diff = abs(true_final - estimate)
        print(f"  DIFFERENCE                       : {diff}us")
        print("═" * 55)

        # Use the finish estimate if available; fall back to true final.
        final_time = estimate if from_pl_finish and estimate > 0 else true_final
        self.estimated_finish_us = final_time
        self.current_timer_display = self._format_timer(final_time, ms=True)
        self.ui.update_delta("−−.−−−")
        self.race_data_manager.record_final_time(final_time, self.last_velocity_raw)

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
        self.last_delta_s = None
        self._last_starting_ts = None
        self._starting_display_shown = False
        self.race_data_manager.reset_race_data()
        self.ui.update_save_ghost_button_state()
        print("Race state reset")

    # ------------------------------------------------------------------
    # Per-tick processing helpers
    # ------------------------------------------------------------------

    def _process_percentage_change(self, current_progress: float, prev_pct: float, timer_us: int, velocity: float = 0.0):
        """Handle a percentage change during a live race."""
        if prev_pct == 0.0 and current_progress > 0.01:
            return False
        if self.race_in_progress and timer_us > 0 and current_progress < 1.0:
            existing = self.race_data_manager.current_progress_data[len(self.race_data_manager.current_progress_data) - 1] if len(self.race_data_manager.current_progress_data) > 0 else 0
            if existing != current_progress or current_progress == 0:
                self.race_data_manager.record_time_at_progress(current_progress, timer_us, velocity)
            else:
                print(f"Skipping {current_progress*100:.2f}% — already recorded as {existing}us")
            self.ui.update_save_ghost_button_state()

        current_mode = self.ui.get_current_mode()
        ghost_loaded = self.race_data_manager.is_ghost_loaded()

        if current_mode == "Race vs Ghost" and ghost_loaded and self.race_in_progress:
            if current_progress < 1:
                delta_seconds = self.race_data_manager.calculate_delta(current_progress, timer_us)
                if delta_seconds is not None:
                    self.last_delta_s = delta_seconds
                    sign = "+" if delta_seconds >= 0 else "\u2212"
                    if abs(delta_seconds) < 10.0: delta_str = f"{sign}{round(abs(delta_seconds), 3):.3f}"
                    elif abs(delta_seconds) < 100.0: delta_str = f"{sign}{round(abs(delta_seconds), 2):.2f}"
                    else: delta_str = f"{sign}{round(abs(delta_seconds), 1):.1f}"
                    self.last_valid_delta = delta_str
                    self.ui.update_delta(delta_str)
                    self.ui.update_background_color("Race vs Ghost", delta_seconds)
                else:
                    self.ui.update_delta("−−.−−−")
                    self.ui.update_background_color("Record Ghost")
            else:
                self.ui.update_delta(self.last_valid_delta)
        else:
            self.ui.update_delta("−−.−−−")
            self.ui.update_background_color("Record Ghost")
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
        prev_game_state = "startup"
        _debug_log_interval = 3.0
        _last_debug_log = 0.0

        while self.capturing:
            loop_start = systime.perf_counter()

            # ── Read from memory (synchronous) ────────────────────────
            vals = self.de_client.read()
            if vals is False:
                # Nothing changed in game memory (or not yet attached).
                # Sleep briefly to avoid busy-spinning, then skip this tick.
                systime.sleep(0.001)
                continue
            self.total_loops += 1

            timer_raw_us   = vals["timer_raw"]
            progress_raw   = vals["progress"]
            race_state_val = vals["visual_timer"]
            gear           = vals["gear"]
            rpm            = vals["rpm"]
            velocity_raw   = vals.get("velocity_raw", 0.0)
            physics_update = vals.get("physics_update", False)
            steering_raw   = vals.get("steering_raw", 0.0)
            self.last_velocity_raw = velocity_raw
            if race_state_val == 1000000:
                self.end_init()
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
                race_state_val, timer_raw_us, progress_raw, gear, rpm, self.estimated_finish_us, self.init
            )

            # -- State transitions -------------------------------------

            # Transition INTO racing — start recording.
            if game_state in ("racing_pl", "racing_sp") and not self.race_in_progress:
                if self.race_completed or progress_raw > 0:
                    self.reset_race_state()
                self.race_in_progress = True
                self.ui.update_delta("=0.000")
                self.ui.update_background_color("Race vs Ghost", 0)
                # Clear debounce clock — we're genuinely racing now.
                self._last_starting_ts = None
                # Fallback: if begin_race_display was never called (e.g. game
                # skipped "starting" entirely and jumped straight to racing),
                # fire it now so overlays are guaranteed visible.
                if not self._starting_display_shown:
                    self._starting_display_shown = True
                    self.starting = True
                    ghost_loaded_now = self.race_data_manager.is_ghost_loaded()
                    self.ui.begin_race_display(self.ui.get_current_mode(), ghost_loaded_now)
                    try:
                        self.ui.update_splits(0, 0.0)
                    except Exception:
                        pass
                print("Race active — recording")

            # Transition to "ended" — game says race finished.
            if game_state == "ended_sp" and prev_game_state == "racing_sp":
                self._handle_race_completion(True)
                if not self.race_completed and self.race_in_progress:
                    print("Game state: Race Ended")
                    self._handle_race_completion()
                # Hide motion overlays on race end; split view stays until menus.
                self.ui.update_gear_rpm(0, 0, False)
                self.ui.update_velocity(0.0, False)
                self.ui.update_steering(0.0, False)
                self.ui.update_vdelta(0.0, None, False)
                self.ui.restore_race_panel()
            elif game_state == "ended_pl" and prev_game_state == "racing_pl":
                if not self.race_completed and self.race_in_progress:
                    print("Game state: Race Ended")
                    self._handle_race_completion(True)
                # Hide motion overlays on race end; split view stays until menus.
                self.ui.update_gear_rpm(0, 0, False)
                self.ui.update_velocity(0.0, False)
                self.ui.update_steering(0.0, False)
                self.ui.update_vdelta(0.0, None, False)
                self.ui.restore_race_panel()

            if game_state == "starting" and prev_game_state != "starting":
                # (Re-)arm the debounce clock — 5 s grace period starts now.
                self._last_starting_ts = systime.perf_counter()
                self._starting_display_shown = True
                self.starting = True
                print("Countdown started - Loading Race GUI")
                self.ui.update_timer("00:00.000")
                if self.ui.get_current_mode() == "Race vs Ghost":
                    self.ui.update_delta("=0.000")
                    self.ui.update_background_color("Race vs Ghost", 0)
                else:
                    self.ui.update_delta("−−.−−−")
                ghost_loaded_now = self.race_data_manager.is_ghost_loaded()
                self.ui.begin_race_display(self.ui.get_current_mode(), ghost_loaded_now)
                try:
                    self.ui.update_splits(0, 0.0)
                except Exception:
                    pass
            elif game_state != "starting" and prev_game_state == "starting":
                self._starting_display_shown = False
                self.starting = False

            # Transition to "menus" — player left
            if game_state == "menus" and prev_game_state != "menus":
                if self.race_in_progress and not self.race_completed and not self.init:
                    print("Returned to menus mid-race — discarding partial data")
                    self.current_timer_display = "Quit Race"
                    self.ui.update_delta("−−.−−−")
                    self.race_in_progress = False
                    self.race_data_manager.reset_race_data()
                elif self.race_in_progress and not self.init:
                    self.race_in_progress = False
                    print("Returned to menus after race completion")
                    self.race_data_manager.reset_race_data()
                elif self.init:
                    print("Initial state: Menus")
                    self.current_timer_display = "00:00.000"
                    self.ui.update_delta("−−.−−−")
                    self.reset_race_state()
                # If the debounce clock is still running ("starting" was seen
                # recently), leave all overlays up.  The flush block below will
                # tear them down once the 5-second grace period expires.
                _in_debounce = (
                    self._last_starting_ts is not None
                    and systime.perf_counter() - self._last_starting_ts < self.HIDE_DEBOUNCE_S
                )
                if not _in_debounce:
                    self.ui.update_gear_rpm(0, 0, False)
                    self.ui.update_velocity(0.0, False)
                    self.ui.update_steering(0.0, False)
                    self.ui.update_vdelta(0.0, None, False)
                    self.ui.auto_hide_race_overlays()
                    self.ui.schedule_split_view_reset()
                    self._last_starting_ts = None
                self._prev_timer_us = 0
                self._prev_progress = 0
                self.current_timer_us = 0
                self.percentage = "0%"
                self.last_captured_timer_us = 0

            # Flush: if the 5-second grace has elapsed while still in menus,
            # tear down all overlays now.
            if self._last_starting_ts is not None and game_state == "menus":
                if systime.perf_counter() - self._last_starting_ts >= self.HIDE_DEBOUNCE_S:
                    self._last_starting_ts = None
                    self.race_data_manager.reset_race_data()
                    self.ui.update_gear_rpm(0, 0, False)
                    self.ui.update_velocity(0.0, False)
                    self.ui.update_steering(0.0, False)
                    self.ui.update_vdelta(0.0, None, False)
                    self.ui.auto_hide_race_overlays()
                    self.ui.schedule_split_view_reset()
            prev_game_state = game_state

            # -- Only process data while actually racing ---------------
            actively_racing = game_state in ("racing_pl", "racing_sp") and self.race_in_progress
            is_pl = game_state == "racing_pl" and self.race_in_progress
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
            if not self._finish_locked and self._progress_legitimized and is_pl:
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
                if self._process_percentage_change(progress_raw, self._prev_progress, timer_raw_us, velocity_raw):
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
                self.ui.update_background_color("Record Ghost")

            # -- Throttled UI updates ----------------------------------
            now = systime.time()
            # Overlays visible during countdown, while racing, or while the
            # 5-second false-positive debounce clock is still running.
            should_show_overlays = (
                game_state in ("racing_pl", "racing_sp")
                or self.starting
                or self._last_starting_ts is not None
            )
            if physics_update or (now - self.last_ui_update >= self.ui_update_interval):
                self.ui.update_timer(self.current_timer_display)
                if self.race_data_manager.is_new_split_available():
                    self.ui.update_splits(timer_raw_us, progress_raw)
                self.ui.update_percentage(self.percentage)
                self.ui.update_gear_rpm(gear, rpm, should_show_overlays)
                self.ui.update_velocity(velocity_raw, should_show_overlays)
                self.ui.update_steering(steering_raw, should_show_overlays)
                # Velocity delta: compare current speed vs ghost speed at same progress
                ghost_loaded = self.race_data_manager.is_ghost_loaded()
                ghost_vel_raw = None
                if ghost_loaded and actively_racing:
                    ghost_vel_raw = self.race_data_manager.get_ghost_velocity_at_progress(progress_raw)
                self.ui.update_vdelta(
                    velocity_raw, ghost_vel_raw, should_show_overlays,
                    ghost_loaded=ghost_loaded and should_show_overlays,
                    delta_s=self.last_delta_s,
                    current_timer_us=timer_raw_us,
                )
                self.last_ui_update = now

            # -- Loop timing -------------------------------------------
            elapsed_ms = (systime.perf_counter() - loop_start) * 1000
            self.loop_times.append(elapsed_ms)
            self.avg_loop_time = sum(self.loop_times) / len(self.loop_times)
            self.ui.update_loop_time(elapsed_ms, self.avg_loop_time)


if __name__ == "__main__":
    tool = ALUTimingTool()
    try:
        tool.run_main_loop()
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    finally:
        tool.stop()
