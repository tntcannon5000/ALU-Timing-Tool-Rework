"""
User Interface Module

This module handles the GUI for the ALU Timing Tool.
Visually based on the original v4 UI design, with v5 features (splits, CE integration).
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
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
        self.current_bg_color = "#2c3e50"

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

        # Data to display
        self.current_timer_display = "00:00.000"
        self.elapsed_ms = 0
        self.avg_loop_time = 0
        self.percentage = "0%"
        self.avg_inference_time = 0
        self.current_inference_time = 0
        self.delta_time = "Rec..."  # Default delta text (CE v5: shows Rec... in record mode)

        # Delta display font base size (adjust this to change the main display text size)
        self.DELTA_FONT_BASE = 55

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
            self.root.wm_attributes("-topmost", True)
            self.pin_button.config(text="●", bg="#4ecdc4")
        else:
            self.root.wm_attributes("-topmost", False)
            self.pin_button.config(text="○", bg="#95a5a6")

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
            # Show race control indicator
            self.race_control_indicator.pack(side="left", padx=10, pady=5)
        else:
            # Hide race control indicator
            self.race_control_indicator.pack_forget()
            self.race_panel.pack_forget()
            self.race_button.config(text="▾", bg="#e67e22")
            # Also collapse debug if open
            if self.debug_expanded:
                self.debug_frame.pack_forget()
                self.debug_expanded = False
                if hasattr(self, 'debug_button') and self.debug_button:
                    self.debug_button.config(text="🐛 Debug", bg="#3498db")
        self._auto_resize()

    def toggle_debug(self):
        """Toggle debug panel visibility within race panel."""
        if not self.race_panel_expanded:
            return

        self.debug_expanded = not self.debug_expanded
        if self.debug_expanded:
            self.debug_frame.pack(side="bottom", fill="x", padx=0, pady=(0, 0))
            if hasattr(self, 'debug_button') and self.debug_button:
                self.debug_button.config(text="🐛 Debug ▴", bg="#2980b9")
        else:
            self.debug_frame.pack_forget()
            if hasattr(self, 'debug_button') and self.debug_button:
                self.debug_button.config(text="🐛 Debug", bg="#3498db")
        self._auto_resize()

    # ──────────────────────────────────────────────────────────────────────
    #  Mode / ghost / split handling
    # ──────────────────────────────────────────────────────────────────────

    def on_mode_changed(self, event=None):
        """Handle mode change."""
        mode = self.mode_var.get()

        if mode == "record":
            self.load_ghost_button.config(state="disabled", bg="#7f8c8d", text="Load Race Ghost", command=self.load_ghost_file)
            if self.configure_splits_button:
                self.configure_splits_button.config(state="disabled", bg="#7f8c8d")
            if self.toggle_split_view_button:
                self.toggle_split_view_button.config(state="disabled", bg="#7f8c8d")
        elif mode == "race":
            self.load_ghost_button.config(state="normal", bg="#3498db", text="Load Race Ghost", command=self.load_ghost_file)
            if self.configure_splits_button:
                self.configure_splits_button.config(state="disabled", bg="#7f8c8d")
            if self.toggle_split_view_button:
                self.toggle_split_view_button.config(state="disabled", bg="#7f8c8d")
        elif mode == "splits":
            self.load_ghost_button.config(state="normal", bg="#3498db", text="Load Split Ghost", command=self.load_split_file)
            if self.configure_splits_button:
                self.configure_splits_button.config(state="normal", bg="#8e44ad")
            if self.toggle_split_view_button:
                if self.race_data_manager and getattr(self.race_data_manager, 'splits', None):
                    self.toggle_split_view_button.config(state="normal", bg="#8e44ad")
                else:
                    self.toggle_split_view_button.config(state="disabled", bg="#7f8c8d")

        if self.on_mode_change:
            self.on_mode_change(mode)

    def load_ghost_file(self):
        """Open file dialog to load a ghost file."""
        if self.on_load_ghost:
            filetypes = [("JSON files", "*.json"), ("All files", "*.*")]
            filename = filedialog.askopenfilename(
                title="Load Race Ghost",
                filetypes=filetypes,
                initialdir=os.getcwd(),
            )
            if filename:
                self.on_load_ghost(filename)

    def load_split_file(self):
        """Open file dialog to load a split-type ghost file."""
        if hasattr(self, 'on_load_split') and self.on_load_split:
            filetypes = [("JSON files", "*.json"), ("All files", "*.*")]
            filename = filedialog.askopenfilename(
                title="Load Split Race Ghost",
                filetypes=filetypes,
                initialdir=os.getcwd(),
            )
            if filename:
                self.on_load_split(filename)

    def save_ghost_file(self):
        """Open file dialog to save current race data as ghost file."""
        if self.on_save_ghost:
            filetypes = [("JSON files", "*.json"), ("All files", "*.*")]
            filename = filedialog.asksaveasfilename(
                title="Save Current Ghost",
                filetypes=filetypes,
                defaultextension=".json",
                initialdir=os.getcwd(),
            )
            if filename:
                self.on_save_ghost(filename)

    def update_ghost_filename(self, filename: str):
        """Update the displayed ghost filename."""
        if self.ghost_filename_label:
            if filename:
                self.ghost_filename_label.config(text=filename, fg="#bdc3c7")
            else:
                self.ghost_filename_label.config(text="No ghost loaded", fg="#e74c3c")

    def show_ghost_saved_message(self):
        """Show temporary 'Ghost Saved!' message."""
        if self.ghost_filename_label:
            original_text = self.ghost_filename_label.cget("text")
            original_color = self.ghost_filename_label.cget("fg")
            self.ghost_filename_label.config(text="Ghost Saved!", fg="#2ecc71",
                                             font=("Helvetica", 9, "bold underline"))

            def restore_text():
                if self.ghost_filename_label:
                    self.ghost_filename_label.config(text=original_text, fg=original_color,
                                                     font=("Helvetica", 9))

            if self.root:
                self.root.after(1000, restore_text)

    def update_save_ghost_button_state(self):
        """Update save ghost button state based on race completion."""
        if hasattr(self, 'save_ghost_button') and self.save_ghost_button:
            if self.race_data_manager and self.race_data_manager.is_race_complete():
                self.save_ghost_button.config(state="normal", bg="#f39c12")
            else:
                self.save_ghost_button.config(state="disabled", bg="#7f8c8d")

    # ──────────────────────────────────────────────────────────────────────
    #  Split view
    # ──────────────────────────────────────────────────────────────────────

    def open_configure_splits_dialog(self):
        """Open a dialog allowing the user to configure split names and percentages."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Configure Splits")
        dialog.geometry("480x420")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(bg="#34495e")

        tk.Label(dialog, text="Number of splits (2-10):", bg="#34495e", fg="white").pack(pady=(8, 4))
        initial_count = 2
        if self.race_data_manager and getattr(self.race_data_manager, 'splits', None):
            initial_count = len(self.race_data_manager.splits)
        count_var = tk.IntVar(value=initial_count)
        count_spin = tk.Spinbox(dialog, from_=2, to=10, textvariable=count_var, width=5)
        count_spin.pack(pady=(0, 6))

        rows_frame = tk.Frame(dialog, bg="#34495e")
        rows_frame.pack(fill="both", expand=True, padx=8, pady=4)

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
                frame = tk.Frame(rows_frame, bg="#34495e")
                frame.pack(fill="x", pady=2)
                tk.Label(frame, text=f"Split {i+1} name:", bg="#34495e", fg="white").pack(side="left")
                name_var = tk.StringVar(value=(existing[i]['name'] if i < len(existing) else f"split_{i+1}"))
                name_entry = tk.Entry(frame, textvariable=name_var, width=18)
                name_entry.pack(side="left", padx=6)
                tk.Label(frame, text="Percent:", bg="#34495e", fg="white").pack(side="left")
                if i == n - 1:
                    percent_var = tk.IntVar(value=99)
                    tk.Label(frame, text="End", bg="#34495e", fg="#ecf0f1", width=5).pack(side="left", padx=6)
                else:
                    default_percent = (existing[i]['percent'] if i < len(existing) else int(((i+1)/n)*99))
                    percent_var = tk.IntVar(value=default_percent)
                    tk.Spinbox(frame, from_=1, to=98, textvariable=percent_var, width=5).pack(side="left", padx=6)
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

        btn_frame = tk.Frame(dialog, bg="#34495e")
        btn_frame.pack(pady=8)

        def save_and_close():
            splits_list = []
            try:
                for name_var, percent_var in entry_widgets:
                    name = name_var.get().strip()
                    percent = int(percent_var.get())
                    splits_list.append([name, percent])
            except Exception:
                messagebox.showerror("Error", "Invalid split values")
                return

            if not (2 <= len(splits_list) <= 10):
                messagebox.showerror("Error", "Splits count must be between 2 and 10")
                return
            if splits_list[-1][1] != 99:
                messagebox.showerror("Error", "Last split percent must be 99")
                return

            percents = [p for (_, p) in splits_list]
            if any(p < 1 or p > 99 for p in percents):
                messagebox.showerror("Error", "Split percents must be between 1 and 99")
                return
            if any(percents[i] <= percents[i-1] for i in range(1, len(percents))):
                messagebox.showerror("Error", "Split percents must be strictly increasing")
                return

            normalized = None
            if self.race_data_manager and hasattr(self.race_data_manager, '_normalize_splits'):
                normalized = self.race_data_manager._normalize_splits(splits_list)
                if normalized is None:
                    messagebox.showerror("Error", "Failed to normalize splits")
                    return
                self.race_data_manager.splits = normalized
                if self.toggle_split_view_button:
                    self.toggle_split_view_button.config(state="normal", bg="#8e44ad")

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
                self.on_configure_splits(normalized if normalized is not None else splits_list)

            dialog.destroy()

        tk.Button(btn_frame, text="Save", command=save_and_close, bg="#27ae60", fg="white", width=10).pack(side="left", padx=6)
        tk.Button(btn_frame, text="Cancel", command=dialog.destroy, bg="#e74c3c", fg="white", width=10).pack(side="left", padx=6)
        dialog.focus_set()

    def toggle_split_view(self):
        """Toggle the split comparison view visibility."""
        self.split_view_visible = not self.split_view_visible
        if self.split_view_visible:
            if not self.split_view_frame:
                self.split_view_frame = tk.Frame(self.root, bg="#222f3e")
            # Pack split view between main display and race panel
            self.split_view_frame.pack(side="top", fill="x", padx=0, pady=(4, 0))
            self.update_split_view()
        else:
            if self.split_view_frame:
                self.split_view_frame.pack_forget()
        self._adjust_height_for_split_view()

    def _get_split_view_height(self):
        """Calculate split view height if visible."""
        if not self.split_view_visible or not self.race_data_manager:
            return 0
        try:
            splits = self.race_data_manager.splits
            if splits:
                return max(60, int(len(splits) * 28 * self.current_scaling))
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

    def _format_time_ms(self, ms_str: str) -> str:
        try:
            if not ms_str or ms_str == "0000000":
                return "--:--.---"
            ms = int(ms_str)
            seconds = ms / 1000.0
            m = int(seconds // 60)
            s = seconds - (m * 60)
            return f"{m}:{s:06.3f}"
        except Exception:
            return "--:--.---"

    def _format_delta_ms(self, delta_ms: int) -> str:
        try:
            if delta_ms is None:
                return ""
            sign = '-' if delta_ms < 0 else '+'
            s = abs(delta_ms) / 1000.0
            return f"{sign}{s:0.2f}"
        except Exception:
            return ""

    def update_split_view(self):
        """Rebuild the split comparison view from current split data."""
        if not self.split_view_frame:
            self.split_view_frame = tk.Frame(self.root, bg="#222f3e")

        for w in self.split_view_frame.winfo_children():
            w.destroy()

        splits = None
        if self.race_data_manager and hasattr(self.race_data_manager, 'get_splits'):
            splits = self.race_data_manager.get_splits()

        if not splits:
            tk.Label(self.split_view_frame, text="No splits configured", bg="#222f3e", fg="white").pack(padx=8, pady=4)
            return

        has_live = False
        try:
            for v in (self.race_data_manager.current_race_data.values()
                      if hasattr(self.race_data_manager, 'current_race_data') else []):
                if v != "0000000":
                    has_live = True
                    break
        except Exception:
            has_live = False

        font_size = max(8, int(10 * self.current_scaling))

        for s_item in splits:
            name = s_item.get('name', 'split')
            percent = s_item.get('percent', 0)

            ghost_time = None
            if getattr(self.race_data_manager, 'split_times', None):
                ghost_time = self.race_data_manager.split_times.get(str(percent), "0000000")

            row = tk.Frame(self.split_view_frame, bg="#222f3e")
            row.pack(fill='x', padx=8, pady=2)

            if not has_live:
                tk.Label(row, text=name, bg="#222f3e", fg="white", anchor='w',
                         width=10, font=("Helvetica", font_size)).grid(row=0, column=0, sticky='w')
                tk.Label(row, text="=0.00", bg="#222f3e", fg="#bdc3c7",
                         width=5, anchor='e', font=("Helvetica", font_size)).grid(row=0, column=1, sticky='e')
                tk.Label(row, text="=0.00", bg="#222f3e", fg="#bdc3c7",
                         width=5, anchor='e', font=("Helvetica", font_size)).grid(row=0, column=2, sticky='e')
                tk.Label(row, text="0.00", bg="#222f3e", fg="#bdc3c7",
                         width=4, anchor='e', font=("Helvetica", font_size)).grid(row=0, column=3, sticky='e')
            else:
                current_time = (self.race_data_manager.current_race_data.get(str(percent), "0000000")
                                if hasattr(self.race_data_manager, 'current_race_data') else "0000000")
                delta_display = ""
                try:
                    if current_time and ghost_time and current_time != "0000000" and ghost_time != "0000000":
                        delta_ms = int(current_time) - int(ghost_time)
                        delta_display = self._format_delta_ms(delta_ms)
                except Exception:
                    delta_display = ""

                tk.Label(row, text=name, bg="#222f3e", fg="white", anchor='w',
                         width=20, font=("Helvetica", font_size)).pack(side='left')
                delta_fg = "#2ecc71" if delta_display and delta_display.startswith('-') else "#e74c3c"
                tk.Label(row, text=delta_display, bg="#222f3e", fg=delta_fg,
                         width=8, font=("Helvetica", font_size)).pack(side='left')
                tk.Label(row, text=self._format_time_ms(ghost_time), bg="#222f3e", fg="#bdc3c7",
                         anchor='e', width=12, font=("Helvetica", font_size)).pack(side='right')

    # ──────────────────────────────────────────────────────────────────────
    #  Background color (race mode delta coloring)
    # ──────────────────────────────────────────────────────────────────────

    def update_background_color(self, mode: str, delta: float = None):
        """Update UI background color based on race mode and delta."""
        if mode == "race" and delta is not None:
            if delta < 0:
                bg_color = "#2d5a3d"  # green — ahead
            elif delta > 0:
                bg_color = "#5a2d2d"  # red — behind
            else:
                bg_color = "#2d3a5a"  # blue — even
        else:
            bg_color = "#2c3e50"

        if bg_color != self.current_bg_color:
            self.current_bg_color = bg_color
            if hasattr(self, 'main_display_frame') and self.main_display_frame:
                self.main_display_frame.configure(bg=bg_color)
            if hasattr(self, 'delta_label') and self.delta_label:
                self.delta_label.configure(bg=bg_color)
            if hasattr(self, 'button_section') and self.button_section:
                self.button_section.configure(bg=bg_color)
            if hasattr(self, 'race_control_indicator') and self.race_control_indicator:
                self.race_control_indicator.configure(bg=bg_color)

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
            dialog.configure(bg="#34495e")
            dialog.transient(self.root)
            dialog.grab_set()

            tk.Label(dialog, text="Race name:", bg="#34495e", fg="white").pack(pady=(10, 5))
            filename_var = tk.StringVar()
            entry = tk.Entry(dialog, textvariable=filename_var, width=30)
            entry.pack(pady=5)
            entry.focus_set()

            button_frame = tk.Frame(dialog, bg="#34495e")
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
                width, height, x, y = 300, 120, "100", "100"

            new_width = int(width * scaling_ratio)
            new_height = int(height * scaling_ratio)

            was_race_expanded = self.race_panel_expanded
            was_debug_expanded = self.debug_expanded
            current_mode = self.get_current_mode() if self.mode_var else "record"

            for widget in self.root.winfo_children():
                widget.destroy()

            self.root.tk.call("tk", "scaling", self.current_scaling)

            base_width = int(300 * self.current_scaling)
            base_height = int(120 * self.current_scaling)
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
        self.adjust_scaling(0.05)

    def decrease_scaling(self):
        self.adjust_scaling(-0.05)

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
        self.start_x = event.x
        self.start_y = event.y

    def on_drag(self, event):
        x = self.root.winfo_x() + (event.x - self.start_x)
        y = self.root.winfo_y() + (event.y - self.start_y)
        self.root.geometry(f"+{x}+{y}")

    # ──────────────────────────────────────────────────────────────────────
    #  UI creation  (matches old v4 layout exactly)
    # ──────────────────────────────────────────────────────────────────────

    def create_ui(self):
        """Create the main UI window."""
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
        base_h = int(120 * self.current_scaling)
        gparts = geometry.replace('x', '+').replace('+', ' ').split()
        self.root.geometry(f"{gparts[0]}x{base_h}+{gparts[2]}+{gparts[3]}")
        self.root.overrideredirect(True)

        # Hidden taskbar window
        self.taskbar_window = tk.Toplevel(self.root)
        self.taskbar_window.title("ALU Timing Tool")
        self.taskbar_window.geometry("1x1+0+0")
        self.taskbar_window.withdraw()
        self.taskbar_window.iconify()

        self.root.configure(bg="#2c3e50")

        # Pin state
        self.is_pinned = self.ui_config.get("is_pinned", True)
        self.root.wm_attributes("-topmost", self.is_pinned)

        # ── Main container (fixed height — does not grow with panels) ──
        main_container = tk.Frame(self.root, bg="#2c3e50", height=base_h)
        main_container.pack(side="top", fill="x")
        main_container.pack_propagate(False)

        # Main UI frame (delta display + button bar)
        main_ui_frame = tk.Frame(main_container, bg="#2c3e50")
        main_ui_frame.pack(side="left", fill="both", expand=True)

        main_ui_frame.bind("<Button-1>", self.start_drag)
        main_ui_frame.bind("<B1-Motion>", self.on_drag)

        # Delta display area
        self.main_display_frame = tk.Frame(main_ui_frame, bg="#2c3e50")
        self.main_display_frame.pack(fill="both", expand=True)
        self.main_display_frame.bind("<Button-1>", self.start_drag)
        self.main_display_frame.bind("<B1-Motion>", self.on_drag)

        self.delta_label = tk.Label(
            self.main_display_frame, text=self.delta_time,
            font=("Helvetica", self.DELTA_FONT_BASE, "bold"),
            fg="#ecf0f1", bg="#2c3e50",
        )
        self.delta_label.pack(expand=True, fill="both")
        self.delta_label.bind("<Button-1>", self.start_drag)
        self.delta_label.bind("<B1-Motion>", self.on_drag)

        # Right-click to toggle race panel
        self.main_display_frame.bind('<Button-3>', self.toggle_race_panel)
        self.delta_label.bind('<Button-3>', self.toggle_race_panel)

        # ── Bottom button section (30 px bar) ──
        button_section = tk.Frame(main_ui_frame, bg="#2c3e50", height=30)
        button_section.pack(fill="x", side="bottom")
        button_section.pack_propagate(False)
        self.button_section = button_section

        button_section.bind("<Button-1>", self.start_drag)
        button_section.bind("<B1-Motion>", self.on_drag)

        # Race Control indicator (left, hidden until panel opens)
        self.race_control_indicator = tk.Label(
            button_section, text="Race Control",
            font=("Helvetica", 10, "bold"), fg="white", bg="#2c3e50",
        )

        # Close button (rightmost)
        self.close_button = tk.Button(
            button_section, text="✕", command=self.close_app,
            bg="#e74c3c", fg="white", font=("Helvetica", 11, "bold"),
            relief="flat", width=3, height=0, pady=0,
        )
        self.close_button.pack(side="right", padx=2, pady=2)

        # Pin button
        pin_text = "●" if self.is_pinned else "○"
        pin_bg = "#4ecdc4" if self.is_pinned else "#95a5a6"
        self.pin_button = tk.Button(
            button_section, text=pin_text, command=self.toggle_pin,
            bg=pin_bg, fg="white", font=("Helvetica", 11, "bold"),
            relief="flat", width=3, height=0, pady=0,
        )
        self.pin_button.pack(side="right", padx=2, pady=2)

        # Race panel toggle button
        self.race_button = tk.Button(
            button_section, text="▾", command=self.toggle_race_panel,
            bg="#e67e22", fg="white", font=("Helvetica", 11, "bold"),
            relief="flat", width=3, height=0, pady=0,
        )
        self.race_button.pack(side="right", padx=2, pady=2)

        # ── Race panel (hidden, packed below when toggled) ──
        self.race_panel = tk.Frame(self.root, bg="#2c3e50", height=150)
        self._create_race_panel_content()

        # Restore saved panel states
        self._restore_panel_states_from_config()

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
        base_height = int(120 * self.current_scaling)
        self.root.geometry(f"{base_width}x{base_height}")
        self.root.overrideredirect(True)

        # Taskbar window
        self.taskbar_window = tk.Toplevel(self.root)
        self.taskbar_window.title("ALU Timing Tool")
        self.taskbar_window.geometry("1x1+0+0")
        self.taskbar_window.withdraw()
        self.taskbar_window.iconify()

        self.root.configure(bg="#2c3e50")
        self.root.wm_attributes("-topmost", self.is_pinned)

        # Main container (fixed height — does not grow with panels)
        main_container = tk.Frame(self.root, bg="#2c3e50", height=base_height)
        main_container.pack(side="top", fill="x")
        main_container.pack_propagate(False)

        main_ui_frame = tk.Frame(main_container, bg="#2c3e50")
        main_ui_frame.pack(side="left", fill="both", expand=True)
        main_ui_frame.bind("<Button-1>", self.start_drag)
        main_ui_frame.bind("<B1-Motion>", self.on_drag)

        self.main_display_frame = tk.Frame(main_ui_frame, bg="#2c3e50")
        self.main_display_frame.pack(fill="both", expand=True)
        self.main_display_frame.bind("<Button-1>", self.start_drag)
        self.main_display_frame.bind("<B1-Motion>", self.on_drag)

        self.delta_label = tk.Label(
            self.main_display_frame, text=self.delta_time,
            font=("Helvetica", self.DELTA_FONT_BASE, "bold"),
            fg="#ecf0f1", bg="#2c3e50",
        )
        self.delta_label.pack(expand=True, fill="both")
        self.delta_label.bind("<Button-1>", self.start_drag)
        self.delta_label.bind("<B1-Motion>", self.on_drag)
        self.main_display_frame.bind('<Button-3>', self.toggle_race_panel)
        self.delta_label.bind('<Button-3>', self.toggle_race_panel)

        # Button section
        button_section = tk.Frame(main_ui_frame, bg="#2c3e50", height=30)
        button_section.pack(fill="x", side="bottom")
        button_section.pack_propagate(False)
        self.button_section = button_section
        button_section.bind("<Button-1>", self.start_drag)
        button_section.bind("<B1-Motion>", self.on_drag)

        self.race_control_indicator = tk.Label(
            button_section, text="Race Control",
            font=("Helvetica", 10, "bold"), fg="white", bg="#2c3e50",
        )

        self.close_button = tk.Button(
            button_section, text="✕", command=self.close_app,
            bg="#e74c3c", fg="white", font=("Helvetica", 11, "bold"),
            relief="flat", width=3, height=0, pady=0,
        )
        self.close_button.pack(side="right", padx=2, pady=2)

        pin_text = "●" if self.is_pinned else "○"
        pin_bg = "#4ecdc4" if self.is_pinned else "#95a5a6"
        self.pin_button = tk.Button(
            button_section, text=pin_text, command=self.toggle_pin,
            bg=pin_bg, fg="white", font=("Helvetica", 11, "bold"),
            relief="flat", width=3, height=0, pady=0,
        )
        self.pin_button.pack(side="right", padx=2, pady=2)

        self.race_button = tk.Button(
            button_section, text="▾", command=self.toggle_race_panel,
            bg="#e67e22", fg="white", font=("Helvetica", 11, "bold"),
            relief="flat", width=3, height=0, pady=0,
        )
        self.race_button.pack(side="right", padx=2, pady=2)

        self.race_panel = tk.Frame(self.root, bg="#2c3e50", height=150)
        self._create_race_panel_content()

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
        """Create the race panel content with 2-column layout (old UI design)."""
        if not self.race_panel:
            return

        # Main 2-column container
        main_container = tk.Frame(self.race_panel, bg="#2c3e50")
        main_container.pack(fill="both", expand=True, padx=15, pady=15)

        # ── Left column: Ghost info + Mode selector ──
        left_column = tk.Frame(main_container, bg="#2c3e50")
        left_column.pack(side="left", fill="both", expand=True, padx=(0, 15))

        # Ghost section
        ghost_frame = tk.Frame(left_column, bg="#2c3e50")
        ghost_frame.pack(fill="x", pady=(0, 15))

        tk.Label(ghost_frame, text="Ghost Name:",
                 font=("Helvetica", 10, "bold"), fg="#bdc3c7", bg="#2c3e50").pack(anchor="w")
        self.ghost_filename_label = tk.Label(
            ghost_frame, text="No ghost loaded",
            font=("Helvetica", 9), fg="#e74c3c", bg="#2c3e50",
            wraplength=200, justify="left",
        )
        self.ghost_filename_label.pack(anchor="w", pady=(2, 0))

        # Mode section
        mode_frame = tk.Frame(left_column, bg="#2c3e50")
        mode_frame.pack(fill="x", pady=(0, 5))

        tk.Label(mode_frame, text="Mode:",
                 font=("Helvetica", 10, "bold"), fg="#bdc3c7", bg="#2c3e50").pack(anchor="w")
        self.mode_var = tk.StringVar(value="record")
        self.mode_combobox = ttk.Combobox(
            mode_frame, textvariable=self.mode_var,
            values=["record", "race", "splits"],
            state="readonly", width=18,
        )
        self.mode_combobox.pack(anchor="w", pady=(2, 0))
        self.mode_combobox.bind('<<ComboboxSelected>>', self.on_mode_changed)

        # Debug button (below mode selector)
        self.debug_button = tk.Button(
            left_column, text="🐛 Debug", command=self.toggle_debug,
            bg="#3498db", fg="white", font=("Helvetica", 9),
            relief="flat", anchor="w",
        )
        self.debug_button.pack(anchor="w", pady=(10, 0))

        # ── Right column: Action buttons ──
        right_column = tk.Frame(main_container, bg="#2c3e50")
        right_column.pack(side="right", fill="both", expand=True)

        # Load ghost
        self.load_ghost_button = tk.Button(
            right_column, text="Load Race Ghost", command=self.load_ghost_file,
            bg="#7f8c8d", fg="white", font=("Helvetica", 9),
            relief="flat", width=18, state="disabled",
        )
        self.load_ghost_button.pack(pady=(0, 10))

        # Save ghost
        self.save_ghost_button = tk.Button(
            right_column, text="Save Current Ghost", command=self.save_ghost_file,
            bg="#7f8c8d", fg="white", font=("Helvetica", 9),
            relief="flat", width=18, state="disabled",
        )
        self.save_ghost_button.pack(pady=(0, 10))

        # Configure splits button (disabled unless splits mode)
        self.configure_splits_button = tk.Button(
            right_column, text="Configure Splits", command=self.open_configure_splits_dialog,
            bg="#7f8c8d", fg="white", font=("Helvetica", 9),
            relief="flat", width=18, state="disabled",
        )
        self.configure_splits_button.pack(pady=(0, 5))

        # Toggle split view button (disabled unless splits configured)
        self.toggle_split_view_button = tk.Button(
            right_column, text="Split View", command=self.toggle_split_view,
            bg="#7f8c8d", fg="white", font=("Helvetica", 9),
            relief="flat", width=18, state="disabled",
        )
        self.toggle_split_view_button.pack(pady=(0, 10))

        # ── Debug panel (hidden, packed below when expanded) ──
        self.debug_frame = tk.Frame(self.race_panel, bg="#2c3e50")
        self._create_debug_panel_content()

    def _create_debug_panel_content(self):
        """Create the debug panel content with 2-column layout (old UI design)."""
        if not self.debug_frame:
            return

        main_container = tk.Frame(self.debug_frame, bg="#2c3e50")
        main_container.pack(fill="both", expand=True, padx=5, pady=3)

        # Title row
        title_row = tk.Frame(main_container, bg="#2c3e50")
        title_row.pack(fill="x", pady=(0, 3))

        tk.Label(title_row, text="Debug Information",
                 font=("Helvetica", 11, "bold"), fg="#ecf0f1", bg="#2c3e50").pack(side="left", anchor="w")

        self.debug_close_button = tk.Button(
            title_row, text="✕", font=("Helvetica", 11, "bold"),
            bg="#e74c3c", fg="white", width=3, height=0, pady=0,
            command=self.toggle_debug, relief="flat", bd=1,
        )
        self.debug_close_button.pack(side="right")

        # 2-column info
        info_container = tk.Frame(main_container, bg="#2c3e50")
        info_container.pack(fill="both", expand=True)

        # Left: Performance metrics
        left_column = tk.Frame(info_container, bg="#2c3e50")
        left_column.pack(side="left", fill="both", expand=True, padx=(0, 10))

        tk.Label(left_column, text="Performance Metrics",
                 font=("Helvetica", 10, "bold"), fg="#bdc3c7", bg="#2c3e50").pack(anchor="w", pady=(0, 3))

        self.elapsed_label = tk.Label(left_column, text=f"Loop: {self.elapsed_ms:.1f}ms",
                                      font=("Helvetica", 9), fg="#ecf0f1", bg="#2c3e50")
        self.elapsed_label.pack(anchor="w")

        self.avg_loop_label = tk.Label(left_column, text="Avg Loop: --",
                                       font=("Helvetica", 9), fg="#ecf0f1", bg="#2c3e50")
        self.avg_loop_label.pack(anchor="w")

        self.inference_label = tk.Label(left_column, text="Inference: --",
                                        font=("Helvetica", 9), fg="#ecf0f1", bg="#2c3e50")
        self.inference_label.pack(anchor="w")

        self.avg_inference_label = tk.Label(left_column, text="Avg Inference: --",
                                            font=("Helvetica", 9), fg="#ecf0f1", bg="#2c3e50")
        self.avg_inference_label.pack(anchor="w")

        # Right: Game state
        right_column = tk.Frame(info_container, bg="#2c3e50")
        right_column.pack(side="right", fill="both", expand=True)

        tk.Label(right_column, text="Game State",
                 font=("Helvetica", 10, "bold"), fg="#bdc3c7", bg="#2c3e50").pack(anchor="w", pady=(0, 3))

        self.time_label = tk.Label(right_column, text=f"Timer: {self.current_timer_display}",
                                    font=("Helvetica", 9), fg="#ecf0f1", bg="#2c3e50")
        self.time_label.pack(anchor="w")

        self.percentage_label = tk.Label(right_column, text="Distance: --",
                                          font=("Helvetica", 9, "bold"), fg="#95a5a6", bg="#2c3e50")
        self.percentage_label.pack(anchor="w")

        self.debug_timer_label = tk.Label(right_column, text="Timer: 00:00.000",
                                           font=("Courier", 9), fg="#95a5a6", bg="#2c3e50")
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
            if current_mode == "race" or current_mode == "splits":
                self.delta_label.config(text=self.delta_time)
            else:
                # Record mode: show live timer or "Rec..."
                if self.current_timer_display and self.current_timer_display != "00:00.000":
                    self.delta_label.config(text=self.current_timer_display)
                else:
                    self.delta_label.config(text="Rec...")

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

    def update_loop_time(self, elapsed_ms: float, avg_loop_time: float):
        self.elapsed_ms = elapsed_ms
        self.avg_loop_time = avg_loop_time

    def update_inference_time(self, current_time: float, avg_time: float):
        self.current_inference_time = current_time
        self.avg_inference_time = avg_time

    def get_current_mode(self) -> str:
        if self.mode_var:
            return self.mode_var.get()
        return "record"

    def show_message(self, title: str, message: str, is_error: bool = False):
        if is_error:
            messagebox.showerror(title, message)
        else:
            messagebox.showinfo(title, message)

    def close(self):
        self.close_app()
