"""
User Interface Module

This module handles the GUI for the ALU Timing Tool.
Visually based on the original v4 UI design, with v5 features (splits, pymem integration).
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import ctypes
import shutil
import threading
import sys
import os
from .ui_config import UIConfigManager


class TimingToolUI:
    """
    Main UI class for the ALU Timing Tool.
    Near 1:1 visual clone of the original v4 UI with added splits mode.
    """

    def __init__(self, race_data_manager=None):
        """Initialize the UI."""
        self.root = None
        self.is_pinned = True
        self.start_x = 0
        self.start_y = 0
        self.debug_expanded = False
        self.race_panel_expanded = False

        # UI Configuration Manager for position persistence
        self.config_manager = UIConfigManager()
        self.ui_config = self.config_manager.load_config()

        # Race data manager
        self.race_data_manager = race_data_manager

        # UI elements
        self.delta_label = None
        self.time_label = None
        self.elapsed_label = None
        self.avg_loop_label = None
        self.percentage_label = None
        self.pin_button = None
        self.close_button = None
        self.debug_button = None
        self.race_button = None
        self.debug_frame = None
        self.race_panel = None

        # Track current background color to avoid unnecessary updates
        self.current_bg_color = "#000000"

        # Race panel elements
        self.ghost_filename_label = None
        self.race_control_indicator = None
        self.mode_var = None
        self.mode_combobox = None
        self.load_ghost_button = None
        self.save_ghost_button = None
        self.vel_mode_var = None
        self.gear_rpm_var = None

        # Split view elements
        self.split_view_frame = None
        self.split_view_visible = False
        self.split_view_enabled = self.ui_config.get("splits_enabled", False)  # saved checkbox preference
        self.race_panel_auto_hidden = False
        self.splits_checkbox = None
        self.split_view_var = None
        self.gear_rpm_checkbox = None
        self.configure_splits_button = None
        self.rows = []

        # Gear / RPM bar elements
        self.main_container = None
        self.gear_rpm_frame = None
        self.gear_label = None
        self.rpm_canvas = None
        self.gear_rpm_visible = False
        self.gear_rpm_enabled = self.ui_config.get("gear_rpm_enabled", True)  # controlled by Gear/RPM dropdown
        self.current_gear = 0
        self.current_rpm = 1250

        # Steering bar elements
        self.steering_frame = None
        self.steering_label = None
        self.steering_border_frame = None
        self.steering_canvas = None
        self.steering_visible = False
        self.steering_enabled = self.ui_config.get("steering_enabled", True)
        self.steering_var = None       # BooleanVar
        self.steering_checkbox = None
        self.current_steering = 0.0

        # Velocity delta display elements
        self.vdelta_frame = None
        self.vdelta_label = None
        self.vdelta_ratio_label = None
        self.vdelta_visible = False
        self.vdelta_enabled = self.ui_config.get("vdelta_enabled", True)
        self.vdelta_var = None         # BooleanVar
        self.vdelta_checkbox = None
        self.current_vdelta = None     # None = no ghost velocity data available
        self.vdelta_height_shift = 0
        self._vdelta_has_vel = False    # whether left label is currently gridded
        self._ratio_prev_delta_s = None # for dΔ/dt when no velocity data
        self._ratio_prev_timer_us: int = 0

        # Batch show flag — suppresses individual _auto_resize() calls inside
        # begin_race_display() so all overlays pack with a single layout pass.
        self._batch_show: bool = False

        # Thread-safe deferred split-view reset: set by timer thread, consumed
        # by update_ui() which runs on the Tk main thread.
        self._pending_split_reset: bool = False

        # Velocity indicator elements
        self.velocity_frame = None
        self.velocity_label = None
        self.velocity_visible = False
        self.current_velocity = 0.0
        self.velocity_height_shift = 0
        self.vel_mode = self.ui_config.get("vel_mode", "Real KM/H")  # controlled by velocity mode dropdown

        # Data to display
        self.current_timer_display = "00:00.000"
        self.elapsed_ms = 0
        self.avg_loop_time = 0
        self.percentage = "0%"
        self.delta_time = "Rec..."  # Default delta text (shows Rec... in record mode)
        self.current_timer_us = 0
        self.progress = 0.0

        # Delta display font base size (adjust this to change the main display text size)
        self.DELTA_FONT_BASE = 65

        # Scaling adjustment - load from config
        self.current_scaling = self.ui_config.get("scaling", 1.15)

        # Callbacks for race functionality
        self.on_mode_change = None
        self.on_load_ghost = None
        self.on_save_ghost = None
        self.on_save_race = None
        self.on_close = None
        self.on_load_split = None
        self.on_configure_splits = None

        # Panel states from config
        self.race_panel_expanded = False  # Always opened on startup (create_ui calls toggle_race_panel)
        self.debug_expanded = self.ui_config.get("panels", {}).get("debug_panel_expanded", False)
        self.is_pinned = self.ui_config.get("is_pinned", True)

        # Loaded ghost name (basename, e.g. "911_v2.json") — used as save-dialog default
        self._current_ghost_name: str = ""

    # ──────────────────────────────────────────────────────────────────────
    #  Configuration persistence
    # ──────────────────────────────────────────────────────────────────────

    def save_ui_config(self):
        """Save current UI configuration to file."""
        try:
            if self.root:
                # Get current window geometry
                geometry = self.root.geometry()
                geometry_info = self.config_manager.extract_geometry_from_string(geometry)

                config = {
                    "window_position": geometry_info["window_position"],
                    "window_size": geometry_info["window_size"],
                    "scaling": self.current_scaling,
                    "is_pinned": self.is_pinned,
                    "vel_mode": self.vel_mode,
                    "gear_rpm_enabled": self.gear_rpm_enabled,
                    "steering_enabled": self.steering_enabled,
                    "splits_enabled": self.split_view_var.get() if self.split_view_var else self.split_view_enabled,
                    "vdelta_enabled": self.vdelta_enabled,
                    "panels": {
                        "race_panel_expanded": self.race_panel_expanded,
                        "debug_panel_expanded": self.debug_expanded,
                    },
                }

                success = self.config_manager.save_config(config)
                if success:
                    print("UI configuration saved successfully")
                else:
                    print("Failed to save UI configuration")
        except Exception as e:
            print(f"Error saving UI configuration: {e}")

    # ──────────────────────────────────────────────────────────────────────
    #  Window controls
    # ──────────────────────────────────────────────────────────────────────

    def toggle_pin(self):
        """Toggle window pin state."""
        self.is_pinned = not self.is_pinned
        if self.is_pinned:
        #    self.root.wm_attributes("-topmost", True)
            self.pin_button.config(text="○", bg="#95a5a6")
        else:
        #    self.root.wm_attributes("-topmost", False)
            self.pin_button.config(text="●", bg="#4ecdc4")

    def _auto_resize(self):
        """Let Tk compute natural window height based on packed content."""
        if self._batch_show:
            return  # deferred — begin_race_display() will call once at the end
        self.root.update_idletasks()
        current_geometry = self.root.geometry()
        parts = current_geometry.replace('x', '+').replace('+', ' ').split()
        width, x, y = parts[0], parts[2], parts[3]
        req_h = self.root.winfo_reqheight()
        self.root.geometry(f"{width}x{req_h}+{x}+{y}")

    def toggle_race_panel(self, _event=None):
        """Toggle race panel visibility."""
        self.race_panel_expanded = not self.race_panel_expanded
        if self.race_panel_expanded:
            self.race_panel.pack(side="top", fill="x", padx=0, pady=0)
            # If split view is visible, ensure it stays below the race panel.
            if self.split_view_visible and self.split_view_frame:
                self.split_view_frame.pack_forget()
                self._repack_split_view()
        else:
            self.race_panel.pack_forget()
            # Also collapse debug if open
            if self.debug_expanded:
                self.debug_frame.pack_forget()
                self.debug_expanded = False
                if hasattr(self, 'debug_button') and self.debug_button:
                    self.debug_button.config(bg="#3498db")
        self._auto_resize()

    def toggle_debug(self):
        """Toggle debug panel visibility within race panel."""
        if not self.race_panel_expanded:
            return

        self.debug_expanded = not self.debug_expanded
        if self.debug_expanded:
            self.debug_frame.pack(side="bottom", fill="x", padx=0, pady=(0, 0))
            if hasattr(self, 'debug_button') and self.debug_button:
                self.debug_button.config(bg="#2980b9")
        else:
            self.debug_frame.pack_forget()
            if hasattr(self, 'debug_button') and self.debug_button:
                self.debug_button.config(bg="#3498db")
        self._auto_resize()

    # ──────────────────────────────────────────────────────────────────────
    #  Mode / ghost / split handling
    # ──────────────────────────────────────────────────────────────────────

    def on_mode_changed(self, event=None):
        """Handle mode change."""
        mode = self.mode_var.get()
        py = int(8 * self.current_scaling)

        if mode == "Record Ghost":
            # Swap slot button: show Configure Splits, hide Load Race Ghost
            self.race_data_manager.is_split_loaded = False
            if self.load_ghost_button:
                self.load_ghost_button.pack_forget()
            if self.configure_splits_button and self.save_ghost_button:
                self.configure_splits_button.pack(fill="x", pady=(0, py),
                                                  before=self.save_ghost_button)
            
        else:  # race mode
            # Swap slot button: show Load Race Ghost, hide Configure Splits
            self.race_data_manager.is_split_loaded = self.race_data_manager.ghost_splits is not None
            if self.configure_splits_button:
                self.configure_splits_button.pack_forget()
            if self.load_ghost_button and self.save_ghost_button:
                self.load_ghost_button.pack(fill="x", pady=(0, py),
                                            before=self.save_ghost_button)
            # Restore ghost name display if still showing placeholder
            if self.ghost_filename_label:
                try:
                    if self.ghost_filename_label.cget("text") == "ALU Timer v5.0":
                        self.ghost_filename_label.config(text="No ghost loaded", fg="#e74c3c")
                except tk.TclError:
                    pass

        if self.splits_checkbox:
            if self.race_data_manager and getattr(self.race_data_manager, 'splits', None):
                self.splits_checkbox.config(state="normal")
            else:
                self.splits_checkbox.config(state="disabled")

        if self.vdelta_checkbox:
            if mode == "Record Ghost":
                self.vdelta_checkbox.config(state="disabled")
            else:
                self.vdelta_checkbox.config(state="normal")

        if self.on_mode_change:
            self.on_mode_change(mode)

    def on_vel_mode_changed(self, event=None):
        """Handle velocity mode dropdown change."""
        if self.vel_mode_var:
            self.vel_mode = self.vel_mode_var.get()
            # If disabled, immediately hide any visible velocity display
            if self.vel_mode == "Speed Off" and self.velocity_frame and self.velocity_visible:
                vh = self.velocity_height_shift
                self.velocity_height_shift = 0
                self.velocity_frame.pack_forget()
                self.velocity_visible = False
                self._auto_resize()
                try:
                    geo = self.root.geometry()
                    parts = geo.replace('x', '+').replace('+', ' ').split()
                    if len(parts) >= 4:
                        x, y = int(parts[2]), int(parts[3])
                        self.root.geometry(f"+{x}+{y + vh}")
                except (tk.TclError, ValueError):
                    pass

    def on_gear_rpm_changed(self, event=None):
        """Handle gear/RPM checkbox change."""
        if self.gear_rpm_var:
            self.gear_rpm_enabled = self.gear_rpm_var.get()
            # If disabled, immediately hide any visible gear/RPM display
            if not self.gear_rpm_enabled and self.gear_rpm_frame and self.gear_rpm_visible:
                self.gear_rpm_frame.pack_forget()
                self.gear_rpm_visible = False
                self._auto_resize()

    def _on_splits_checkbox_changed(self):
        """Handle splits checkbox toggle.

        Checking the box saves the preference for when the next race starts
        (begin_race_display picks it up).  If splits are loaded and the panel
        is hidden, it is shown immediately.  Unchecking hides the panel.
        """
        want = self.split_view_var.get() if self.split_view_var else False
        if want:
            if not self.split_view_visible:
                self.show_splits_if_enabled()
        elif self.split_view_visible:
            self.toggle_split_view()

    @staticmethod
    def _get_most_recent_json(runs_dir: str) -> str:
        """Return the filename of the most recently modified .json in runs_dir, or ''."""
        try:
            jsons = [f for f in os.listdir(runs_dir) if f.lower().endswith('.json')]
            if jsons:
                return max(jsons, key=lambda f: os.path.getmtime(os.path.join(runs_dir, f)))
        except Exception:
            pass
        return ""

    def load_ghost_file(self):
        """Open file dialog to load a ghost file."""
        if self.on_load_ghost:
            filetypes = [("JSON files", "*.json"), ("All files", "*.*")]
            runs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "runs")
            os.makedirs(runs_dir, exist_ok=True)
            filename = filedialog.askopenfilename(
                title="Load Race Ghost",
                filetypes=filetypes,
                initialdir=runs_dir,
                initialfile=self._get_most_recent_json(runs_dir),
            )
            if filename:
                self.on_load_ghost(filename)

    def load_split_file(self):
        """Open file dialog to load a split-type ghost file."""
        if hasattr(self, 'on_load_split') and self.on_load_split:
            filetypes = [("JSON files", "*.json"), ("All files", "*.*")]
            runs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "runs")
            os.makedirs(runs_dir, exist_ok=True)
            filename = filedialog.askopenfilename(
                title="Load Split Race Ghost",
                filetypes=filetypes,
                initialdir=runs_dir,
                initialfile=self._get_most_recent_json(runs_dir),
            )
            if filename:
                self.on_load_split(filename)

    def save_ghost_file(self):
        """Open file dialog to save current race data as ghost file."""
        if self.on_save_ghost:
            filetypes = [("JSON files", "*.json"), ("All files", "*.*")]
            runs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "runs")
            os.makedirs(runs_dir, exist_ok=True)
            # Default to the currently loaded ghost name so overwriting is one click.
            default_name = os.path.splitext(self._current_ghost_name)[0] if self._current_ghost_name else ""
            filename = filedialog.asksaveasfilename(
                title="Save Current Ghost",
                filetypes=filetypes,
                defaultextension=".json",
                initialdir=runs_dir,
                initialfile=default_name,
            )
            if filename:
                self.on_save_ghost(filename)

    def update_ghost_filename(self, filename: str):
        """Update the displayed ghost filename."""
        # Track the basename so save_ghost_file can default to it.
        self._current_ghost_name = os.path.basename(filename) if filename else ""
        if self.ghost_filename_label:
            try:
                if not self.ghost_filename_label.winfo_exists():
                    return
                if filename:
                    self.ghost_filename_label.config(text=filename, fg="#bdc3c7")
                else:
                    self.ghost_filename_label.config(text="No ghost loaded", fg="#e74c3c")
            except tk.TclError:
                pass

    def show_ghost_saved_message(self):
        """Show temporary 'Ghost Saved!' message."""
        if self.ghost_filename_label:
            try:
                if not self.ghost_filename_label.winfo_exists():
                    return
                original_text = self.ghost_filename_label.cget("text")
                original_color = self.ghost_filename_label.cget("fg")
                self.ghost_filename_label.config(text="Ghost Saved!", fg="#2ecc71",
                                                 font=("Helvetica", 9, "bold underline"))
            except tk.TclError:
                return

            def restore_text():
                if self.ghost_filename_label:
                    try:
                        if self.ghost_filename_label.winfo_exists():
                            self.ghost_filename_label.config(text=original_text, fg=original_color,
                                                             font=("Helvetica", 9))
                    except tk.TclError:
                        pass

            if self.root:
                self.root.after(1000, restore_text)

    def update_save_ghost_button_state(self):
        """Update save ghost button state based on race completion."""
        if hasattr(self, 'save_ghost_button') and self.save_ghost_button:
            try:
                if not self.save_ghost_button.winfo_exists():
                    return
                if self.race_data_manager and self.race_data_manager.data_exists():
                    self.save_ghost_button.config(state="normal", bg="#f39c12")
                else:
                    self.save_ghost_button.config(state="disabled", bg="#7f8c8d")
            except tk.TclError:
                pass

    def set_pb_detected(self, is_pb: bool):
        """
        Update the ALU Timer title label to indicate a new personal best.

        When is_pb is True the label changes to 'New PB! Save Ghost?' in green.
        When False it reverts to the default 'ALU Timer v5.0' in white.
        """
        if not hasattr(self, 'race_control_indicator') or not self.race_control_indicator:
            return
        try:
            if not self.race_control_indicator.winfo_exists():
                return
            if is_pb:
                self.race_control_indicator.config(text="New PB! Save Ghost?", fg="#2ecc71")
            else:
                self.race_control_indicator.config(text="ALU Timer v5.0", fg="white")
        except tk.TclError:
            pass

    # ──────────────────────────────────────────────────────────────────────
    #  Split view
    # ──────────────────────────────────────────────────────────────────────

    def open_configure_splits_dialog(self):
        """Open a dialog allowing the user to configure split names and percentages."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Configure Splits")
        dialog.geometry("800x675")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(bg="#000000")

        _font = ("Helvetica", 20)
        _font_bold = ("Helvetica", 20, "bold")

        tk.Label(dialog, text="Number of splits (2-10):", bg="#000000", fg="white", font=_font).pack(pady=(16, 8))
        initial_count = 2
        if self.race_data_manager and getattr(self.race_data_manager, 'splits', None):
            initial_count = len(self.race_data_manager.splits)
        count_var = tk.IntVar(value=initial_count)
        count_spin = tk.Spinbox(dialog, from_=2, to=10, textvariable=count_var, width=5, font=_font)
        count_spin.pack(pady=(0, 12))

        rows_frame = tk.Frame(dialog, bg="#000000")
        rows_frame.pack(fill="both", expand=True, padx=16, pady=8)

        entry_widgets = []

        def build_rows():
            for w in rows_frame.winfo_children():
                w.destroy()
            entry_widgets.clear()

            n = max(2, min(10, int(count_var.get())))
            existing = []
            if self.race_data_manager and getattr(self.race_data_manager, 'splits', None):
                existing = self.race_data_manager.splits

            for i in range(n):
                frame = tk.Frame(rows_frame, bg="#000000")
                frame.pack(fill="x", pady=4)
                tk.Label(frame, text=f"Split {i+1} name:", bg="#000000", fg="white", font=_font).pack(side="left")
                name_var = tk.StringVar(value=(existing[i][0] if i < len(existing) else f"split_{i+1}"))
                name_entry = tk.Entry(frame, textvariable=name_var, width=18, font=_font)
                name_entry.pack(side="left", padx=12)
                tk.Label(frame, text="Percent:", bg="#000000", fg="white", font=_font).pack(side="left")
                if i == n - 1:
                    percent_var = tk.IntVar(value=100)
                    tk.Label(frame, text="End", bg="#000000", fg="#ecf0f1", width=5, font=_font).pack(side="left", padx=12)
                else:
                    default_percent = (existing[i][1] if i < len(existing) else int(((i+1)/n)*100))
                    percent_var = tk.IntVar(value=default_percent)
                    tk.Spinbox(frame, from_=1, to=98, textvariable=percent_var, width=5, font=_font).pack(side="left", padx=12)
                entry_widgets.append((name_var, percent_var))

        def on_count_change(*_args):
            try:
                v = int(count_var.get())
            except Exception:
                v = 2
                count_var.set(2)
            v = max(2, min(10, v))
            count_var.set(v)
            build_rows()

        count_var.trace_add('write', lambda *_: on_count_change())
        build_rows()

        btn_frame = tk.Frame(dialog, bg="#000000")
        btn_frame.pack(pady=16)

        def save_and_close():
            splits_list = []
            try:
                for name_var, percent_var in entry_widgets:
                    name = name_var.get().strip()
                    percent = percent_var.get() / 100.0
                    splits_list.append([name, percent])
            except Exception:
                messagebox.showerror("Error", "Invalid split values")
                return

            if not (2 <= len(splits_list) <= 10):
                messagebox.showerror("Error", "Splits count must be between 2 and 10")
                return
            if splits_list[-1][1] != 1.0:
                messagebox.showerror("Error", "Last split percent must be 100%")
                return

            percents = [p for (_, p) in splits_list]
            if any(p < .01 or p > 1.0 for p in percents):
                messagebox.showerror("Error", "Split percents must be between 1 and 100%")
                return
            if any(percents[i] <= percents[i-1] for i in range(1, len(percents))):
                messagebox.showerror("Error", "Split percents must be strictly increasing")
                return

            if self.splits_checkbox:
                self.splits_checkbox.config(state="normal")

            # Back up existing split file before overwriting
            if (self.race_data_manager
                    and getattr(self.race_data_manager, 'is_split_loaded', False)
                    and getattr(self.race_data_manager, 'split_filepath', None)):
                try:
                    orig = self.race_data_manager.split_filepath
                    d, fname = os.path.split(orig)
                    base, ext = os.path.splitext(fname)
                    n = 0
                    while True:
                        candidate = os.path.join(d, f"{base} backup{ext}" if n == 0 else f"{base} backup {n}{ext}")
                        if not os.path.exists(candidate):
                            break
                        n += 1
                    shutil.copy(orig, candidate)
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to create backup: {e}")
                    return
                if hasattr(self.race_data_manager, 'save_split_data'):
                    saved = self.race_data_manager.save_split_data()
                    if not saved:
                        messagebox.showerror("Error", "Failed to save updated split file")
                        return

            if hasattr(self, 'on_configure_splits') and self.on_configure_splits:
                self.on_configure_splits(splits_list)

            dialog.destroy()

        tk.Button(btn_frame, text="Save", command=save_and_close, bg="#27ae60", fg="white", width=20, font=("Helvetica", 20, "bold")).pack(side="left", padx=12)
        tk.Button(btn_frame, text="Cancel", command=dialog.destroy, bg="#e74c3c", fg="white", width=20, font=("Helvetica", 20, "bold")).pack(side="left", padx=12)
        dialog.focus_set()

    def toggle_split_view(self):
        """Toggle the split comparison view visibility."""
        self.split_view_visible = not self.split_view_visible
        # Do NOT sync split_view_var here — the checkbox is preference-only.
        # auto_hide_race_overlays hides the split view without clearing the preference.
        if self.split_view_visible:
            if not self.split_view_frame:
                self.split_view_frame = tk.Frame(self.root, bg="#000000")
            # Position split view below race panel (or at top if race panel is hidden).
            self._repack_split_view()
            self.update_split_view()
        else:
            if self.split_view_frame:
                self.split_view_frame.pack_forget()
        self._auto_resize()

    def begin_race_display(self, mode: str, ghost_is_loaded: bool):
        """Show all race overlays atomically: one layout pass, one geometry shift.

        Replaces the four separate update_* show-calls at race-start so the
        window expands and repositions exactly once instead of stuttering
        through 4-5 individual resize + geometry operations.
        """
        if not self.root:
            return

        # ── Freeze layout updates until we're done packing everything ──
        self._batch_show = True

        # ── Frames that expand upward (packed BEFORE main_container) ──
        vel_will_show = (
            self.velocity_frame is not None
            and self.vel_mode != "Speed Off"
            and not self.velocity_visible
        )
        if vel_will_show:
            self.velocity_visible = True
            if self.main_container:
                self.velocity_frame.pack(side="top", fill="x", before=self.main_container)
            else:
                self.velocity_frame.pack(side="top", fill="x")
            try:
                self.velocity_label.config(text=self.format_velocity(0.0))
            except tk.TclError:
                pass

        vdelta_will_show = (
            self.vdelta_frame is not None
            and self.vdelta_enabled
            and ghost_is_loaded
            and self.vel_mode != "Speed Off"
            and not self.vdelta_visible
        )
        if vdelta_will_show:
            self.vdelta_visible = True
            if vel_will_show and self.velocity_frame:
                self.vdelta_frame.pack(side="top", fill="x", after=self.velocity_frame)
            elif self.main_container:
                self.vdelta_frame.pack(side="top", fill="x", before=self.main_container)
            else:
                self.vdelta_frame.pack(side="top", fill="x")

        # ── Frames that expand downward (packed AFTER main_container) ──
        if self.gear_rpm_frame and self.gear_rpm_enabled and not self.gear_rpm_visible:
            self.gear_rpm_visible = True
            if self.race_panel and self.race_panel.winfo_ismapped():
                self.gear_rpm_frame.pack(side="top", fill="x", before=self.race_panel)
            elif self.main_container:
                self.gear_rpm_frame.pack(side="top", fill="x", after=self.main_container)
            else:
                self.gear_rpm_frame.pack(side="top", fill="x")

        if self.steering_frame and self.steering_enabled and not self.steering_visible:
            self.steering_visible = True
            if self.gear_rpm_visible and self.gear_rpm_frame:
                self.steering_frame.pack(side="top", fill="x", after=self.gear_rpm_frame)
            elif self.race_panel and self.race_panel.winfo_ismapped():
                self.steering_frame.pack(side="top", fill="x", after=self.race_panel)
            elif self.main_container:
                self.steering_frame.pack(side="top", fill="x", after=self.main_container)
            else:
                self.steering_frame.pack(side="top", fill="x")

        # ── Split view: rebuild rows to blank state while hidden, then show ──
        want_split = (
            self.split_view_var and self.split_view_var.get()
            and not self.split_view_visible
            and self.race_data_manager
            and getattr(self.race_data_manager, 'splits', None)
        )
        if want_split:
            if not self.split_view_frame:
                self.split_view_frame = tk.Frame(self.root, bg="#000000")
            # Rebuild rows from reset data BEFORE making frame visible — no flicker.
            self.update_split_view()
            self.split_view_visible = True
            self._repack_split_view()

        # ── Auto-hide race panel while racing ──
        if self.race_panel_expanded and not self.debug_expanded:
            self.race_panel_auto_hidden = True
            self.race_panel.pack_forget()
            self.race_panel_expanded = False
            if self.race_button:
                self.race_button.config(text="▾", bg="#e67e22")

        # ── Release batch lock, measure heights, apply single geometry change ──
        self._batch_show = False
        self.root.update_idletasks()

        total_upward = 0
        if vel_will_show and self.velocity_frame:
            try:
                vh = self.velocity_frame.winfo_reqheight()
                self.velocity_height_shift = vh
                total_upward += vh
            except tk.TclError:
                pass
        if vdelta_will_show and self.vdelta_frame:
            try:
                self.vdelta_height_shift = self.vdelta_frame.winfo_reqheight()
            except tk.TclError:
                pass
            # vdelta sits BELOW the speedometer — window does not shift up for it.

        if total_upward > 0:
            try:
                geo = self.root.geometry()
                parts = geo.replace('x', '+').replace('+', ' ').split()
                if len(parts) >= 4:
                    x, y = int(parts[2]), int(parts[3])
                    self.root.geometry(f"+{x}+{y - total_upward}")
            except (tk.TclError, ValueError):
                pass

        self._auto_resize()

        # Trigger initial bar redraws
        if self.gear_rpm_visible:
            self._draw_rpm_bar()
        if self.steering_visible:
            self._draw_steering_bar()

    def schedule_split_view_reset(self, delay_ms: int = 150):
        """Schedule a background rebuild of split-view rows to blank/dash state.

        Called after race end while the split view is invisible, so when it
        appears at the next race start it shows clean rows instead of stale
        times and deltas from the previous race.

        Thread-safe: sets a flag that update_ui() (running on the Tk thread)
        picks up and converts to a root.after() call.
        """
        self._pending_split_reset = True

    def _reset_split_view_if_hidden(self):
        """Rebuild split-view rows only while the view is not visible."""
        if not self.split_view_visible and self.split_view_frame:
            try:
                self.update_split_view()
            except Exception:
                pass

    def show_splits_if_enabled(self):
        """Populate rows and show the split panel if the user has it enabled and splits are loaded.

        Rows are rebuilt while the panel is hidden so the show is instant with
        no flicker.  Safe to call from any callback — no-ops if conditions are
        not met.
        """
        if not self.split_view_var or not self.split_view_var.get():
            return  # checkbox is off — don't force the panel open
        if not (self.race_data_manager and getattr(self.race_data_manager, 'splits', None)):
            return  # no splits loaded
        # Rebuild rows while panel is still hidden to avoid flicker.
        try:
            self.update_split_view()
        except Exception:
            pass
        if not self.split_view_visible:
            self.toggle_split_view()

    def update_splits_checkbox_state(self):
        """Enable the splits checkbox when splits are loaded; disable it otherwise."""
        if not self.splits_checkbox:
            return
        has_splits = bool(self.race_data_manager and getattr(self.race_data_manager, 'splits', None))
        try:
            self.splits_checkbox.config(state="normal" if has_splits else "disabled")
        except tk.TclError:
            pass

    def restore_race_panel(self):
        """Restore the race panel if it was auto-hidden at race start.

        Called at race *end* (not at menus).  Split view is intentionally
        left visible — it stays on screen until the player returns to menus.
        """
        if self.race_panel_auto_hidden:
            self.race_panel_auto_hidden = False
            try:
                self.race_panel.pack(side="top", fill="x", padx=0, pady=0)
                self.race_panel_expanded = True
                if self.race_button:
                    self.race_button.config(text="\u25b4", bg="#e67e22")
                if self.split_view_visible and self.split_view_frame:
                    self.split_view_frame.pack_forget()
                    self._repack_split_view()
                self._auto_resize()
            except tk.TclError:
                pass

    def auto_show_race_overlays(self):
        """Show race-only overlays (split view) and auto-hide the race panel."""
        # Show split view if checkbox is checked and splits are loaded
        if (
            self.split_view_var and self.split_view_var.get()
            and not self.split_view_visible
            and self.race_data_manager
            and getattr(self.race_data_manager, 'splits', None)
        ):
            self.toggle_split_view()

        # Auto-hide race panel while racing, unless debug is open
        if self.race_panel_expanded and not self.debug_expanded:
            self.race_panel_auto_hidden = True
            self.race_panel.pack_forget()
            self.race_panel_expanded = False
            if self.race_button:
                self.race_button.config(text="▾", bg="#e67e22")
            self._auto_resize()

    def auto_hide_race_overlays(self):
        """Hide race-only overlays (split view) and restore the race panel."""
        # Hide split view
        if self.split_view_visible:
            self.toggle_split_view()

        # Restore race panel if it was auto-hidden
        if self.race_panel_auto_hidden:
            self.race_panel_auto_hidden = False
            self.race_panel.pack(side="top", fill="x", padx=0, pady=0)
            self.race_panel_expanded = True
            if self.race_button:
                self.race_button.config(text="▴", bg="#e67e22")
            # Keep split view below the race panel if it re-appears somehow
            if self.split_view_visible and self.split_view_frame:
                self.split_view_frame.pack_forget()
                self._repack_split_view()
            self._auto_resize()

    # ──────────────────────────────────────────────────────────────────────
    #  Gear / RPM bar
    # ──────────────────────────────────────────────────────────────────────

    def _create_gear_rpm_bar(self):
        """Create the gear/RPM bar widget (packed into root, hidden by default)."""
        bar_h = 52  # 35 * 1.5

        self.gear_rpm_frame = tk.Frame(self.root, bg="#000000", height=bar_h)
        self.gear_rpm_frame.pack_propagate(False)
        # NOT packed — only shown when update_gear_rpm is called with racing=True

        inner = tk.Frame(self.gear_rpm_frame, bg="#000000")
        inner.pack(fill="both", expand=True, padx=(4, 4), pady=3)

        self.gear_label = tk.Label(
            inner, text="0", width=2,
            font=("Helvetica", 40, "bold"),
            fg="#ecf0f1", bg="#000000", anchor="center",
        )
        self.gear_label.pack(side="left", padx=(0, 4))

        canvas_bg = "#222222"
        canvas_frame = tk.Frame(inner, bg=canvas_bg, bd=0, highlightthickness=0)
        canvas_frame.pack(side="left", fill="both", expand=True)

        self.rpm_canvas = tk.Canvas(
            canvas_frame, bg=canvas_bg, highlightthickness=0,
        )
        self.rpm_canvas.pack(fill="both", expand=True)
        self.rpm_canvas.bind("<Configure>", lambda _e: self._draw_rpm_bar())

    def _draw_rpm_bar(self):
        """Redraw the RPM canvas bar based on current_gear / current_rpm."""
        if not self.rpm_canvas or not self.gear_label:
            return
        try:
            RPM_MIN  = 1250
            RPM_MAX  = 8700

            # Gear ratios (gear index → relative ratio; gear 5 = 1.0 reference)
            GEAR_RATIOS = {1: 0.3, 2: 0.5, 3: 2/3, 4: 5/6, 5: 1.0}
            DOWNSHIFT_ENGAGE  = 6400  # RPM in the lower gear that triggers color change (buffer)
            DOWNSHIFT_ACTUAL  = 6200  # RPM in the lower gear where the actual autoshift fires
            UPSHIFT_NORMAL    = 7250  # RPM (current gear) for upshift without nitro
            UPSHIFT_NITRO     = 8200  # RPM (current gear) for upshift with nitro

            g = self.current_gear
            if g >= 2:
                r_cur  = GEAR_RATIOS.get(g,  GEAR_RATIOS[5])
                r_prev = GEAR_RATIOS.get(g - 1, GEAR_RATIOS[1])
                # RPM_in_lower = RPM_current * (r_cur / r_prev)
                # Red when RPM_in_lower < DOWNSHIFT_ENGAGE
                # → RPM_current < DOWNSHIFT_ENGAGE * (r_prev / r_cur)
                downshift_threshold = DOWNSHIFT_ENGAGE * (r_prev / r_cur)
                downshift_line_rpm  = DOWNSHIFT_ACTUAL  * (r_prev / r_cur)
            else:
                downshift_threshold = RPM_MIN  # gear 0/1 — never red
                downshift_line_rpm  = None     # no downshift line for gear 0/1

            rpm = self.current_rpm
            if   rpm >= 8000:
                bar_color = "#3498db"   # blue  — near/at limiter
            elif rpm >= 7000:
                bar_color = "#2ecc71"   # yellow — high RPM
            elif rpm >= downshift_threshold:
                bar_color = "#f1c40f"   # green  — normal
            else:
                bar_color = "#e74c3c"   # red    — should downshift

            fill_ratio = max(0.0, min(1.0, (rpm - RPM_MIN) / (RPM_MAX - RPM_MIN)))
            gear_text = str(g) if g > 0 else "N"
            self.gear_label.config(text=gear_text)

            w = self.rpm_canvas.winfo_width()
            h = self.rpm_canvas.winfo_height()
            if w <= 1 or h <= 1:
                return

            fill_w = int(w * fill_ratio)

            # Update background item in-place (no delete → no blank-frame flicker)
            if self.rpm_canvas.find_withtag("rpm_bg"):
                self.rpm_canvas.coords("rpm_bg", 0, 0, w, h)
            else:
                self.rpm_canvas.create_rectangle(0, 0, w, h, fill="#222222", outline="", tags="rpm_bg")

            # Update fill item in-place
            if fill_w > 0:
                if self.rpm_canvas.find_withtag("rpm_fill"):
                    self.rpm_canvas.coords("rpm_fill", 0, 0, fill_w, h)
                    self.rpm_canvas.itemconfig("rpm_fill", fill=bar_color, state="normal")
                else:
                    self.rpm_canvas.create_rectangle(0, 0, fill_w, h, fill=bar_color, outline="", tags="rpm_fill")
            else:
                if self.rpm_canvas.find_withtag("rpm_fill"):
                    self.rpm_canvas.itemconfig("rpm_fill", state="hidden")

            # ── Vertical marker lines ──────────────────────────────────
            def _rpm_to_x(r):
                return int(w * max(0.0, min(1.0, (r - RPM_MIN) / (RPM_MAX - RPM_MIN))))

            # Downshift marker (gear-dependent — only in gear 2+)
            if downshift_line_rpm is not None:
                dl_x = _rpm_to_x(downshift_line_rpm)
                if self.rpm_canvas.find_withtag("rpm_line_down"):
                    self.rpm_canvas.coords("rpm_line_down", dl_x, 0, dl_x, h)
                    self.rpm_canvas.itemconfig("rpm_line_down", state="normal")
                else:
                    self.rpm_canvas.create_line(dl_x, 0, dl_x, h, fill="white", width=2, tags="rpm_line_down")
            else:
                if self.rpm_canvas.find_withtag("rpm_line_down"):
                    self.rpm_canvas.itemconfig("rpm_line_down", state="hidden")

            # Upshift without nitro marker
            up_x = _rpm_to_x(UPSHIFT_NORMAL)
            if self.rpm_canvas.find_withtag("rpm_line_up"):
                self.rpm_canvas.coords("rpm_line_up", up_x, 0, up_x, h)
                self.rpm_canvas.itemconfig("rpm_line_up", state="normal")
            else:
                self.rpm_canvas.create_line(up_x, 0, up_x, h, fill="white", width=2, tags="rpm_line_up")

            # Upshift with nitro marker
            nitro_x = _rpm_to_x(UPSHIFT_NITRO)
            if self.rpm_canvas.find_withtag("rpm_line_nitro"):
                self.rpm_canvas.coords("rpm_line_nitro", nitro_x, 0, nitro_x, h)
                self.rpm_canvas.itemconfig("rpm_line_nitro", state="normal")
            else:
                self.rpm_canvas.create_line(nitro_x, 0, nitro_x, h, fill="white", width=2, tags="rpm_line_nitro")

            # Raise marker lines above the fill bar
            for _tag in ("rpm_line_down", "rpm_line_up", "rpm_line_nitro"):
                if self.rpm_canvas.find_withtag(_tag):
                    self.rpm_canvas.tag_raise(_tag)

            # Keep background behind fill
            self.rpm_canvas.tag_lower("rpm_bg", "rpm_fill")
        except tk.TclError:
            pass

    # ──────────────────────────────────────────────────────────────────────
    #  Steering bar
    # ──────────────────────────────────────────────────────────────────────

    def _create_steering_display(self):
        """Create the steering input bar widget (hidden by default)."""
        bar_h = 46

        self.steering_frame = tk.Frame(self.root, bg="#000000", height=bar_h)
        self.steering_frame.pack_propagate(False)
        # NOT packed — only shown when update_steering is called with racing=True

        inner = tk.Frame(self.steering_frame, bg="#000000")
        inner.pack(fill="both", expand=True, padx=(4, 4), pady=3)

        self.steering_label = tk.Label(
            inner, text="0", width=3,
            font=("Helvetica", 28, "bold"),
            fg="#ecf0f1", bg="#000000", anchor="center",
        )
        self.steering_label.pack(side="left", padx=(0, 0))

        # Border frame — padx/pady act as the outline thickness
        self.steering_border_frame = tk.Frame(inner, bg="#555555", padx=4, pady=4)
        self.steering_border_frame.pack(side="left", fill="both", expand=True)

        self.steering_canvas = tk.Canvas(
            self.steering_border_frame, bg="#222222", highlightthickness=0,
        )
        self.steering_canvas.pack(fill="both", expand=True)
        self.steering_canvas.bind("<Configure>", lambda _e: self._draw_steering_bar())

    def _draw_steering_bar(self):
        """Redraw the steering canvas bar based on current_steering."""
        if not self.steering_canvas or not self.steering_label or not self.steering_border_frame:
            return
        try:
            s = max(-1.0, min(1.0, self.current_steering))
            pct = int(round(s * 100))
            self.steering_label.config(text=str(pct))

            # Outline colour: green at 0, red at ±1, neutral otherwise
            if s == 0.0:
                border_color = "#27ae60"   # green
            elif abs(s) >= 1.0:
                border_color = "#e74c3c"   # red
            else:
                border_color = "#555555"   # neutral dark grey
            self.steering_border_frame.config(bg=border_color)

            w = self.steering_canvas.winfo_width()
            h = self.steering_canvas.winfo_height()
            if w <= 1 or h <= 1:
                return

            center_x = w // 2
            fill_w = int(abs(s) * center_x)

            # Background — update in-place
            if self.steering_canvas.find_withtag("steer_bg"):
                self.steering_canvas.coords("steer_bg", 0, 0, w, h)
            else:
                self.steering_canvas.create_rectangle(
                    0, 0, w, h, fill="#222222", outline="", tags="steer_bg"
                )

            # Fill — extends left from center (negative) or right (positive)
            if fill_w > 0:
                fx1 = center_x - fill_w if s < 0 else center_x
                fx2 = center_x          if s < 0 else center_x + fill_w
                if self.steering_canvas.find_withtag("steer_fill"):
                    self.steering_canvas.coords("steer_fill", fx1, 0, fx2, h)
                    self.steering_canvas.itemconfig("steer_fill", state="normal")
                else:
                    self.steering_canvas.create_rectangle(
                        fx1, 0, fx2, h, fill="#e67e22", outline="", tags="steer_fill"
                    )
            else:
                if self.steering_canvas.find_withtag("steer_fill"):
                    self.steering_canvas.itemconfig("steer_fill", state="hidden")

            # Centre tick line
            if self.steering_canvas.find_withtag("steer_center"):
                self.steering_canvas.coords("steer_center", center_x, 0, center_x, h)
            else:
                self.steering_canvas.create_line(
                    center_x, 0, center_x, h, fill="#ecf0f1", width=2, tags="steer_center"
                )

            # Z-order: bg → fill → center line
            self.steering_canvas.tag_lower("steer_bg")
            try:
                self.steering_canvas.tag_raise("steer_fill", "steer_bg")
            except Exception:
                pass
            self.steering_canvas.tag_raise("steer_center")
        except tk.TclError:
            pass

    def on_steering_changed(self, event=None):
        """Handle steering checkbox change."""
        if self.steering_var:
            self.steering_enabled = self.steering_var.get()
            if not self.steering_enabled and self.steering_frame and self.steering_visible:
                self.steering_frame.pack_forget()
                self.steering_visible = False
                self._auto_resize()

    def update_steering(self, steering: float, racing: bool):
        """Show/update the steering bar during a race; hide it otherwise."""
        self.current_steering = steering

        if not self.steering_frame:
            return

        if not self.steering_enabled:
            racing = False

        was_visible = self.steering_visible
        self.steering_visible = racing

        if racing and not was_visible:
            # Pack below gear/RPM frame (or after main_container if gear not shown)
            if self.gear_rpm_frame and self.gear_rpm_visible:
                self.steering_frame.pack(
                    side="top", fill="x", after=self.gear_rpm_frame, padx=0, pady=0
                )
            elif self.race_panel and self.race_panel.winfo_ismapped():
                self.steering_frame.pack(
                    side="top", fill="x", after=self.race_panel, padx=0, pady=0
                )
            elif self.main_container:
                self.steering_frame.pack(
                    side="top", fill="x", after=self.main_container, padx=0, pady=0
                )
            else:
                self.steering_frame.pack(side="top", fill="x", padx=0, pady=0)
            self._auto_resize()
        elif not racing and was_visible:
            self.steering_frame.pack_forget()
            self._auto_resize()

        if racing:
            self._draw_steering_bar()

    # ──────────────────────────────────────────────────────────────────────
    #  Velocity delta display
    # ──────────────────────────────────────────────────────────────────────

    def _velocity_to_float(self, speed_raw: float) -> float:
        """Convert raw velocity (m/s) to current display units as a float."""
        if self.vel_mode in ("Fake KM/H", "Fake MPH"):
            if 0 <= speed_raw < 100/3.6:
                pass
            elif 100/3.6 <= speed_raw < 200/3.6:
                speed_raw = speed_raw*1.35 - 35/3.6
            elif 200/3.6 <= speed_raw < 300/3.6:
                speed_raw = speed_raw*1.85 - 135/3.6
            elif 300/3.6 <= speed_raw < 350/3.6:
                speed_raw = speed_raw*2.6 - 360/3.6
            elif speed_raw >= 350/3.6:
                speed_raw = speed_raw - 200/3.6
            else:
                return 0.0
        if self.vel_mode in ("Fake MPH", "Real MPH"):
            return speed_raw * 2.23694
        elif self.vel_mode in ("Fake KM/H", "Real KM/H"):
            return speed_raw * 3.6
        return 0.0

    def _create_vdelta_display(self):
        """Create the velocity delta label widget (hidden by default)."""
        # Fixed frame height clips surplus font whitespace, same approach as
        # velocity_frame — the labels are anchored to the bottom of the frame.
        vd_h = int(26 * self.current_scaling)
        self.vdelta_frame = tk.Frame(self.root, bg="#000000", height=vd_h)
        self.vdelta_frame.pack_propagate(False)
        self.vdelta_frame.columnconfigure(0, weight=1, uniform="vdcol")
        self.vdelta_frame.columnconfigure(1, weight=1, uniform="vdcol")
        # NOT packed until update_vdelta shows it
        _vd_font = ("Franklin Gothic Heavy", 44)
        self.vdelta_label = tk.Label(
            self.vdelta_frame, text="=0.00",
            font=_vd_font,
            fg="#ecf0f1", bg="#000000",
            anchor="se", justify="right",
        )
        self.vdelta_label.grid(row=0, column=0, sticky="sew", padx=(4, 6), pady=0)
        self.vdelta_ratio_label = tk.Label(
            self.vdelta_frame, text="=0.000",
            font=_vd_font,
            fg="#ecf0f1", bg="#000000",
            anchor="se", justify="right",
        )
        self.vdelta_ratio_label.grid(row=0, column=1, sticky="sew", padx=(0, 4), pady=0)

    def on_vdelta_changed(self, event=None):
        """Handle velocity delta checkbox change."""
        if self.vdelta_var:
            self.vdelta_enabled = self.vdelta_var.get()
            if not self.vdelta_enabled and self.vdelta_frame and self.vdelta_visible:
                self.vdelta_height_shift = 0
                self.vdelta_frame.pack_forget()
                self.vdelta_visible = False
                self._auto_resize()

    def update_vdelta(self, current_vel_raw: float, ghost_vel_raw, racing: bool,
                       *, ghost_loaded: bool = False, delta_s: float = None,
                       current_timer_us: int = 0):
        """Show/update velocity delta (current − ghost) during a race; hide otherwise.

        Args:
            current_vel_raw:  Current velocity in m/s.
            ghost_vel_raw:    Ghost velocity in m/s, or None if ghost has no vel data.
            racing:           Whether overlays should be shown.
            ghost_loaded:     Whether any ghost is loaded (enables display even without vel).
            delta_s:          Current time delta in seconds (for ratio when no vel data).
            current_timer_us: Current race timer in microseconds (for ratio derivative).
        """
        if not self.vdelta_frame:
            return

        show = (
            racing
            and self.vdelta_enabled
            and ghost_loaded
            and self.vel_mode != "Speed Off"
        )
        has_vel = ghost_vel_raw is not None

        if show:
            # ── Manage left/right label grid layout based on velocity availability ──
            if has_vel != self._vdelta_has_vel:
                self._vdelta_has_vel = has_vel
                try:
                    if has_vel:
                        # Restore two-column layout
                        self.vdelta_label.grid(row=0, column=0, sticky="ew",
                                               padx=(4, 6), pady=0, columnspan=1)
                        self.vdelta_ratio_label.grid(row=0, column=1, sticky="ew",
                                                     padx=(0, 4), pady=0, columnspan=1)
                    else:
                        # No velocity data: hide left label, ratio spans full width
                        self.vdelta_label.grid_remove()
                        self.vdelta_ratio_label.grid(row=0, column=0, sticky="ew",
                                                     padx=(4, 4), pady=0, columnspan=2)
                except tk.TclError:
                    pass

            if has_vel:
                # ── Velocity delta label (left) ──
                cur = self._velocity_to_float(current_vel_raw)
                gst = self._velocity_to_float(ghost_vel_raw)
                vd = cur - gst
                self.current_vdelta = vd
                if abs(vd) < 0.005:
                    text, color = "=0.00", "#ecf0f1"
                elif vd > 0:
                    text = f"+{round(vd, 2):.2f}"
                    color = "#27ae60"   # green — you are faster
                else:
                    text = f"\u2212{round(abs(vd), 2):.2f}"
                    color = "#e74c3c"   # red — you are slower
                try:
                    self.vdelta_label.config(text=text, fg=color)
                except tk.TclError:
                    pass
                # ── Time gain ratio (right): ratio = v_cur/v_ghost - 1 ──
                try:
                    if abs(ghost_vel_raw) > 0.1:
                        ratio = current_vel_raw / ghost_vel_raw - 1.0
                        if abs(ratio) < 0.0005:
                            rtxt, rcol = "=0.000", "#ecf0f1"
                        elif ratio > 0:
                            rtxt = f"+{ratio:.3f}"
                            rcol = "#27ae60"
                        else:
                            rtxt = f"\u2212{abs(ratio):.3f}"
                            rcol = "#e74c3c"
                    else:
                        rtxt, rcol = "=0.000", "#ecf0f1"
                    if self.vdelta_ratio_label:
                        self.vdelta_ratio_label.config(text=rtxt, fg=rcol)
                except tk.TclError:
                    pass
            else:
                # No velocity data: compute ratio from derivative of delta
                self.current_vdelta = None
                try:
                    if (delta_s is not None
                            and self._ratio_prev_delta_s is not None
                            and current_timer_us > self._ratio_prev_timer_us
                            and (current_timer_us - self._ratio_prev_timer_us) > 50000):
                        dt_s = (current_timer_us - self._ratio_prev_timer_us) / 1_000_000.0
                        ratio = (delta_s - self._ratio_prev_delta_s) / dt_s
                        if abs(ratio) < 0.0005:
                            rtxt, rcol = "=0.000", "#ecf0f1"
                        elif ratio > 0:
                            rtxt = f"+{ratio:.3f}"
                            rcol = "#27ae60"
                        else:
                            rtxt = f"\u2212{abs(ratio):.3f}"
                            rcol = "#e74c3c"
                    else:
                        rtxt, rcol = "-.---", "#ecf0f1"
                    if self.vdelta_ratio_label:
                        self.vdelta_ratio_label.config(text=rtxt, fg=rcol)
                except tk.TclError:
                    pass
                # Advance derivative tracking
                if delta_s is not None and current_timer_us > 0:
                    self._ratio_prev_delta_s = delta_s
                    self._ratio_prev_timer_us = current_timer_us
        else:
            self.current_vdelta = None

        # Reset derivative tracking when display transitions to visible
        if show and not self.vdelta_visible and not has_vel:
            self._ratio_prev_delta_s = None
            self._ratio_prev_timer_us = 0

        was_visible = self.vdelta_visible
        self.vdelta_visible = show

        if show and not was_visible:
            if self.velocity_frame and self.velocity_visible:
                self.vdelta_frame.pack(side="top", fill="x", after=self.velocity_frame)
            elif self.main_container:
                self.vdelta_frame.pack(side="top", fill="x", before=self.main_container)
            else:
                self.vdelta_frame.pack(side="top", fill="x")
            self.root.update_idletasks()
            self.vdelta_height_shift = self.vdelta_frame.winfo_reqheight()
            # vdelta sits below the speedometer — window top does not shift.
            self._auto_resize()
        elif not show and was_visible:
            self.vdelta_height_shift = 0
            self.vdelta_frame.pack_forget()
            # vdelta sits below the speedometer — window top does not shift.
            self._auto_resize()

    def format_velocity(self, speed_raw: float) -> str:
        """Convert raw velocity (m/s) to km/h and format as string."""
        if self.vel_mode in ("Fake KM/H","Fake MPH"):
            if 0 <= speed_raw < 100/3.6:
                pass
            elif 100/3.6 <= speed_raw < 200/3.6:
                speed_raw = speed_raw*1.35 - 35/3.6
            elif 200/3.6 <= speed_raw < 300/3.6:
                speed_raw = speed_raw*1.85 - 135/3.6
            elif 300/3.6 <= speed_raw < 350/3.6:
                speed_raw = speed_raw*2.6 - 360/3.6
            elif speed_raw >= 350/3.6:
                speed_raw = speed_raw + 200/3.6
            else:
                return "0.0"
        if self.vel_mode in ("Fake MPH","Real MPH"):
            speed_raw = speed_raw * 2.23694
        elif self.vel_mode in ("Fake KM/H","Real KM/H"):
            speed_raw = speed_raw * 3.6
        else:
            return "0.0"
        speed_output = round(speed_raw,1)
        return f"{speed_output:.1f}"

    def _create_velocity_display(self):
        """Create the velocity indicator widget (hidden by default)."""
        # Fixed frame height clips the surplus ascender/descender whitespace that
        # Tk reserves for the font's full line-height while keeping digits fully
        # visible (numbers have no descenders so the bottom ~30% can be cropped).
        vel_h = int(85 * self.current_scaling)
        self.velocity_frame = tk.Frame(self.root, bg="#000000", height=vel_h)
        self.velocity_frame.pack_propagate(False)
        # NOT packed — only shown when update_velocity is called with racing=True
        self.velocity_label = tk.Label(
            self.velocity_frame, text="0.0",
            font=("Franklin Gothic Heavy", 110),
            fg="#ecf0f1", bg="#000000", anchor="e",
        )
        self.velocity_label.pack(fill="x", padx=(4, 4), pady=0)

    def update_velocity(self, speed_kmh: float, racing: bool):
        """Show/update the velocity indicator during a race; hide it otherwise."""
        self.current_velocity = speed_kmh

        if not self.velocity_frame:
            return

        # Never show if velocity mode is Disabled
        if self.vel_mode == "Speed Off":
            racing = False

        was_visible = self.velocity_visible
        self.velocity_visible = racing

        if racing:
            try:
                self.velocity_label.config(text=self.format_velocity(speed_kmh))
            except tk.TclError:
                pass

        if racing and not was_visible:
            # Pack at the very top of the window, before main_container
            if self.main_container:
                self.velocity_frame.pack(side="top", fill="x", before=self.main_container)
            else:
                self.velocity_frame.pack(side="top", fill="x")
            self.root.update_idletasks()
            try:
                vh = self.velocity_frame.winfo_reqheight()
            except tk.TclError:
                vh = int(95 * self.current_scaling)
            self.velocity_height_shift = vh
            # Move window top up so the delta panel stays at the same screen position
            try:
                geo = self.root.geometry()
                parts = geo.replace('x', '+').replace('+', ' ').split()
                if len(parts) >= 4:
                    x, y = int(parts[2]), int(parts[3])
                    self.root.geometry(f"+{x}+{y - vh}")
            except (tk.TclError, ValueError):
                pass
            self._auto_resize()
        elif not racing and was_visible:
            vh = self.velocity_height_shift
            self.velocity_height_shift = 0
            self.velocity_frame.pack_forget()
            # Resize height first (preserves current shifted-up y), then correct position
            self._auto_resize()
            # Move window down to restore original position
            try:
                geo = self.root.geometry()
                parts = geo.replace('x', '+').replace('+', ' ').split()
                if len(parts) >= 4:
                    x, y = int(parts[2]), int(parts[3])
                    self.root.geometry(f"+{x}+{y + vh}")
            except (tk.TclError, ValueError):
                pass

    def update_gear_rpm(self, gear: int, rpm: int, racing: bool):
        """Show/update the gear+RPM bar during a race; hide it otherwise."""
        self.current_gear = gear
        self.current_rpm = rpm

        if not self.gear_rpm_frame:
            return

        # Never show if gear/RPM display is disabled
        if not self.gear_rpm_enabled:
            racing = False

        was_visible = self.gear_rpm_visible
        self.gear_rpm_visible = racing

        if racing and not was_visible:
            # Place bar immediately after main_container, before race_panel
            if self.race_panel and self.race_panel.winfo_ismapped():
                self.gear_rpm_frame.pack(side="top", fill="x", before=self.race_panel)
            elif self.main_container:
                self.gear_rpm_frame.pack(side="top", fill="x", after=self.main_container)
            else:
                self.gear_rpm_frame.pack(side="top", fill="x")
            self._auto_resize()
        elif not racing and was_visible:
            self.gear_rpm_frame.pack_forget()
            self._auto_resize()

        if racing:
            self._draw_rpm_bar()

    def _format_time_ms(self, raw_us: int) -> str:
        try:
            if not raw_us or raw_us == 0:
                return "--.---"
            seconds = raw_us / 1000000.0
            return f"{round(seconds,3):.3f}"
        except Exception:
            return "--.---"

    def _format_delta_ms(self, delta_us: int) -> str:
        try:
            if delta_us is None:
                return "--.---"
            sign = '-' if delta_us <= 0 else '+'
            s = abs(delta_us) / 1000000.0
            return f"{sign}{round(s,3):.3f}"
        except Exception:
            return "--.---"

    def _repack_split_view(self):
        """Re-attach split_view_frame below steering (if visible), gear/RPM, race panel, or top."""
        if self.race_panel and self.race_panel.winfo_ismapped():
            self.split_view_frame.pack(side="top", fill="x", after=self.race_panel, padx=0, pady=(0, 0))
        elif self.steering_frame and self.steering_visible:
            self.split_view_frame.pack(side="top", fill="x", after=self.steering_frame, padx=0, pady=(0, 0))
        elif self.gear_rpm_frame and self.gear_rpm_visible:
            self.split_view_frame.pack(side="top", fill="x", after=self.gear_rpm_frame, padx=0, pady=(0, 0))
        else:
            self.split_view_frame.pack(side="top", fill="x", padx=0, pady=(0, 0))

    def update_split_view(self):
        """Rebuild the split comparison view from current split data."""
        if not self.split_view_frame:
            self.split_view_frame = tk.Frame(self.root, bg="#000000")

        splits, current, ghost = None, None, None
        if self.race_data_manager and hasattr(self.race_data_manager, 'get_splits'):
            splits, current, ghost = self.race_data_manager.get_splits()

        has_ghost = ghost is not None and self.race_data_manager.is_split_loaded
        has_live = current is not None and len(current) > 0

        # Check whether existing row frames are still valid Tk widgets.
        # They can become stale after a scaling rebuild or if the split view
        # frame was destroyed externally without going through the normal cleanup.
        rows_valid = bool(self.rows) and all(
            (r is not None and r.winfo_exists()) for r in self.rows
        )
        is_init = (
            current is None
            or len(current) == 0
            or len(current) == len(splits)
            or not rows_valid
        )

        # Hide frame before bulk widget creation so all updates are batched
        # into a single render pass when the frame is re-attached.
        was_mapped = False
        if is_init:
            try:
                was_mapped = self.split_view_frame.winfo_ismapped()
            except tk.TclError:
                # Frame was destroyed (e.g. after a scaling rebuild); treat as unmapped.
                self.split_view_frame = tk.Frame(self.root, bg="#000000")
                was_mapped = False
            if was_mapped:
                self.split_view_frame.pack_forget()
            for w in self.split_view_frame.winfo_children():
                try: w.destroy()
                except Exception: pass
            self.rows = []

        if not splits:
            tk.Label(self.split_view_frame, text="No splits configured", bg="#000000", fg="white").pack(padx=8, pady=4)
            if is_init and was_mapped:
                self._repack_split_view()
            return

        font_size = 21
        index = 0
        for s_item in splits:
            row_bg = "#1a1a1a" if index % 2 == 0 else "#000000"
            if is_init or index == len(current) - 1:
                name = s_item[0]
                percent = f"{int(s_item[1]*100)}%"


                if is_init: 
                    self.rows.append(None) # placeholder to preserve indexing for later updates
                    self.rows[index] = tk.Frame(self.split_view_frame, bg=row_bg)
                    self.rows[index].pack(fill='x', padx=6, pady=0)
                
                current_time = current[index] - current[index-1] if 0 < index < len(current) else current[0] if current and len(current) > 0 else None

                if not has_live and not has_ghost:
                    tk.Label(self.rows[index], text=name, bg=row_bg, fg="white", anchor='w',
                            width=15, font=("Bahnschrift Condensed", font_size)).grid(row=0, column=0, sticky='w',padx=0,pady=0)
                    tk.Label(self.rows[index], text="", bg=row_bg, fg="#bdc3c7",
                            width=6, anchor='e', font=("Bahnschrift Condensed", font_size)).grid(row=0, column=1, sticky='e',pady=0)
                    tk.Label(self.rows[index], text="00.000", bg=row_bg, fg="#bdc3c7",
                            width=6, anchor='e', font=("Bahnschrift Condensed", font_size)).grid(row=0, column=2, sticky='e',pady=0)
                    tk.Label(self.rows[index], text=percent, bg=row_bg, fg="#bdc3c7",
                            width=6, anchor='e', font=("Bahnschrift Condensed", font_size)).grid(row=0, column=3, sticky='e',pady=0)
                elif not has_ghost:
                    tk.Label(self.rows[index], text=name, bg=row_bg, fg="white", anchor='w',
                            width=15, font=("Bahnschrift Condensed", font_size)).grid(row=0, column=0, sticky='w',padx=0,pady=0)
                    tk.Label(self.rows[index], text="=0.000", bg=row_bg, fg="#bdc3c7",
                            width=6, anchor='e', font=("Bahnschrift Condensed", font_size)).grid(row=0, column=1, sticky='e',pady=0)
                    tk.Label(self.rows[index], text=self._format_time_ms(current_time), bg=row_bg, fg="#bdc3c7",
                            width=6, anchor='e', font=("Bahnschrift Condensed", font_size)).grid(row=0, column=2, sticky='e',pady=0)
                    tk.Label(self.rows[index], text=percent, bg=row_bg, fg="#bdc3c7",
                            width=6, anchor='e', font=("Bahnschrift Condensed", font_size)).grid(row=0, column=3, sticky='e',pady=0)
                else:
                    ghost_time = ghost[index]
                    delta_display = ""
                    if current_time is None and index == 0:
                        current_time = current[0] if current and len(current) > 0 else None
                    try:
                        if current_time and ghost_time and current_time != 0 and ghost_time != 0:
                            delta_us = current_time - ghost_time
                            delta_display = self._format_delta_ms(delta_us)
                    except Exception:
                        delta_display = ""

                    tk.Label(self.rows[index], text=name, bg=row_bg, fg="white", anchor='w',
                            width=15, font=("Bahnschrift Condensed", font_size)).grid(row=0, column=0, sticky='w',padx=0,pady=0)
                    delta_fg = "#2ecc71" if delta_display and delta_display.startswith('-') else "#e74c3c"
                    tk.Label(self.rows[index], text=delta_display, bg=row_bg, fg=delta_fg,
                            width=6, font=("Bahnschrift Condensed", font_size)).grid(row=0, column=1, sticky='e',pady=0)
                    tk.Label(self.rows[index], text=self._format_time_ms(current_time), bg=row_bg, fg="#bdc3c7",
                            anchor='e', width=6, font=("Bahnschrift Condensed", font_size)).grid(row=0, column=2, sticky='e',pady=0)
                    tk.Label(self.rows[index], text=self._format_time_ms(ghost_time), bg=row_bg, fg="#bdc3c7",
                            anchor='e', width=6, font=("Bahnschrift Condensed", font_size)).grid(row=0, column=3, sticky='e',pady=0)
            index += 1

        if is_init and was_mapped:
            self._repack_split_view()
    # ──────────────────────────────────────────────────────────────────────
    #  Background color (race mode delta coloring)
    # ──────────────────────────────────────────────────────────────────────

    def update_background_color(self, mode: str, delta: float = None):
        """Update UI background color based on race mode and delta."""
        if mode == "Race vs Ghost" and delta is not None:
            if delta < 0:
                bg_color = "#007000"  # green — ahead
            elif delta > 0:
                bg_color = "#700000"  # red — behind
            else:
                bg_color = "#000050"  # blue — even
        else:
            bg_color = "#000000"

        if bg_color != self.current_bg_color:
            self.current_bg_color = bg_color
            if hasattr(self, 'main_display_frame') and self.main_display_frame:
                self.main_display_frame.configure(bg=bg_color)
            if hasattr(self, 'delta_label') and self.delta_label:
                self.delta_label.configure(bg=bg_color)
            if hasattr(self, 'button_section') and self.button_section:
                self.button_section.configure(bg=bg_color)

    # ──────────────────────────────────────────────────────────────────────
    #  Dialogs
    # ──────────────────────────────────────────────────────────────────────

    def prompt_save_race(self):
        """Prompt user to save race data."""
        if self.on_save_race:
            dialog = tk.Toplevel(self.root)
            dialog.title("Save Race Data")
            dialog.geometry("300x120")
            dialog.resizable(False, False)
            dialog.configure(bg="#000000")
            dialog.transient(self.root)
            dialog.grab_set()

            tk.Label(dialog, text="Race name:", bg="#000000", fg="white").pack(pady=(10, 5))
            filename_var = tk.StringVar()
            entry = tk.Entry(dialog, textvariable=filename_var, width=30)
            entry.pack(pady=5)
            entry.focus_set()

            button_frame = tk.Frame(dialog, bg="#000000")
            button_frame.pack(pady=10)

            def save_and_close():
                fn = filename_var.get().strip()
                if fn:
                    dialog.destroy()
                    self.on_save_race(fn)
                else:
                    messagebox.showerror("Error", "Please enter a filename")

            tk.Button(button_frame, text="Save", command=save_and_close,
                      bg="#27ae60", fg="white", width=8).pack(side="left", padx=5)
            tk.Button(button_frame, text="Cancel", command=dialog.destroy,
                      bg="#e74c3c", fg="white", width=8).pack(side="left", padx=5)
            entry.bind('<Return>', lambda _: save_and_close())
            self.root.after(30000, lambda: dialog.destroy())  # Auto-close after 30 seconds to prevent orphaned dialogs

    # ──────────────────────────────────────────────────────────────────────
    #  App lifecycle
    # ──────────────────────────────────────────────────────────────────────

    def close_app(self):
        """Close the application completely."""
        self.save_ui_config()
        if hasattr(self, 'on_close') and self.on_close:
            try:
                self.on_close()
            except Exception as e:
                print(f"Error in close callback: {e}")
        if self.root:
            try:
                self.root.quit()
                self.root.destroy()
            except (tk.TclError, RuntimeError) as e:
                print(f"UI cleanup warning: {e}")
        sys.exit(0)

    # ──────────────────────────────────────────────────────────────────────
    #  Scaling
    # ──────────────────────────────────────────────────────────────────────

    def adjust_scaling(self, delta: float):
        """Adjust UI scaling in real-time by recreating the UI."""
        if not self.root:
            return

        old_scaling = self.current_scaling
        self.current_scaling += delta
        self.current_scaling = max(0.5, min(2.0, self.current_scaling))
        scaling_ratio = self.current_scaling / old_scaling

        try:
            current_geometry = self.root.geometry()
            parts = current_geometry.replace('x', '+').replace('+', ' ').split()
            if len(parts) >= 4:
                width, height, x, y = int(parts[0]), int(parts[1]), parts[2], parts[3]
            else:
                width, height, x, y = 300, 100, "100", "100"

            new_width = int(width * scaling_ratio)
            new_height = int(height * scaling_ratio)

            was_race_expanded = self.race_panel_expanded
            was_debug_expanded = self.debug_expanded
            current_mode = self.get_current_mode() if self.mode_var else "Record Ghost"

            for widget in self.root.winfo_children():
                widget.destroy()
            # Null out references to destroyed widgets so update_split_view
            # doesn't try to call methods on stale Tk objects.
            self.split_view_frame = None
            self.rows = []
            self.gear_rpm_frame = None
            self.gear_rpm_visible = False
            self.velocity_frame = None
            self.velocity_visible = False
            self.velocity_height_shift = 0

            self.root.tk.call("tk", "scaling", self.current_scaling)

            base_width = int(300 * self.current_scaling)
            base_height = int(100 * self.current_scaling)
            self.root.geometry(f"{base_width}x{base_height}")

            self._recreate_ui_content()

            if self.mode_var:
                self.mode_var.set(current_mode)
                self.on_mode_changed()

            if was_race_expanded and not self.race_panel_expanded:
                self.toggle_race_panel()
            if was_debug_expanded and not self.debug_expanded:
                self.toggle_debug()

            self.root.geometry(f"+{x}+{y}")
            print(f"Scaling adjusted to: {self.current_scaling:.2f}, Window size: {new_width}x{new_height}")
        except tk.TclError as e:
            print(f"Error adjusting scaling: {e}")

    def increase_scaling(self):
        self.adjust_scaling(0.01)

    def decrease_scaling(self):
        self.adjust_scaling(-0.01)

    def reset_scaling(self):
        if not self.root:
            return
        self.current_scaling = 1.15
        try:
            self.root.tk.call("tk", "scaling", self.current_scaling)
            print(f"Scaling reset to: {self.current_scaling:.2f}")
        except tk.TclError:
            pass

    # ──────────────────────────────────────────────────────────────────────
    #  Drag support
    # ──────────────────────────────────────────────────────────────────────

    def start_drag(self, event):
        if self.is_pinned: # Don't allow dragging when pinned
            return
        self.start_x = event.x
        self.start_y = event.y

    def on_drag(self, event):
        if self.is_pinned: # Don't allow dragging when pinned
            return
        x = self.root.winfo_x() + (event.x - self.start_x)
        y = self.root.winfo_y() + (event.y - self.start_y)
        self.root.geometry(f"+{x}+{y}")

    # ──────────────────────────────────────────────────────────────────────
    #  UI creation  (matches old v4 layout exactly)
    # ──────────────────────────────────────────────────────────────────────

    def create_ui(self):
        """Create the main UI window."""
        # Force DPI awareness before any window is created so Tk receives
        # true physical pixel coordinates instead of virtualised ones.
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()   # fallback: system-DPI aware
            except Exception:
                pass

        self.root = tk.Tk()

        self.root.tk.call("tk", "scaling", self.current_scaling)

        # Keyboard shortcuts
        self.root.bind_all("<Control-plus>", lambda e: self.increase_scaling())
        self.root.bind_all("<Control-equal>", lambda e: self.increase_scaling())
        self.root.bind_all("<Control-minus>", lambda e: self.decrease_scaling())
        self.root.bind_all("<Control-0>", lambda e: self.reset_scaling())
        self.root.focus_set()

        self.root.title("ALU Timing Tool")

        # Window geometry from config (force base height; panels restored separately)
        geometry = self.config_manager.get_window_geometry_from_config(self.ui_config)
        base_h = int(80 * self.current_scaling)
        gparts = geometry.replace('x', '+').replace('+', ' ').split()
        self.root.geometry(f"{gparts[0]}x{base_h}+{gparts[2]}+{gparts[3]}")
        self.root.overrideredirect(True)

        # Hidden taskbar window
        self.root.configure(bg="#000000")

        # Pin state
        self.is_pinned = self.ui_config.get("is_pinned", True)
        self.root.wm_attributes("-topmost", True)

        # ── Main container (fixed height — does not grow with panels) ──
        main_container = tk.Frame(self.root, bg="#000000", height=base_h)
        main_container.pack(side="top", fill="x")
        main_container.pack_propagate(False)
        self.main_container = main_container

        # Main UI frame (delta display + button bar)
        main_ui_frame = tk.Frame(main_container, bg="#000000")
        main_ui_frame.pack(side="left", fill="both", expand=True)

        main_ui_frame.bind("<Button-1>", self.start_drag)
        main_ui_frame.bind("<B1-Motion>", self.on_drag)

        # Delta display area
        self.main_display_frame = tk.Frame(main_ui_frame, bg="#000000")
        self.main_display_frame.pack(fill="both", expand=True)
        self.main_display_frame.bind("<Button-1>", self.start_drag)
        self.main_display_frame.bind("<B1-Motion>", self.on_drag)

        self.delta_label = tk.Label(
            self.main_display_frame, text=self.delta_time,
            font=("Helvetica", self.DELTA_FONT_BASE, "bold"),
            fg="#ecf0f1", bg="#000000",
        )
        self.delta_label.pack(side="top", fill="x")
        self.delta_label.bind("<Button-1>", self.start_drag)
        self.delta_label.bind("<B1-Motion>", self.on_drag)

        # Right-click anywhere on main area toggles race panel
        main_container.bind('<Button-3>', self.toggle_race_panel)
        main_ui_frame.bind('<Button-3>', self.toggle_race_panel)
        self.main_display_frame.bind('<Button-3>', self.toggle_race_panel)
        self.delta_label.bind('<Button-3>', self.toggle_race_panel)

        self.button_section = None

        # ── Race panel (hidden, packed below when toggled) ──
        self.race_panel = tk.Frame(self.root, bg="#000000", height=150)
        self._create_race_panel_content()

        # ── Gear / RPM bar (hidden until a race starts) ──
        self._create_gear_rpm_bar()

        # ── Steering bar (hidden until a race starts) ──
        self._create_steering_display()

        # ── Velocity delta display (hidden until a race starts) ──
        self._create_vdelta_display()

        # ── Velocity indicator (hidden until a race starts) ──
        self._create_velocity_display()

        # Always open the race panel on startup.
        # The widget is not yet packed at this point, so reset the tracking
        # flag to False (= hidden) before calling toggle, which will flip it
        # to True and pack the panel.
        self.race_panel_expanded = False
        self.toggle_race_panel()

        # Start UI update loop
        self.update_ui()

        self.root.lift()
        self.root.focus_force()
        self.root.mainloop()

    def _recreate_ui_content(self):
        """Recreate the UI content after scaling change (mirrors create_ui layout)."""
        self.race_panel_expanded = False
        self.debug_expanded = False

        base_width = int(300 * self.current_scaling)
        base_height = int(80 * self.current_scaling)
        self.root.geometry(f"{base_width}x{base_height}")
        self.root.overrideredirect(True)

        self.root.configure(bg="#000000")
        self.root.wm_attributes("-topmost", True)

        # Main container (fixed height — does not grow with panels)
        main_container = tk.Frame(self.root, bg="#000000", height=base_height)
        main_container.pack(side="top", fill="x")
        main_container.pack_propagate(False)
        self.main_container = main_container

        main_ui_frame = tk.Frame(main_container, bg="#000000")
        main_ui_frame.pack(side="left", fill="both", expand=True)
        main_ui_frame.bind("<Button-1>", self.start_drag)
        main_ui_frame.bind("<B1-Motion>", self.on_drag)

        self.main_display_frame = tk.Frame(main_ui_frame, bg="#000000")
        self.main_display_frame.pack(fill="both", expand=True)
        self.main_display_frame.bind("<Button-1>", self.start_drag)
        self.main_display_frame.bind("<B1-Motion>", self.on_drag)

        self.delta_label = tk.Label(
            self.main_display_frame, text=self.delta_time,
            font=("Helvetica", self.DELTA_FONT_BASE, "bold"),
            fg="#ecf0f1", bg="#000000",
        )
        self.delta_label.pack(side="top", fill="x")
        self.delta_label.bind("<Button-1>", self.start_drag)
        self.delta_label.bind("<B1-Motion>", self.on_drag)
        # Right-click anywhere on main area toggles race panel
        main_container.bind('<Button-3>', self.toggle_race_panel)
        main_ui_frame.bind('<Button-3>', self.toggle_race_panel)
        self.main_display_frame.bind('<Button-3>', self.toggle_race_panel)
        self.delta_label.bind('<Button-3>', self.toggle_race_panel)

        self.button_section = None

        self.race_panel = tk.Frame(self.root, bg="#000000", height=150)
        self._create_race_panel_content()

        # Gear / RPM bar
        self.gear_rpm_frame = None
        self.gear_rpm_visible = False
        self._create_gear_rpm_bar()

        # Steering bar
        self.steering_frame = None
        self.steering_visible = False
        self._create_steering_display()

        # Velocity delta display
        self.vdelta_frame = None
        self.vdelta_ratio_label = None
        self.vdelta_visible = False
        self.vdelta_height_shift = 0
        self._create_vdelta_display()

        # Velocity indicator
        self.velocity_frame = None
        self.velocity_visible = False
        self.velocity_height_shift = 0
        self._create_velocity_display()

        # Rebind shortcuts
        self.root.bind_all("<Control-plus>", lambda e: self.increase_scaling())
        self.root.bind_all("<Control-equal>", lambda e: self.increase_scaling())
        self.root.bind_all("<Control-minus>", lambda e: self.decrease_scaling())
        self.root.bind_all("<Control-0>", lambda e: self.reset_scaling())
        self.root.focus_set()

        # Always re-open the race panel after a scaling rebuild.
        # race_panel_expanded was reset to False at the top of this method
        # (widget not packed), so toggle_race_panel() will flip it to True.
        self.toggle_race_panel()

    # ──────────────────────────────────────────────────────────────────────
    #  Race panel content (2-column, matches old UI)
    # ──────────────────────────────────────────────────────────────────────

    def _create_race_panel_content(self):
        """Create the race panel content with 2-column layout."""
        if not self.race_panel:
            return

        # Scaled padding — multiplied by current_scaling so they grow/shrink
        # proportionally when adjust_scaling rebuilds the panel.
        px = int(14 * self.current_scaling)
        py = int(10 * self.current_scaling)
        py_sm = int(6 * self.current_scaling)

        # Apply a ttk Style so the Combobox matches the UI theme.
        # 'clam' theme is required on Windows — the default 'vista'/'winnative'
        # theme ignores fieldbackground, arrowcolor, and font overrides entirely.
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("Race.TCombobox",
                        font=("Helvetica", 15, "bold"),
                        foreground="#ecf0f1",
                        background="#34495e",
                        fieldbackground="#34495e",
                        selectbackground="#34495e",
                        selectforeground="#ecf0f1",
                        arrowcolor="#ecf0f1",
                        borderwidth=0,
                        relief="flat",
                        padding=(int(4 * self.current_scaling), int(4 * self.current_scaling)))
        style.map("Race.TCombobox",
                  fieldbackground=[("readonly", "#34495e"), ("disabled", "#2c3e50")],
                  foreground=[("readonly", "#ecf0f1")],
                  background=[("active", "#4a6785"), ("!active", "#34495e")])
        # Dropdown popup listbox — styled via tk option database (not ttk)
        self.root.option_add('*TCombobox*Listbox.font', ("Helvetica", 15, "bold"))
        self.root.option_add('*TCombobox*Listbox.background', "#34495e")
        self.root.option_add('*TCombobox*Listbox.foreground', "#ecf0f1")
        self.root.option_add('*TCombobox*Listbox.selectBackground', "#202d3a")
        self.root.option_add('*TCombobox*Listbox.selectForeground', "#ecf0f1")
        self.root.option_add('*TCombobox*Listbox.relief', "flat")

        # ── Header row: indicator label + button cluster ──
        header_frame = tk.Frame(self.race_panel, bg="#000000")
        header_frame.pack(fill="x", padx=px, pady=(py, 0))
        header_frame.bind('<Button-1>', self.start_drag)
        header_frame.bind('<B1-Motion>', self.on_drag)
        header_frame.bind('<Button-3>', self.toggle_race_panel)

        self.race_control_indicator = tk.Label(
            header_frame, text="ALU Timer v5.0",
            font=("Helvetica", 18, "bold"), fg="white", bg="#000000", anchor='w'
        )
        self.race_control_indicator.pack(side="left")
        self.race_control_indicator.bind('<Button-1>', self.start_drag)
        self.race_control_indicator.bind('<B1-Motion>', self.on_drag)
        self.race_control_indicator.bind('<Button-3>', self.toggle_race_panel)

        header_btns = tk.Frame(header_frame, bg="#000000")
        header_btns.pack(side="right")

        self.close_button = tk.Button(
            header_btns, text="✕", command=self.close_app,
            bg="#e74c3c", fg="white", font=("Helvetica", 11, "bold"),
            relief="flat", width=3, height=0, pady=0,
        )
        self.close_button.pack(side="right", padx=2, pady=2)

        pin_text = "●" if self.is_pinned else "○"
        pin_bg = "#95a5a6" if self.is_pinned else "#4ecdc4"
        self.pin_button = tk.Button(
            header_btns, text=pin_text, command=self.toggle_pin,
            bg=pin_bg, fg="white", font=("Helvetica", 11, "bold"),
            relief="flat", width=3, height=0, pady=0,
        )
        self.pin_button.pack(side="right", padx=2, pady=2)

        self.debug_button = tk.Button(
            header_btns, text="🐛", command=self.toggle_debug,
            bg="#3498db", fg="white", font=("Helvetica", 11, "bold"),
            relief="flat", width=3, height=0, pady=0,
        )
        self.debug_button.pack(side="right", padx=2, pady=2)

        # Main 2-column container — grid with uniform weights keeps both
        # columns exactly equal width regardless of button text length.
        main_container = tk.Frame(self.race_panel, bg="#000000")
        main_container.pack(fill="both", expand=True, padx=px, pady=py)
        main_container.columnconfigure(0, weight=1, uniform="col")
        main_container.columnconfigure(1, weight=1, uniform="col")
        main_container.rowconfigure(0, weight=1)

        # ── Left column: Ghost info + Mode selector + Debug button ──
        left_column = tk.Frame(main_container, bg="#000000")
        left_column.grid(row=0, column=0, sticky="nsew", padx=(0, px // 2))

        # Ghost section
        ghost_frame = tk.Frame(left_column, bg="#000000")
        ghost_frame.pack(fill="x", pady=(0, py_sm))

        self.ghost_filename_label = tk.Label(
            ghost_frame, text="By Orange & Bholla64",
            font=("Helvetica", 12,'bold'), fg="#b4c6c8", bg="#000000",
            wraplength=200, justify="left"
        )
        self.ghost_filename_label.pack(anchor="w", pady=(0, 0))

        # Mode section
        mode_frame = tk.Frame(left_column, bg="#000000")
        mode_frame.pack(fill="x", pady=(0, py))

        self.mode_var = tk.StringVar(value="Record Ghost")
        self.mode_combobox = ttk.Combobox(
            mode_frame, textvariable=self.mode_var,
            values=["Record Ghost", "Race vs Ghost"],
            state="readonly", width=14,
            style="Race.TCombobox",
            font=("Helvetica", 15, "bold"),
        )
        self.mode_combobox.pack(anchor="w", fill="x", pady=(round(0.7353 * self.current_scaling), 0))
        self.mode_combobox.bind('<<ComboboxSelected>>', self.on_mode_changed)

        # Velocity mode dropdown
        self.vel_mode_var = tk.StringVar(value=self.vel_mode)
        vel_mode_combobox = ttk.Combobox(
            left_column, textvariable=self.vel_mode_var,
            values=["Speed Off", "Real KM/H", "Fake KM/H", "Real MPH", "Fake MPH"],
            state="readonly", width=14,
            style="Race.TCombobox",
            font=("Helvetica", 15, "bold"),
        )
        vel_mode_combobox.pack(anchor="w", fill="x", pady=(round(0.7353 * self.current_scaling), 0))
        vel_mode_combobox.bind('<<ComboboxSelected>>', self.on_vel_mode_changed)

        # Checkboxes row: Splits + Gear/RPM side by side
        checks_frame = tk.Frame(left_column, bg="#000000")
        checks_frame.pack(fill="x", pady=(round(2 * self.current_scaling), 0))

        self.split_view_var = tk.BooleanVar(value=self.split_view_enabled)
        self.splits_checkbox = tk.Checkbutton(
            checks_frame, text="Splits", variable=self.split_view_var,
            command=self._on_splits_checkbox_changed,
            bg="#000000", fg="white", selectcolor="#1a1a1a",
            activebackground="#000000", activeforeground="#ecf0f1",
            font=("Helvetica", 12, "bold"),
            relief="flat", state="disabled",
        )
        self.splits_checkbox.pack(side="left", padx=(0, 8))

        self.gear_rpm_var = tk.BooleanVar(value=self.gear_rpm_enabled)
        self.gear_rpm_checkbox = tk.Checkbutton(
            checks_frame, text="Gear/RPM", variable=self.gear_rpm_var,
            command=self.on_gear_rpm_changed,
            bg="#000000", fg="white", selectcolor="#1a1a1a",
            activebackground="#000000", activeforeground="#ecf0f1",
            font=("Helvetica", 12, "bold"),
            relief="flat",
        )
        self.gear_rpm_checkbox.pack(side="left")

        # ── Right column: slot button + Save ──
        right_column = tk.Frame(main_container, bg="#000000")
        right_column.grid(row=0, column=1, sticky="nsew", padx=(px // 2, 0),pady=(round(2*self.current_scaling),0))

        # Slot 1 — Configure Splits (record mode, packed by default)
        # Load Race Ghost is created here but NOT packed — swapped in on_mode_changed
        self.configure_splits_button = tk.Button(
            right_column, text="Split Config",
            command=self.open_configure_splits_dialog,
            bg="#8e44ad", fg="white", font=("Helvetica", 18, "bold"),
            relief="flat",
        )
        self.configure_splits_button.pack(fill="x", pady=(0, py))

        self.load_ghost_button = tk.Button(
            right_column, text="Load Ghost", command=self.load_ghost_file,
            bg="#3498db", fg="white", font=("Helvetica", 18, "bold"),
            relief="flat",
        )
        # NOT packed here — only shown when mode == "Race vs Ghost"

        # Slot 2 — Save Ghost (always present, enabled when data exists)
        self.save_ghost_button = tk.Button(
            right_column, text="Save Ghost", command=self.save_ghost_file,
            bg="#7f8c8d", fg="white", font=("Helvetica", 18, "bold"),
            relief="flat", state="disabled",
        )
        self.save_ghost_button.pack(fill="x", pady=(0, 0))

        # Steering + V delta toggles (side by side in one row)
        overlays_row = tk.Frame(right_column, bg="#000000")
        overlays_row.pack(anchor="w", pady=(round(2 * self.current_scaling), 0))

        self.steering_var = tk.BooleanVar(value=self.steering_enabled)
        self.steering_checkbox = tk.Checkbutton(
            overlays_row, text="Steering", variable=self.steering_var,
            command=self.on_steering_changed,
            bg="#000000", fg="white", selectcolor="#1a1a1a",
            activebackground="#000000", activeforeground="#ecf0f1",
            font=("Helvetica", 12, "bold"),
            relief="flat",
        )
        self.steering_checkbox.pack(side="left", padx=(0, 6))

        self.vdelta_var = tk.BooleanVar(value=self.vdelta_enabled)
        self.vdelta_checkbox = tk.Checkbutton(
            overlays_row, text="V delta", variable=self.vdelta_var,
            command=self.on_vdelta_changed,
            bg="#000000", fg="white", selectcolor="#1a1a1a",
            activebackground="#000000", activeforeground="#ecf0f1",
            font=("Helvetica", 12, "bold"),
            relief="flat",
            state="disabled",  # disabled in Record Ghost mode; enabled on mode switch
        )
        self.vdelta_checkbox.pack(side="left")

        # Enable splits checkbox now if splits are already configured.
        self.update_splits_checkbox_state()

        # ── Debug panel (hidden, packed below when expanded) ──
        self.debug_frame = tk.Frame(self.race_panel, bg="#000000")
        self._create_debug_panel_content()

    def _create_debug_panel_content(self):
        """Create the debug panel content with 2-column layout."""
        if not self.debug_frame:
            return

        px = int(8 * self.current_scaling)
        py = int(5 * self.current_scaling)
        py_sm = int(3 * self.current_scaling)

        main_container = tk.Frame(self.debug_frame, bg="#000000")
        main_container.pack(fill="both", expand=True, padx=px, pady=py)

        # Title row
        title_row = tk.Frame(main_container, bg="#000000")
        title_row.pack(fill="x", pady=(0, py_sm))

        tk.Label(title_row, text="Debug Information",
                 font=("Helvetica", 12, "bold"), fg="#ecf0f1", bg="#000000").pack(side="left", anchor="w")

        self.debug_close_button = tk.Button(
            title_row, text="✕", font=("Helvetica", 11, "bold"),
            bg="#e74c3c", fg="white", width=3, height=0, pady=0,
            command=self.toggle_debug, relief="flat", bd=1,
        )
        self.debug_close_button.pack(side="right")

        # 2-column info
        info_container = tk.Frame(main_container, bg="#000000")
        info_container.pack(fill="both", expand=True)

        # Left: Performance metrics
        left_column = tk.Frame(info_container, bg="#000000")
        left_column.pack(side="left", fill="both", expand=True, padx=(0, px))

        tk.Label(left_column, text="Performance Metrics",
                 font=("Helvetica", 11, "bold"), fg="#bdc3c7", bg="#000000").pack(anchor="w", pady=(0, py_sm))

        self.elapsed_label = tk.Label(left_column, text=f"Loop: {self.elapsed_ms:.1f}ms",
                                      font=("Helvetica", 10), fg="#ecf0f1", bg="#000000")
        self.elapsed_label.pack(anchor="w")

        self.avg_loop_label = tk.Label(left_column, text="Avg Loop: --",
                                       font=("Helvetica", 10), fg="#ecf0f1", bg="#000000")
        self.avg_loop_label.pack(anchor="w")

        # Right: Game state
        right_column = tk.Frame(info_container, bg="#000000")
        right_column.pack(side="right", fill="both", expand=True)

        tk.Label(right_column, text="Game State",
                 font=("Helvetica", 11, "bold"), fg="#bdc3c7", bg="#000000").pack(anchor="w", pady=(0, py_sm))

        self.time_label = tk.Label(right_column, text=f"Timer: {self.current_timer_display}",
                                    font=("Helvetica", 10), fg="#ecf0f1", bg="#000000")
        self.time_label.pack(anchor="w")

        self.percentage_label = tk.Label(right_column, text="Distance: --",
                                          font=("Helvetica", 10, "bold"), fg="#95a5a6", bg="#000000")
        self.percentage_label.pack(anchor="w")

        self.debug_timer_label = tk.Label(right_column, text="Timer: 00:00.000",
                                           font=("Courier", 10), fg="#95a5a6", bg="#000000")
        self.debug_timer_label.pack(anchor="w")

    # ──────────────────────────────────────────────────────────────────────
    #  UI update loop
    # ──────────────────────────────────────────────────────────────────────

    def update_ui(self):
        """Update UI elements with current data."""
        if self.root is None:
            return

        try:
            current_mode = self.get_current_mode()
            if current_mode == "Race vs Ghost":
                if self.delta_time and self.delta_time != "−−.−−−":
                    self.delta_label.config(text=self.delta_time, font=("Franklin Gothic Heavy", 90))
                elif self.current_timer_display == "00:00.000":
                    self.delta_label.config(text="Race Mode", font=("Helvetica", 50))
                else:
                    self.delta_label.config(text=self.current_timer_display, font=("Helvetica", 65))
            else:
                # Record mode: show live timer or "Rec..."
                if self.current_timer_display and self.current_timer_display != "00:00.000":
                    self.delta_label.config(text=self.current_timer_display, font=("Helvetica", 65))
                else:
                    self.delta_label.config(text="Record Mode", font=("Helvetica", 45))

            # Debug info (only when expanded)
            if self.debug_expanded:
                self.time_label.config(text=f"Timer: {self.current_timer_display}")
                self.elapsed_label.config(text=f"Loop: {self.elapsed_ms:.1f}ms")
                self.avg_loop_label.config(text=f"Avg Loop: {self.avg_loop_time:.1f}ms")

                if self.percentage and self.percentage != "0%":
                    self.percentage_label.config(text=f"Distance: {self.percentage}", fg="#2ecc71")
                else:
                    self.percentage_label.config(text="Distance: --", fg="#95a5a6")

                self.debug_timer_label.config(text=f"Timer: {self.current_timer_display}")

            # Consume pending split-view reset (set by timer thread; must be
            # processed here on the Tk main thread to safely call root.after).
            if self._pending_split_reset:
                self._pending_split_reset = False
                self.root.after(150, self._reset_split_view_if_hidden)

            self.root.after(11, self.update_ui)
        except tk.TclError:
            pass

    # ──────────────────────────────────────────────────────────────────────
    #  Public API  (called by timer_v5_pymem.py)
    # ──────────────────────────────────────────────────────────────────────

    def start_ui_thread(self):
        """Start the UI in a separate thread."""
        ui_thread = threading.Thread(target=self.create_ui, daemon=True)
        ui_thread.start()
        return ui_thread

    def set_callbacks(self, on_mode_change=None, on_load_ghost=None, on_save_ghost=None,
                      on_save_race=None, on_close=None, on_load_split=None, on_configure_splits=None):
        """Set callback functions for race functionality."""
        self.on_mode_change = on_mode_change
        self.on_load_ghost = on_load_ghost
        self.on_save_ghost = on_save_ghost
        self.on_save_race = on_save_race
        self.on_close = on_close
        self.on_load_split = on_load_split
        self.on_configure_splits = on_configure_splits

    def update_timer(self, timer_display: str):
        self.current_timer_display = timer_display

    def update_delta(self, delta: str):
        self.delta_time = delta

    def update_percentage(self, percentage: str):
        self.percentage = percentage
    
    def update_splits(self, timer_us: int, progress: float):
        self.current_timer_us = timer_us
        self.progress = progress
        self.update_split_view()

    def update_loop_time(self, elapsed_ms: float, avg_loop_time: float):
        self.elapsed_ms = elapsed_ms
        self.avg_loop_time = avg_loop_time

    def get_current_mode(self) -> str:
        if self.mode_var:
            return self.mode_var.get()
        return "Record Ghost"

    def show_message(self, title: str, message: str, is_error: bool = False):
        if is_error:
            messagebox.showerror(title, message)
        else:
            messagebox.showinfo(title, message)

    def close(self):
        self.close_app()
