"""
User Interface Module

This module handles the GUI for the ALU Timing Tool.
Visually based on the original v4 UI design, with v5 features (splits, CE integration).
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import ctypes
import shutil
import threading
import sys
import os
from src.utils.ui_config import UIConfigManager


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
        self.inference_label = None
        self.avg_inference_label = None
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
        self.mode_var = None
        self.mode_combobox = None
        self.load_ghost_button = None
        self.save_ghost_button = None

        # Split view elements
        self.split_view_frame = None
        self.split_view_visible = False
        self.toggle_split_view_button = None
        self.configure_splits_button = None
        self.rows = []

        # Gear / RPM bar elements
        self.main_container = None
        self.gear_rpm_frame = None
        self.gear_label = None
        self.rpm_canvas = None
        self.gear_rpm_visible = False
        self.current_gear = 0
        self.current_rpm = 1250

        # Velocity indicator elements
        self.velocity_frame = None
        self.velocity_label = None
        self.velocity_visible = False
        self.current_velocity = 0.0
        self.velocity_height_shift = 0

        # Data to display
        self.current_timer_display = "00:00.000"
        self.elapsed_ms = 0
        self.avg_loop_time = 0
        self.percentage = "0%"
        self.avg_inference_time = 0
        self.current_inference_time = 0
        self.delta_time = "Rec..."  # Default delta text (CE v5: shows Rec... in record mode)
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

        # Load panel states from config
        self.race_panel_expanded = self.ui_config.get("panels", {}).get("race_panel_expanded", False)
        self.debug_expanded = self.ui_config.get("panels", {}).get("debug_panel_expanded", False)
        self.is_pinned = self.ui_config.get("is_pinned", True)

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
            self.race_button.config(text="▴", bg="#e67e22")
            # If split view is visible, ensure it stays below the race panel.
            if self.split_view_visible and self.split_view_frame:
                self.split_view_frame.pack_forget()
                self._repack_split_view()
        else:
            self.race_panel.pack_forget()
            self.race_button.config(text="▾", bg="#e67e22")
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

        if self.toggle_split_view_button:
            if self.race_data_manager and getattr(self.race_data_manager, 'splits', None):
                self.toggle_split_view_button.config(state="normal", bg="#44ad4e")
            else:
                self.toggle_split_view_button.config(state="disabled", bg="#7f8c8d")

        if self.on_mode_change:
            self.on_mode_change(mode)

    def load_ghost_file(self):
        """Open file dialog to load a ghost file."""
        if self.on_load_ghost:
            filetypes = [("JSON files", "*.json"), ("All files", "*.*")]
            runs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "runs")
            os.makedirs(runs_dir, exist_ok=True)
            filename = filedialog.askopenfilename(
                title="Load Race Ghost",
                filetypes=filetypes,
                initialdir=runs_dir,
            )
            if filename:
                self.on_load_ghost(filename)

    def load_split_file(self):
        """Open file dialog to load a split-type ghost file."""
        if hasattr(self, 'on_load_split') and self.on_load_split:
            filetypes = [("JSON files", "*.json"), ("All files", "*.*")]
            runs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "runs")
            os.makedirs(runs_dir, exist_ok=True)
            filename = filedialog.askopenfilename(
                title="Load Split Race Ghost",
                filetypes=filetypes,
                initialdir=runs_dir,
            )
            if filename:
                self.on_load_split(filename)

    def save_ghost_file(self):
        """Open file dialog to save current race data as ghost file."""
        if self.on_save_ghost:
            filetypes = [("JSON files", "*.json"), ("All files", "*.*")]
            runs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "runs")
            os.makedirs(runs_dir, exist_ok=True)
            filename = filedialog.asksaveasfilename(
                title="Save Current Ghost",
                filetypes=filetypes,
                defaultextension=".json",
                initialdir=runs_dir,
            )
            if filename:
                self.on_save_ghost(filename)

    def update_ghost_filename(self, filename: str):
        """Update the displayed ghost filename."""
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

            if self.toggle_split_view_button:
                self.toggle_split_view_button.config(state="normal", bg="#44ad4e")

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

    def _get_split_view_height(self):
        """Calculate split view height if visible."""
        if not self.split_view_visible or not self.race_data_manager:
            return 0
        try:
            splits = self.race_data_manager.splits
            if splits:
                return max(60, int(len(splits) * 33 * self.current_scaling))
        except Exception:
            pass
        return 0

    def _adjust_height_for_split_view(self):
        """Adjust window height for split view visibility change."""
        if not self.root:
            return
        split_h = self._get_split_view_height()
        current_geometry = self.root.geometry()
        parts = current_geometry.replace('x', '+').replace('+', ' ').split()
        width, height, x, y = parts[0], int(parts[1]), parts[2], parts[3]
        if self.split_view_visible:
            new_height = height + split_h
        else:
            new_height = height - split_h
        self.root.geometry(f"{width}x{max(60, new_height)}+{x}+{y}")

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
            DOWNSHIFT_ENGAGE = 6400  # RPM in the lower gear that triggers autoshift

            g = self.current_gear
            if g >= 2:
                r_cur  = GEAR_RATIOS.get(g,  GEAR_RATIOS[5])
                r_prev = GEAR_RATIOS.get(g - 1, GEAR_RATIOS[1])
                # RPM_in_lower = RPM_current * (r_cur / r_prev)
                # Red when RPM_in_lower < DOWNSHIFT_ENGAGE
                # → RPM_current < DOWNSHIFT_ENGAGE * (r_prev / r_cur)
                downshift_threshold = DOWNSHIFT_ENGAGE * (r_prev / r_cur)
            else:
                downshift_threshold = RPM_MIN  # gear 0/1 — never red

            rpm = self.current_rpm
            if   rpm >= 8000:
                bar_color = "#3498db"   # blue  — near/at limiter
            elif rpm >= 7000:
                bar_color = "#f1c40f"   # yellow — high RPM
            elif rpm >= downshift_threshold:
                bar_color = "#2ecc71"   # green  — normal
            else:
                bar_color = "#e74c3c"   # red    — should downshift

            fill_ratio = max(0.0, min(1.0, (rpm - RPM_MIN) / (RPM_MAX - RPM_MIN)))
            gear_text = str(g) if g > 0 else "N"
            self.gear_label.config(text=gear_text)

            w = self.rpm_canvas.winfo_width()
            h = self.rpm_canvas.winfo_height()
            if w <= 1 or h <= 1:
                return

            self.rpm_canvas.delete("all")
            # Dark background track
            self.rpm_canvas.create_rectangle(0, 0, w, h, fill="#222222", outline="")
            # Filled portion
            fill_w = int(w * fill_ratio)
            if fill_w > 0:
                self.rpm_canvas.create_rectangle(0, 0, fill_w, h, fill=bar_color, outline="")
        except tk.TclError:
            pass

    def _create_velocity_display(self):
        """Create the velocity indicator widget (hidden by default)."""
        self.velocity_frame = tk.Frame(self.root, bg="#000000")
        # NOT packed — only shown when update_velocity is called with racing=True
        self.velocity_label = tk.Label(
            self.velocity_frame, text="0.0",
            font=("Franklin Gothic Heavy", 105),
            fg="#ecf0f1", bg="#000000", anchor="e",
        )
        self.velocity_label.pack(fill="x", padx=(4, 4), pady=0)

    def update_velocity(self, speed_kmh: float, racing: bool):
        """Show/update the velocity indicator during a race; hide it otherwise."""
        self.current_velocity = speed_kmh

        if not self.velocity_frame:
            return

        was_visible = self.velocity_visible
        self.velocity_visible = racing

        if racing:
            try:
                self.velocity_label.config(text=f"{speed_kmh:.1f}")
            except tk.TclError:
                pass

        if racing and not was_visible:
            # Pack at the very top of the window, before main_container
            if self.main_container:
                self.velocity_frame.pack(side="top", fill="x", before=self.main_container)
            else:
                self.velocity_frame.pack(side="top", fill="x")
            self.root.update_idletasks()
            vh = self.velocity_frame.winfo_reqheight()
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
            self.velocity_frame.pack_forget()
            # Move window down to restore original position
            try:
                geo = self.root.geometry()
                parts = geo.replace('x', '+').replace('+', ' ').split()
                if len(parts) >= 4:
                    x, y = int(parts[2]), int(parts[3])
                    self.root.geometry(f"+{x}+{y + vh}")
            except (tk.TclError, ValueError):
                pass
            self.velocity_height_shift = 0
            self._auto_resize()

    def update_gear_rpm(self, gear: int, rpm: int, racing: bool):
        """Show/update the gear+RPM bar during a race; hide it otherwise."""
        self.current_gear = gear
        self.current_rpm = rpm

        if not self.gear_rpm_frame:
            return

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
        """Re-attach split_view_frame below the race panel (or at top if race panel is hidden)."""
        if self.race_panel and self.race_panel.winfo_ismapped():
            self.split_view_frame.pack(side="top", fill="x", after=self.race_panel, padx=0, pady=(0, 0))
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
        is_init = current is None or len(current) == 0 or len(current) == len(splits)

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
        #try:
        #    for v in (self.race_data_manager.current_race_data.values()
        #              if hasattr(self.race_data_manager, 'current_race_data') else []):
        #        if v != "0000000":
        #            has_live = True
        #            break
        #except Exception:
        #    has_live = False

        #font_size = max(10, int(12 * self.current_scaling))
        font_size = 21
        index = 0
        for s_item in splits:
            if is_init or index == len(current) - 1:
                name = s_item[0]
                percent = f"{int(s_item[1]*100)}%"


                if is_init: 
                    self.rows.append(None) # placeholder to preserve indexing for later updates
                    self.rows[index] = tk.Frame(self.split_view_frame, bg="#000000")
                    self.rows[index].pack(fill='x', padx=6, pady=0)
                
                current_time = current[index] - current[index-1] if 0 < index < len(current) else current[0] if current and len(current) > 0 else None

                if not has_live and not has_ghost:
                    tk.Label(self.rows[index], text=name, bg="#000000", fg="white", anchor='w',
                            width=15, font=("Bahnschrift Condensed", font_size)).grid(row=0, column=0, sticky='w',padx=0,pady=0)
                    tk.Label(self.rows[index], text="", bg="#000000", fg="#bdc3c7",
                            width=6, anchor='e', font=("Bahnschrift Condensed", font_size)).grid(row=0, column=1, sticky='e',pady=0)
                    tk.Label(self.rows[index], text="00.000", bg="#000000", fg="#bdc3c7",
                            width=6, anchor='e', font=("Bahnschrift Condensed", font_size)).grid(row=0, column=2, sticky='e',pady=0)
                    tk.Label(self.rows[index], text=percent, bg="#000000", fg="#bdc3c7",
                            width=6, anchor='e', font=("Bahnschrift Condensed", font_size)).grid(row=0, column=3, sticky='e',pady=0)
                elif not has_ghost:
                    tk.Label(self.rows[index], text=name, bg="#000000", fg="white", anchor='w',
                            width=15, font=("Bahnschrift Condensed", font_size)).grid(row=0, column=0, sticky='w',padx=0,pady=0)
                    tk.Label(self.rows[index], text="=0.000", bg="#000000", fg="#bdc3c7",
                            width=6, anchor='e', font=("Bahnschrift Condensed", font_size)).grid(row=0, column=1, sticky='e',pady=0)
                    tk.Label(self.rows[index], text=self._format_time_ms(current_time), bg="#000000", fg="#bdc3c7",
                            width=6, anchor='e', font=("Bahnschrift Condensed", font_size)).grid(row=0, column=2, sticky='e',pady=0)
                    tk.Label(self.rows[index], text=percent, bg="#000000", fg="#bdc3c7",
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

                    tk.Label(self.rows[index], text=name, bg="#000000", fg="white", anchor='w',
                            width=15, font=("Bahnschrift Condensed", font_size)).grid(row=0, column=0, sticky='w',padx=0,pady=0)
                    delta_fg = "#2ecc71" if delta_display and delta_display.startswith('-') else "#e74c3c"
                    tk.Label(self.rows[index], text=delta_display, bg="#000000", fg=delta_fg,
                            width=6, font=("Bahnschrift Condensed", font_size)).grid(row=0, column=1, sticky='e',pady=0)
                    tk.Label(self.rows[index], text=self._format_time_ms(current_time), bg="#000000", fg="#bdc3c7",
                            anchor='e', width=6, font=("Bahnschrift Condensed", font_size)).grid(row=0, column=2, sticky='e',pady=0)
                    tk.Label(self.rows[index], text=self._format_time_ms(ghost_time), bg="#000000", fg="#bdc3c7",
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
        base_h = int(100 * self.current_scaling)
        gparts = geometry.replace('x', '+').replace('+', ' ').split()
        self.root.geometry(f"{gparts[0]}x{base_h}+{gparts[2]}+{gparts[3]}")
        self.root.overrideredirect(True)

        # Hidden taskbar window
        self.taskbar_window = tk.Toplevel(self.root)
        self.taskbar_window.title("ALU Timing Tool")
        self.taskbar_window.geometry("1x1+0+0")
        self.taskbar_window.withdraw()
        self.taskbar_window.iconify()

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
        self.delta_label.pack(expand=True, fill="both")
        self.delta_label.bind("<Button-1>", self.start_drag)
        self.delta_label.bind("<B1-Motion>", self.on_drag)

        # Right-click to toggle race panel
        self.main_display_frame.bind('<Button-3>', self.toggle_race_panel)
        self.delta_label.bind('<Button-3>', self.toggle_race_panel)

        # ── Bottom button section (30 px bar) ──
        btn_px = int(14 * self.current_scaling)
        button_section = tk.Frame(main_ui_frame, bg="#000000", height=30)
        button_section.pack(fill="x", side="bottom", padx=(btn_px, btn_px), pady=0)
        button_section.pack_propagate(False)
        button_section.grid_propagate(False)
        # 2-column grid mirroring the race panel's uniform split so the
        # button cluster's left edge aligns with the right column's left edge.
        button_section.columnconfigure(0, weight=1, uniform="bcol")
        button_section.columnconfigure(1, weight=1, uniform="bcol")
        self.button_section = button_section

        button_section.bind("<Button-1>", self.start_drag)
        button_section.bind("<B1-Motion>", self.on_drag)

        # Left col: Race Control indicator (always visible)
        self.race_control_indicator = tk.Label(
            button_section, text="ALU Timer v5.0",
            font=("Helvetica", 18, "bold"), fg="white", bg="#000000", anchor='w'
        )
        self.race_control_indicator.grid(row=0, column=0, sticky="w", padx=0, pady=0)

        # Right col: 4-button cluster — fills column so left edge aligns with
        # the race panel's right column left edge.
        btns_frame = tk.Frame(button_section, bg="#000000")
        btns_frame.grid(row=0, column=1, sticky="ew")

        self.close_button = tk.Button(
            btns_frame, text="✕", command=self.close_app,
            bg="#e74c3c", fg="white", font=("Helvetica", 11, "bold"),
            relief="flat", width=3, height=0, pady=0,
        )
        self.close_button.pack(side="right", padx=2, pady=2)

        pin_text = "●" if self.is_pinned else "○"
        pin_bg = "#95a5a6" if self.is_pinned else "#4ecdc4"
        self.pin_button = tk.Button(
            btns_frame, text=pin_text, command=self.toggle_pin,
            bg=pin_bg, fg="white", font=("Helvetica", 11, "bold"),
            relief="flat", width=3, height=0, pady=0,
        )
        self.pin_button.pack(side="right", padx=2, pady=2)

        self.debug_button = tk.Button(
            btns_frame, text="🐛", command=self.toggle_debug,
            bg="#3498db", fg="white", font=("Helvetica", 11, "bold"),
            relief="flat", width=3, height=0, pady=0,
        )
        self.debug_button.pack(side="right", padx=2, pady=2)

        self.race_button = tk.Button(
            btns_frame, text="▾", command=self.toggle_race_panel,
            bg="#e67e22", fg="white", font=("Helvetica", 11, "bold"),
            relief="flat", width=3, height=0, pady=0,
        )
        self.race_button.pack(side="right", padx=2, pady=2)

        # ── Race panel (hidden, packed below when toggled) ──
        self.race_panel = tk.Frame(self.root, bg="#000000", height=150)
        self._create_race_panel_content()

        # ── Gear / RPM bar (hidden until a race starts) ──
        self._create_gear_rpm_bar()

        # ── Velocity indicator (hidden until a race starts) ──
        self._create_velocity_display()

        # Restore saved panel states
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
        base_height = int(100 * self.current_scaling)
        self.root.geometry(f"{base_width}x{base_height}")
        self.root.overrideredirect(True)

        # Taskbar window
        self.taskbar_window = tk.Toplevel(self.root)
        self.taskbar_window.title("ALU Timing Tool")
        self.taskbar_window.geometry("1x1+0+0")
        self.taskbar_window.withdraw()
        self.taskbar_window.iconify()

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
        self.delta_label.pack(expand=True, fill="both")
        self.delta_label.bind("<Button-1>", self.start_drag)
        self.delta_label.bind("<B1-Motion>", self.on_drag)
        self.main_display_frame.bind('<Button-3>', self.toggle_race_panel)
        self.delta_label.bind('<Button-3>', self.toggle_race_panel)

        # Button section
        btn_px = int(14 * self.current_scaling)
        button_section = tk.Frame(main_ui_frame, bg="#000000", height=30)
        button_section.pack(fill="x", side="bottom", padx=(btn_px, btn_px), pady=0)
        button_section.pack_propagate(False)
        button_section.grid_propagate(False)
        button_section.columnconfigure(0, weight=1, uniform="bcol")
        button_section.columnconfigure(1, weight=1, uniform="bcol")
        self.button_section = button_section
        button_section.bind("<Button-1>", self.start_drag)
        button_section.bind("<B1-Motion>", self.on_drag)

        self.race_control_indicator = tk.Label(
            button_section, text="ALU Timer v5.0",
            font=("Helvetica", 18, "bold"), fg="white", bg="#000000", anchor='w'
        )
        self.race_control_indicator.grid(row=0, column=0, sticky="w", padx=0, pady=0)

        btns_frame = tk.Frame(button_section, bg="#000000")
        btns_frame.grid(row=0, column=1, sticky="ew")

        self.close_button = tk.Button(
            btns_frame, text="✕", command=self.close_app,
            bg="#e74c3c", fg="white", font=("Helvetica", 11, "bold"),
            relief="flat", width=3, height=0, pady=0,
        )
        self.close_button.pack(side="right", padx=2, pady=2)

        pin_text = "●" if self.is_pinned else "○"
        pin_bg = "#4ecdc4" if self.is_pinned else "#95a5a6"
        self.pin_button = tk.Button(
            btns_frame, text=pin_text, command=self.toggle_pin,
            bg=pin_bg, fg="white", font=("Helvetica", 11, "bold"),
            relief="flat", width=3, height=0, pady=0,
        )
        self.pin_button.pack(side="right", padx=2, pady=2)

        self.debug_button = tk.Button(
            btns_frame, text="🐛", command=self.toggle_debug,
            bg="#3498db", fg="white", font=("Helvetica", 11, "bold"),
            relief="flat", width=3, height=0, pady=0,
        )
        self.debug_button.pack(side="right", padx=2, pady=2)

        self.race_button = tk.Button(
            btns_frame, text="▾", command=self.toggle_race_panel,
            bg="#e67e22", fg="white", font=("Helvetica", 11, "bold"),
            relief="flat", width=3, height=0, pady=0,
        )
        self.race_button.pack(side="right", padx=2, pady=2)

        self.race_panel = tk.Frame(self.root, bg="#000000", height=150)
        self._create_race_panel_content()

        # Gear / RPM bar
        self.gear_rpm_frame = None
        self.gear_rpm_visible = False
        self._create_gear_rpm_bar()

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

        #tk.Label(ghost_frame, text="Ghost Name:",
        #         font=("Helvetica", 12, "bold"), fg="#bdc3c7", bg="#000000").pack(anchor="w")
        self.ghost_filename_label = tk.Label(
            ghost_frame, text="By Orange & Bholla64",
            font=("Helvetica", 12,'bold'), fg="#b4c6c8", bg="#000000",
            wraplength=200, justify="left"
        )
        self.ghost_filename_label.pack(anchor="w", pady=(0, 0))

        # Mode section
        mode_frame = tk.Frame(left_column, bg="#000000")
        mode_frame.pack(fill="x", pady=(0, py))

        #tk.Label(mode_frame, text="Mode:",
        #         font=("Helvetica", 12, "bold"), fg="#bdc3c7", bg="#000000").pack(anchor="w")
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

        # Split View — fills width of left column
        self.toggle_split_view_button = tk.Button(
            left_column, text="Toggle Split View", command=self.toggle_split_view,
            bg="#7f8c8d", fg="white", font=("Helvetica", 12, "bold"),
            relief="flat", state="disabled",
        )
        self.toggle_split_view_button.pack(fill="x", pady=(0, 0))

        # ── Right column: slot button + Save + Split View ──
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
            right_column, text="Load Ghost", command=self.load_split_file,
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

        self.inference_label = tk.Label(left_column, text="Inference: --",
                                        font=("Helvetica", 10), fg="#ecf0f1", bg="#000000")
        self.inference_label.pack(anchor="w")

        self.avg_inference_label = tk.Label(left_column, text="Avg Inference: --",
                                            font=("Helvetica", 10), fg="#ecf0f1", bg="#000000")
        self.avg_inference_label.pack(anchor="w")

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

    def _restore_panel_states_from_config(self):
        """Restore panel states from saved configuration."""
        try:
            panels_config = self.ui_config.get("panels", {})
            saved_race = panels_config.get("race_panel_expanded", False)
            if saved_race and not self.race_panel_expanded:
                self.toggle_race_panel()
            saved_debug = panels_config.get("debug_panel_expanded", False)
            if saved_debug and self.race_panel_expanded and not self.debug_expanded:
                self.toggle_debug()
        except Exception as e:
            print(f"Error restoring panel states: {e}")

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
                self.inference_label.config(text=f"Inference: {self.current_inference_time:.1f}ms")
                self.avg_inference_label.config(text=f"Average: {self.avg_inference_time:.1f}ms")

            self.root.after(11, self.update_ui)
        except tk.TclError:
            pass

    # ──────────────────────────────────────────────────────────────────────
    #  Public API  (called by timer_v5_CE.py / main.py)
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

    def update_inference_time(self, current_time: float, avg_time: float):
        self.current_inference_time = current_time
        self.avg_inference_time = avg_time

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
