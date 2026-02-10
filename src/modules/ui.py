"""
User Interface Module

This module handles the GUI for the ALU Timing Tool.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import shutil
import threading
import sys
import os
from src.utils.ui_config import UIConfigManager
#from ui_config import UIConfigManager
class TimingToolUI:
    """
    Main UI class for the ALU Timing Tool.
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
        # Split view elements
        self.split_view_frame = None
        self.split_view_visible = False
        self.toggle_split_view_button = None
        
        # Data to display
        self.current_timer_display = "00:00.000"
        self.elapsed_ms = 0
        self.avg_loop_time = 0
        self.percentage = "0%"
        self.avg_inference_time = 0
        self.current_inference_time = 0
        self.delta_time = "=0.00"  # Default delta time
        
        # Scaling adjustment - load from config
        self.current_scaling = self.ui_config.get("scaling", 1.15)  # Load from config or use default
        
        # Callbacks for race functionality
        self.on_mode_change = None
        self.on_load_ghost = None
        self.on_save_ghost = None
        self.on_save_race = None
        self.on_close = None
        
        # Load panel states from config
        self.race_panel_expanded = self.ui_config.get("panels", {}).get("race_panel_expanded", False)
        self.debug_expanded = self.ui_config.get("panels", {}).get("debug_panel_expanded", False)
        self.is_pinned = self.ui_config.get("is_pinned", True)
    
    def save_ui_config(self):
        """Save current UI configuration to file."""
        try:
            if self.root:

                #retract both windows for accurate geometry measurement
                if self.race_panel_expanded: 
                    print(self.root.geometry())
                    self.toggle_race_panel()
                    print(self.root.geometry())
                # Get current window geometry
                geometry = self.root.geometry()
                geometry_info = self.config_manager.extract_geometry_from_string(geometry)
                # Update configuration
                config = {
                    "window_position": geometry_info["window_position"],
                    "window_size": geometry_info["window_size"],
                    "scaling": self.current_scaling,
                    "is_pinned": self.is_pinned,
                }
                
                # Save to file
                success = self.config_manager.save_config(config)
                if success:
                    print("UI configuration saved successfully")
                else:
                    print("Failed to save UI configuration")
        except Exception as e:
            print(f"Error saving UI configuration: {e}")
    
    def _get_base_height(self):
        """Get the base height of just the delta display."""
        self.main_display_frame.config(height=int(120 * self.current_scaling))
        return int(120 * self.current_scaling)
    
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
    
    def _get_race_panel_height(self):
        """Get race panel height (includes debug if expanded)."""
        if not self.race_panel_expanded:
            return 0
        base = int(137 * self.current_scaling)
        if self.debug_expanded:
            debug_height = int(100 * self.current_scaling)
            return base + debug_height
        return base
    
    def _calculate_total_height(self):
        """Calculate total window height based on visible panels."""
        total = self._get_base_height()
        total += self._get_split_view_height()
        total += self._get_race_panel_height()
        return total
    
    def _update_window_height(self):
        """Update window height based on current panel states."""
        if not self.root:
            return
        current_geometry = self.root.geometry()
        parts = current_geometry.replace('x', '+').replace('+', ' ').split()
        width = parts[0]
        x = parts[2]
        y = parts[3]
        new_height = self._calculate_total_height()
        self.root.geometry(f"{width}x{new_height}+{x}+{y}")
        self.main_display_frame.config(height=int(120 * self.current_scaling))
        self.root.update()

    def toggle_pin(self):
        """Toggle window pin state."""
        self.is_pinned = not self.is_pinned
        if self.is_pinned:
            self.root.wm_attributes("-topmost", True)
            self.pin_button.config(text="📌", bg="#4ecdc4")
        else:
            self.root.wm_attributes("-topmost", False)
            self.pin_button.config(text="📍", bg="#95a5a6")
    
    def toggle_race_panel(self,none=None):
        """Toggle race panel visibility."""
        self.race_panel_expanded = not self.race_panel_expanded
        if self.race_panel_expanded:
            # Pack race panel (below main_ui_frame in main_container)
            self.race_panel.pack(side="top", fill="x", expand=False, padx=int(0 * self.current_scaling), pady=int(0 * self.current_scaling))
            self.race_panel.pack_propagate(True)
            # Ensure debug button is visible when race panel opens (unless debug is expanded)
            if hasattr(self, 'debug_button') and self.debug_button and not self.debug_expanded:
                self.debug_button.pack(padx=int(5 * self.current_scaling), pady=int(0 * self.current_scaling))
        else:
            # Unpack race panel
            self.race_panel.pack_forget()
            # Also collapse debug if race panel is closed
            if self.debug_expanded:
                self.debug_frame.pack_forget()
                self.debug_expanded = False
            # Ensure debug button is hidden
            if hasattr(self, 'debug_button') and self.debug_button:
                self.debug_button.pack_forget()
        
        # Recalculate window height
        self._update_window_height()
    
    def on_mode_changed(self, event=None):
        """Handle mode change."""
        mode = self.mode_var.get()

        # Update load button and configure button depending on mode
        if mode == "record":
            self.load_ghost_button.config(state="disabled", bg="#7f8c8d", text="Load Race Ghost", command=self.load_ghost_file)
            self.configure_splits_button.config(state="disabled", bg="#7f8c8d")
        elif mode == "race":
            self.load_ghost_button.config(state="normal", bg="#3498db", text="Load Race Ghost", command=self.load_ghost_file)
            self.configure_splits_button.config(state="disabled", bg="#7f8c8d")
        elif mode == "splits":
            self.load_ghost_button.config(state="normal", bg="#3498db", text="Load Split Race Ghost", command=self.load_split_file)
            self.configure_splits_button.config(state="normal", bg="#8e44ad")
            # Only enable toggle if a splits configuration exists
            if hasattr(self, 'toggle_split_view_button') and self.toggle_split_view_button:
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
                initialdir=os.getcwd()
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
                initialdir=os.getcwd()
            )
            if filename:
                self.on_load_split(filename)

    def open_configure_splits_dialog(self):
        """Open a dialog allowing the user to configure split names and percentages."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Configure Splits")
        dialog.geometry("480x420")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(bg="#34495e")

        # Number of splits selector
        tk.Label(dialog, text="Number of splits (2-10):", bg="#34495e", fg="white").pack(pady=(int(8 * self.current_scaling), int(4 * self.current_scaling)))
        initial_count = 2
        if self.race_data_manager and getattr(self.race_data_manager, 'splits', None):
            initial_count = len(self.race_data_manager.splits)
        count_var = tk.IntVar(value=initial_count)
        count_spin = tk.Spinbox(dialog, from_=2, to=10, textvariable=count_var, width=5)
        count_spin.pack(pady=(0, int(6 * self.current_scaling)))

        rows_frame = tk.Frame(dialog, bg="#34495e")
        rows_frame.pack(fill="both", expand=True, padx=int(8 * self.current_scaling), pady=int(4 * self.current_scaling))

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
                frame.pack(fill="x", pady=(int(2 * self.current_scaling), int(2 * self.current_scaling)))
                tk.Label(frame, text=f"Split {i+1} name:", bg="#34495e", fg="white").pack(side="left")
                name_var = tk.StringVar(value=(existing[i]['name'] if i < len(existing) else f"split_{i+1}"))
                name_entry = tk.Entry(frame, textvariable=name_var, width=18)
                name_entry.pack(side="left", padx=int(6 * self.current_scaling))
                tk.Label(frame, text="Percent:", bg="#34495e", fg="white").pack(side="left")
                # Last split is hardcoded to 99% and should be shown as non-interactive "End"
                if i == n - 1:
                    percent_var = tk.IntVar(value=99)
                    end_label = tk.Label(frame, text="End", bg="#34495e", fg="#ecf0f1", width=5)
                    end_label.pack(side="left", padx=int(6 * self.current_scaling))
                else:
                    default_percent = (existing[i]['percent'] if i < len(existing) else int(((i+1)/n)*99))
                    percent_var = tk.IntVar(value=default_percent)
                    percent_entry = tk.Spinbox(frame, from_=1, to=98, textvariable=percent_var, width=5)
                    percent_entry.pack(side="left", padx=int(6 * self.current_scaling))
                entry_widgets.append((name_var, percent_var))

        def on_count_change(*args):
            try:
                v = int(count_var.get())
            except Exception:
                v = 2
                count_var.set(2)
            v = max(2, min(10, v))
            count_var.set(v)
            build_rows()

        count_var.trace_add('write', lambda *args: on_count_change())
        build_rows()

        # Buttons
        btn_frame = tk.Frame(dialog, bg="#34495e")
        btn_frame.pack(pady=int(8 * self.current_scaling))

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
                # After configuring splits, enable toggle split view button
                if hasattr(self, 'toggle_split_view_button') and self.toggle_split_view_button:
                    self.toggle_split_view_button.config(state="normal", bg="#8e44ad")

            # If a split file is already loaded, back it up before overwriting
            if (self.race_data_manager and getattr(self.race_data_manager, 'is_split_loaded', False)
                    and getattr(self.race_data_manager, 'split_filepath', None)):
                try:
                    orig = self.race_data_manager.split_filepath
                    d, fname = os.path.split(orig)
                    base, ext = os.path.splitext(fname)
                    n = 0
                    while True:
                        if n == 0:
                            candidate = os.path.join(d, f"{base} backup{ext}")
                        else:
                            candidate = os.path.join(d, f"{base} backup {n}{ext}")
                        if not os.path.exists(candidate):
                            break
                        n += 1
                    shutil.copy(orig, candidate)
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to create backup: {e}")
                    return

                # Save updated split configuration back to the original file
                if hasattr(self.race_data_manager, 'save_split_data'):
                    saved = self.race_data_manager.save_split_data()
                    if not saved:
                        messagebox.showerror("Error", "Failed to save updated split file")
                        return

            if hasattr(self, 'on_configure_splits') and self.on_configure_splits:
                self.on_configure_splits(normalized if normalized is not None else splits_list)

            dialog.destroy()

        tk.Button(btn_frame, text="Save", command=save_and_close, bg="#27ae60", fg="white", width=10).pack(side="left", padx=int(6 * self.current_scaling))
        tk.Button(btn_frame, text="Cancel", command=dialog.destroy, bg="#e74c3c", fg="white", width=10).pack(side="left", padx=int(6 * self.current_scaling))

        dialog.focus_set()

    def toggle_split_view(self):
        """Toggle the split comparison view visibility."""
        self.split_view_visible = not self.split_view_visible
        if self.split_view_visible:
            # Create frame if missing
            if not self.split_view_frame:
                self.split_view_frame = tk.Frame(self.root, bg="#222f3e")
            # Pack split view below delta display, independently of race panel
            self.split_view_frame.pack(side="top", fill="x", expand=False, padx=int(0 * self.current_scaling), pady=(int(4 * self.current_scaling), 0))
            self.update_split_view()
        else:
            if self.split_view_frame:
                self.split_view_frame.pack_forget()
        
        # Recalculate window height
        self._update_window_height()

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

        # Clear old widgets
        for w in self.split_view_frame.winfo_children():
            w.destroy()

        splits = None
        if self.race_data_manager and hasattr(self.race_data_manager, 'get_splits'):
            splits = self.race_data_manager.get_splits()

        if not splits:
            lbl = tk.Label(self.split_view_frame, text="No splits configured", bg="#222f3e", fg="white")
            lbl.pack(padx=int(8 * self.current_scaling), pady=int(4 * self.current_scaling))
            return

        # Determine if we have live current race data (any non-zero entry)
        has_live = False
        try:
            for v in (self.race_data_manager.current_race_data.values() if hasattr(self.race_data_manager, 'current_race_data') else []):
                if v != "0000000":
                    has_live = True
                    break
        except Exception:
            has_live = False

        # Adjust size based on number of splits
        count = len(splits)
        font_size = max(8, int(10 * self.current_scaling))

        for s in splits:
            name = s.get('name', 'split')
            percent = s.get('percent', 0)

            # Get ghost time at this percent
            ghost_time = None
            if getattr(self.race_data_manager, 'split_times', None):
                ghost_time = self.race_data_manager.split_times.get(str(percent), "0000000")

            # If we don't have live data yet, show placeholders with names and percents
            if not has_live:
                row = tk.Frame(self.split_view_frame, bg="#222f3e")
                row.pack(fill='x', padx=int(8 * self.current_scaling), pady=(int(2 * self.current_scaling), int(2 * self.current_scaling)))
                name_lbl = tk.Label(row, text=name, bg="#222f3e", fg="white", anchor='w',width=10, font=("Helvetica", font_size))
                name_lbl.grid(row=0, column=0, sticky='w')
                # Placeholder delta
                delta_lbl = tk.Label(row, text="=0.00", bg="#222f3e", fg="#bdc3c7",width=5, anchor='e', font=("Helvetica", font_size))
                delta_lbl.grid(row=0, column=1, sticky='e')
                # Placeholder delta
                delta_lbl2 = tk.Label(row, text="=0.00", bg="#222f3e", fg="#bdc3c7",width=5, anchor='e', font=("Helvetica", font_size))
                delta_lbl2.grid(row=0, column=2, sticky='e')
                # Show percent on right
                pct_lbl = tk.Label(row, text=f"0.00", bg="#222f3e", fg="#bdc3c7",width=4, anchor='e', font=("Helvetica", font_size))
                pct_lbl.grid(row=0, column=3, sticky='e')
            else:
                current_time = self.race_data_manager.current_race_data.get(str(percent), "0000000") if hasattr(self.race_data_manager, 'current_race_data') else "0000000"
                # Compute delta if possible
                delta_display_pb = ""
                delta_display_bpt = ""
                try:
                    if current_time and ghost_time and current_time != "0000000" and ghost_time != "0000000":
                        delta_ms = int(current_time) - int(ghost_time)
                        delta_display_pb = self._format_delta_ms(delta_ms)
                        delta_display_bpt = self._format_delta_ms(delta_ms)
                except Exception:
                    delta_display_pb = ""
                    delta_display_bpt = ""

                row = tk.Frame(self.split_view_frame, bg="#222f3e")
                row.pack(fill='x', padx=int(8 * self.current_scaling), pady=(int(2 * self.current_scaling), int(2 * self.current_scaling)))
                name_lbl = tk.Label(row, text=name, bg="#222f3e", fg="white", anchor='w', width=20, font=("Helvetica", font_size))
                name_lbl.pack(side='left')
                delta_lbl_pb = tk.Label(row, text=delta_display_pb, bg="#222f3e", fg="#2ecc71" if delta_display_pb and delta_display_pb.startswith('-') else "#e74c3c", width=8, font=("Helvetica", font_size))
                delta_lbl_pb.pack(side='left')
                delta_lbl_bpt = tk.Label(row, text=delta_display_bpt, bg="#222f3e", fg="#2ecc71" if delta_display_bpt and delta_display_bpt.startswith('-') else "#e74c3c", width=8, font=("Helvetica", font_size))
                delta_lbl_bpt.pack(side='left')
                time_lbl = tk.Label(row, text=self._format_time_ms(ghost_time), bg="#222f3e", fg="#bdc3c7", anchor='e', width=12, font=("Helvetica", font_size))
                time_lbl.pack(side='right')
    
    def save_ghost_file(self):
        """Open file dialog to save current race data as ghost file."""
        if self.on_save_ghost:
            filetypes = [("JSON files", "*.json"), ("All files", "*.*")]
            filename = filedialog.asksaveasfilename(
                title="Save Current Ghost",
                filetypes=filetypes,
                defaultextension=".json",
                initialdir=os.getcwd()
            )
            if filename:
                self.on_save_ghost(filename)
    
    def update_ghost_filename(self, filename: str):
        """Update the displayed ghost filename."""
        if self.ghost_filename_label:
            if filename:
                display_name = filename
                # Ghost loaded - use white/light gray color
                self.ghost_filename_label.config(text=display_name, fg="#bdc3c7")
            else:
                display_name = "No ghost loaded"
                # No ghost - use red color
                self.ghost_filename_label.config(text=display_name, fg="#e74c3c")
    
    def show_ghost_saved_message(self):
        """Show temporary 'Ghost Saved!' message."""
        if self.ghost_filename_label:
            # Store current text and color
            original_text = self.ghost_filename_label.cget("text")
            original_color = self.ghost_filename_label.cget("fg")
            
            # Show "Ghost Saved!" message
            self.ghost_filename_label.config(text="Ghost Saved!", fg="#2ecc71", 
                                           font=("Helvetica", 9, "bold underline"))
            
            # Restore original text after 1 second
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
                # Enable button if race is complete
                self.save_ghost_button.config(state="normal", bg="#f39c12")
            else:
                # Disable button if race is not complete
                self.save_ghost_button.config(state="disabled", bg="#7f8c8d")
    
    def update_background_color(self, mode: str, delta: float = None):
        """Update UI background color based on race mode and delta."""
        if mode == "race" and delta is not None:
            if delta < 0:  # Ahead of ghost (negative means faster)
                bg_color = "#2d5a3d"  # Green - ahead
            elif delta > 0:  # Behind ghost (positive means slower)
                bg_color = "#5a2d2d"  # Red - behind
            else:  # Exactly even (delta == 0)
                bg_color = "#2d3a5a"  # Blue - even
        else:
            bg_color = "#2c3e50"  # Default dark blue
        
        # Only update if color actually changed to prevent UI stuttering
        if bg_color != self.current_bg_color:
            self.current_bg_color = bg_color
            # Update both the main display area and footer background
            if hasattr(self, 'main_display_frame') and self.main_display_frame:
                self.main_display_frame.configure(bg=bg_color)
            if hasattr(self, 'delta_label') and self.delta_label:
                self.delta_label.configure(bg=bg_color)
    
    def prompt_save_race(self):
        """Prompt user to save race data."""
        if self.on_save_race:
            # Create a simple dialog to get filename
            dialog = tk.Toplevel(self.root)
            dialog.title("Save Race Data")
            dialog.geometry("300x120")
            dialog.resizable(False, False)
            dialog.configure(bg="#34495e")
            
            # Center the dialog
            dialog.transient(self.root)
            dialog.grab_set()
            
            # Filename entry
            tk.Label(dialog, text="Race name:", bg="#34495e", fg="white").pack(pady=(int(10 * self.current_scaling), int(5 * self.current_scaling)))
            filename_var = tk.StringVar()
            entry = tk.Entry(dialog, textvariable=filename_var, width=30)
            entry.pack(pady=int(5 * self.current_scaling))
            entry.focus_set()
            
            # Buttons
            button_frame = tk.Frame(dialog, bg="#34495e")
            button_frame.pack(pady=int(10 * self.current_scaling))
            
            def save_and_close():
                filename = filename_var.get().strip()
                if filename:
                    dialog.destroy()
                    self.on_save_race(filename)
                else:
                    messagebox.showerror("Error", "Please enter a filename")
            
            def cancel_and_close():
                dialog.destroy()
            
            tk.Button(button_frame, text="Save", command=save_and_close, 
                     bg="#27ae60", fg="white", width=8).pack(side="left", padx=int(5 * self.current_scaling))
            tk.Button(button_frame, text="Cancel", command=cancel_and_close, 
                     bg="#e74c3c", fg="white", width=8).pack(side="left", padx=int(5 * self.current_scaling))
            
            # Enter key saves
            entry.bind('<Return>', lambda e: save_and_close())
    
    def close_app(self):
        """Close the application completely."""
        # Save UI configuration before closing
        self.save_ui_config()
        
        # Call the close callback to stop all threads in the main application
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
                # Handle cases where the window is already destroyed or main loop not running
                print(f"UI cleanup warning: {e}")
                pass
        # Exit the entire Python script
        sys.exit(0)
    
    def adjust_scaling(self, delta: float):
        """Adjust UI scaling in real-time by recreating the UI."""
        if not self.root:
            return

        old_scaling = self.current_scaling
        self.current_scaling += delta
        # Clamp scaling between 0.75 and 2.0
        self.current_scaling = max(0.75, min(2.0, self.current_scaling))
        
        # Calculate scaling ratio for window size adjustment
        scaling_ratio = self.current_scaling / old_scaling
        
        try:
            # Store current states
            was_race_expanded = self.race_panel_expanded
            was_debug_expanded = self.debug_expanded
            current_mode = self.get_current_mode() if self.mode_var else "record"
            # Store current window position and size
            current_geometry = self.root.geometry()
            parts = current_geometry.replace('x', '+').replace('+', ' ').split()
            if len(parts) >= 4:
                width, height, x, y = int(parts[0]), int(parts[1]), parts[2], parts[3]
            else:
                width, height, x, y = 300, 120, "100", "100"
            
            # Calculate new window size based on scaling ratio
            new_width = int(width * scaling_ratio)
            new_height = int(height * scaling_ratio)
            
            # Destroy current UI elements (but keep root window)
            for widget in self.root.winfo_children():
                widget.destroy()
            

            # Apply new scaling
            self.root.tk.call("tk", "scaling", self.current_scaling)
            
            # Set new window size (start with base size, will be adjusted by panel states)
            base_width = int(300 * self.current_scaling)
            base_height = int(120 * self.current_scaling)
            self.root.geometry(f"{base_width}x{base_height}")
            self.root.update()
            # Recreate the UI content
            self._recreate_ui_content()
            
            # Restore states (this will adjust window size for expanded panels)
            if self.mode_var:
                self.mode_var.set(current_mode)
                self.on_mode_changed()
            
            # Restore panel states
            if was_race_expanded and not self.race_panel_expanded:
                self.toggle_race_panel()
            if was_debug_expanded and not self.debug_expanded:
                self.toggle_debug()
            
            # Restore window position
            self.root.geometry(f"+{x}+{y}")
            
            # Recalculate window height to ensure all panels are properly sized
            self._update_window_height()
            
            print(f"Scaling adjusted to: {self.current_scaling:.2f}, Window size: {new_width}x{new_height}")
        except tk.TclError as e:
            print(f"Error adjusting scaling: {e}")
            pass
    
    def _recreate_ui_content(self):
        """Recreate the UI content after scaling change."""
        # Reset panel states
        self.race_panel_expanded = False
        self.debug_expanded = False
        
        # Calculate scaled dimensions
        base_width = int(300 * self.current_scaling)
        base_height = int(120 * self.current_scaling)
        
        # Set geometry with scaled size
        self.root.geometry(f"{base_width}x{base_height}")
        
        # Remove window decorations and make it borderless
        self.root.overrideredirect(True)
        
        # Create a hidden window for taskbar representation
        self.taskbar_window = tk.Toplevel(self.root)
        self.taskbar_window.title("ALU Timing Tool")
        self.taskbar_window.geometry("1x1+0+0")  # Minimal size
        self.taskbar_window.withdraw()  # Hide it but keep it in taskbar
        self.taskbar_window.iconify()  # Minimize to taskbar
        
        # Set up the window style
        self.root.configure(bg="#2c3e50")
        
        # Set pin state from config
        self.is_pinned = self.ui_config.get("is_pinned", True)
        if self.is_pinned:
            self.root.wm_attributes("-topmost", True)
        else:
            self.root.wm_attributes("-topmost", False)
        
        # Create main horizontal container
        main_container = tk.Frame(self.root, bg="#2c3e50")
        main_container.pack(fill="both", expand=False)
        
        # Main UI container (center)
        main_ui_frame = tk.Frame(main_container, bg="#2c3e50")
        main_ui_frame.pack(side="top", fill="both", expand=False)
        
        # Bind drag events to main frame for window movement
        main_ui_frame.bind("<Button-1>", self.start_drag)
        main_ui_frame.bind("<B1-Motion>", self.on_drag)
        
        # Main delta display (takes up almost entire UI)
        self.main_display_frame = tk.Frame(main_ui_frame, bg="#2c3e50")
        self.main_display_frame.pack(side='top',fill="both",anchor='n', expand=False)
        
        # Make delta frame draggable
        self.main_display_frame.bind("<Button-1>", self.start_drag)
        self.main_display_frame.bind("<B1-Motion>", self.on_drag)
        
        self.delta_label = tk.Label(self.main_display_frame, text=self.delta_time, 
                                    font=("Franklin Gothic Heavy", int(110), "bold"), fg="#ecf0f1", bg="#2c3e50")
        self.delta_label.pack(side='top',anchor='n',fill='x',expand=False)

        self.main_display_frame.config(height=int(120 * self.current_scaling))

        # Bind right click to open the race panel
        self.main_display_frame.bind('<Button-3>',self.toggle_race_panel)
        self.delta_label.bind('<Button-3>',self.toggle_race_panel)

        # Make delta label draggable
        self.delta_label.bind("<Button-1>", self.start_drag)
        self.delta_label.bind("<B1-Motion>", self.on_drag)
        
        # Race panel (initially hidden, packed into main_container below button panel)
        self.race_panel = tk.Frame(main_container, bg="#2c3e50")
        # Don't pack it initially
        
        # Create race panel content
        self._create_race_panel_content()
        
        self.main_display_frame.config(height=int(120 * self.current_scaling))
        self.root.update()
        # Rebind keyboard shortcuts
        self.root.bind_all("<Control-plus>", lambda e: self.increase_scaling())
        self.root.bind_all("<Control-equal>", lambda e: self.increase_scaling())
        self.root.bind_all("<Control-minus>", lambda e: self.decrease_scaling())
        self.root.bind_all("<Control-0>", lambda e: self.reset_scaling())
        self.root.focus_set()
    
    def increase_scaling(self):
        """Increase UI scaling by 0.05."""
        self.adjust_scaling(0.05)
    
    def decrease_scaling(self):
        """Decrease UI scaling by 0.05."""
        self.adjust_scaling(-0.05)
    
    def reset_scaling(self):
        """Reset scaling to 1.0."""
        if not self.root:
            return
        self.current_scaling = 1.0
        try:
            self.root.tk.call("tk", "scaling", self.current_scaling)
            print(f"Scaling reset to: {self.current_scaling:.2f}")
        except tk.TclError:
            pass
    
    def toggle_debug(self):
        """Toggle debug panel visibility within race panel."""
        if not self.race_panel_expanded:
            return  # Can't show debug if race panel is closed
            
        self.debug_expanded = not self.debug_expanded
        if self.debug_expanded:
            # Pack debug frame
            self.debug_frame.pack(side="top", fill="x", padx=int(0 * self.current_scaling), pady=(int(0 * self.current_scaling), int(0 * self.current_scaling)))
            # Hide the debug button when panel is open
            self.debug_button.pack_forget()
        else:
            # Unpack debug frame
            self.debug_frame.pack_forget()
            # Show the debug button again when panel is closed
            self.debug_button.pack(side="left", padx=int(5 * self.current_scaling), pady=(int(2 * self.current_scaling), int(0 * self.current_scaling)))
        
        # Recalculate window height
        self._update_window_height()
    
    def start_drag(self, event):
        """Start window drag."""
        self.start_x = event.x
        self.start_y = event.y
    
    def on_drag(self, event):
        """Handle window drag."""
        x = self.root.winfo_x() + (event.x - self.start_x)
        y = self.root.winfo_y() + (event.y - self.start_y)
        self.root.geometry(f"+{x}+{y}")
    
    def update_ui(self):
        """Update UI elements with current data."""
        if self.root is None:
            return
            
        try:
            # Update main display - show timer in record mode, delta in race mode
            current_mode = self.get_current_mode()
            if current_mode == "race":
                # Show delta when racing
                self.delta_label.config(text=self.delta_time)
            else:
                # Show placeholder when recording
                self.delta_label.config(text="=0.00")
            
            # Update debug info only if expanded
            if self.debug_expanded:
                self.time_label.config(text=f"Timer: {self.current_timer_display}")
                self.elapsed_label.config(text=f"Loop: {self.elapsed_ms:.1f}ms")
                self.avg_loop_label.config(text=f"Avg Loop: {self.avg_loop_time:.1f}ms")
                
                # Update percentage display
                if self.percentage and self.percentage != "0%":
                    self.percentage_label.config(text=f"Distance: {self.percentage}", fg="#2ecc71")
                else:
                    self.percentage_label.config(text="Distance: --", fg="#95a5a6")
                
                # Update debug timer display (shows actual in-game timer)
                self.debug_timer_label.config(text=f"Timer: {self.current_timer_display}")
                
                # Performance metrics
                self.inference_label.config(text=f"Inference: {self.current_inference_time:.1f}ms")
                self.avg_inference_label.config(text=f"Average: {self.avg_inference_time:.1f}ms")

            # Schedule next update at 11ms (90 FPS) for ultra-responsive UI
            self.root.after(11, self.update_ui)
        except tk.TclError:
            # Window was destroyed
            pass
            pass
    
    def create_ui(self):
        """Create the main UI window."""
        self.root = tk.Tk()
        
        # Fix for high DPI scaling issues (150% scaling on laptops)
        self.root.tk.call("tk", "scaling", self.current_scaling)
        
        # Bind keyboard shortcuts for scaling adjustment
        self.root.bind_all("<Control-plus>", lambda e: self.increase_scaling())
        self.root.bind_all("<Control-equal>", lambda e: self.increase_scaling())  # For keyboards without numpad
        self.root.bind_all("<Control-minus>", lambda e: self.decrease_scaling())
        self.root.bind_all("<Control-0>", lambda e: self.reset_scaling())
        
        # Focus the root window to ensure key bindings work
        self.root.focus_set()
        
        self.root.title("ALU Timing Tool")
        
        # Use saved position and size from config
        geometry = self.config_manager.get_window_geometry_from_config(self.ui_config)
        self.root.geometry(geometry)
        self.root.resizable(False, False)
        
        # Remove window decorations and make it borderless
        self.root.overrideredirect(True)
        
        # Create a hidden window for taskbar representation
        self.taskbar_window = tk.Toplevel(self.root)
        self.taskbar_window.title("ALU Timing Tool")
        self.taskbar_window.geometry("1x1+0+0")  # Minimal size
        self.taskbar_window.withdraw()  # Hide it but keep it in taskbar
        self.taskbar_window.iconify()  # Minimize to taskbar
        
        # Set up the window style
        self.root.configure(bg="#2c3e50")
        
        # Set pin state from config
        self.is_pinned = self.ui_config.get("is_pinned", True)
        if self.is_pinned:
            self.root.wm_attributes("-topmost", True)
        else:
            self.root.wm_attributes("-topmost", False)
        
        # Create main horizontal container
        main_container = tk.Frame(self.root, bg="#2c3e50")
        main_container.pack(fill="both", expand=False)
        
        # Main UI container (center)
        main_ui_frame = tk.Frame(main_container, bg="#2c3e50")
        main_ui_frame.pack(side="top", fill="both", expand=False)
        
        # Bind drag events to main frame for window movement
        main_ui_frame.bind("<Button-1>", self.start_drag)
        main_ui_frame.bind("<B1-Motion>", self.on_drag)
        
        # Main delta display (takes up almost entire UI)
        self.main_display_frame = tk.Frame(main_ui_frame, bg="#2c3e50")
        self.main_display_frame.pack(side='top',fill="both",anchor='n', expand=False)
        
        # Make delta frame draggable
        self.main_display_frame.bind("<Button-1>", self.start_drag)
        self.main_display_frame.bind("<B1-Motion>", self.on_drag)
        
        self.delta_label = tk.Label(self.main_display_frame, text=self.delta_time, 
                                    font=("Franklin Gothic Heavy", int(110), "bold"), fg="#ecf0f1", bg="#2c3e50")
        self.delta_label.pack(side='top',anchor='n',fill='x',expand=False)
        

        self.main_display_frame.config(height=int(120 * self.current_scaling))

        # Bind right click to open the race panel
        self.main_display_frame.bind('<Button-3>',self.toggle_race_panel)
        self.delta_label.bind('<Button-3>',self.toggle_race_panel)
        
        # Make delta label draggable
        self.delta_label.bind("<Button-1>", self.start_drag)
        self.delta_label.bind("<B1-Motion>", self.on_drag)
        
        
        # Race panel (initially hidden, packed into main_container below button panel)
        self.race_panel = tk.Frame(main_container, bg="#2c3e50")
        # Don't pack it initially
        
        # Create race panel content
        self._create_race_panel_content()
        
        # Start the UI update loop
        self.update_ui()
        
        # Make the window appear on top initially
        self.root.lift()
        self.root.focus_force()
        self.main_display_frame.config(height=int(120 * self.current_scaling))
        self.root.update()
        self.root.mainloop()
    
    def _create_race_panel_content(self):
        """Create the race panel content with 2-column layout."""
        if not self.race_panel:
            return

        # Main container with 2-column layout
        main_container = tk.Frame(self.race_panel, bg="#2c3e50",height=self.race_panel.winfo_height())
        main_container.pack(side='top',fill="both",anchor='n', expand=False, padx=int(15 * self.current_scaling), pady=int(0 * self.current_scaling))
        
        # Left column - Ghost and Mode controls
        left_column = tk.Frame(main_container, bg="#2c3e50")
        left_column.pack(side="left", fill="both", expand=True, padx=(int(0 * self.current_scaling), int(15 * self.current_scaling)))
        
        # Ghost section
        ghost_frame = tk.Frame(left_column, bg="#2c3e50")
        ghost_frame.pack(fill="x", pady=(int(0 * self.current_scaling), int(0 * self.current_scaling)))
        
        # Race Control indicator (bottom left, initially hidden) - bigger and white
        tk.Label(ghost_frame, text="Race Control", font=("Helvetica", 20, "bold"), fg="white", bg="#2c3e50").pack(anchor='w', pady=int(0 * self.current_scaling))
        tk.Label(ghost_frame, text="Ghost Name:", 
                font=("Helvetica", 10, "bold"), fg="#bdc3c7", bg="#2c3e50").pack(anchor="w")
        
        self.ghost_filename_label = tk.Label(ghost_frame, text="No ghost loaded", 
                                           font=("Helvetica", 9), fg="#e74c3c", bg="#2c3e50",
                                           wraplength=200, justify="left")
        self.ghost_filename_label.pack(anchor="w", pady=(int(2 * self.current_scaling), int(0 * self.current_scaling)))
        
        # Mode section (reduced bottom spacing)
        mode_frame = tk.Frame(left_column, bg="#2c3e50")
        mode_frame.pack(fill="x", pady=(int(0 * self.current_scaling), int(5 * self.current_scaling)))
        
        tk.Label(mode_frame, text="Mode:", 
                font=("Helvetica", 10, "bold"), fg="#bdc3c7", bg="#2c3e50").pack(anchor="w")
        
        self.mode_var = tk.StringVar(value="record")
        self.mode_combobox = ttk.Combobox(mode_frame, textvariable=self.mode_var, 
                         values=["record", "race", "splits"], state="readonly", width=18)
        self.mode_combobox.pack(anchor="w", pady=(int(2 * self.current_scaling), int(0 * self.current_scaling)))
        self.mode_combobox.bind('<<ComboboxSelected>>', self.on_mode_changed)
        
        
        # Toggle split view button (always visible, independent of race panel)
        self.toggle_split_view_button = tk.Button(left_column, text="Toggle Split View",
                     command=self.toggle_split_view,
                     bg="#7f8c8d", fg="white", font=("Helvetica", 9),
                     relief="flat", width=18, state="disabled")
        self.toggle_split_view_button.pack(anchor='w',pady=(int(0 * self.current_scaling), int(4 * self.current_scaling)))


        # Button container at bottom of left column - only for debug button
        #button_container = tk.Frame(left_column, bg="#2c3e50")
        #button_container.pack(fill="x", pady=(int(4 * self.current_scaling), int(0 * self.current_scaling)))
        
        # Debug button
        self.debug_button = tk.Button(left_column, text="Open Debug Panel", font=("Helvetica", 9),
                         bg="#3498db", fg="white", width=18,
                         command=self.toggle_debug,
                         relief="flat")
        self.debug_button.pack(anchor='w', pady=int(0 * self.current_scaling))




        # Right column - Action buttons and status
        right_column = tk.Frame(main_container, bg="#2c3e50")
        right_column.pack(side="right", fill="both", expand=True)
        
        # Close button (rightmost)
        self.close_button = tk.Button(right_column, text="Close Timing Tool", command=self.close_app, 
                      bg="#e74c3c", fg="white", font=("Helvetica", 9),
                      relief="flat", height=1)
        self.close_button.pack(pady=(int(0 * self.current_scaling), int(10 * self.current_scaling)))
        
        # Pin button (second from right)
        self.pin_button = tk.Button(right_column, text="Toggle Window Pin", command=self.toggle_pin, 
                      bg="#4ecdc4", fg="white", font=("Helvetica", 9),
                      relief="flat", height=1)
        self.pin_button.pack(pady=(int(0 * self.current_scaling), int(10 * self.current_scaling)))

        # Load ghost button
        self.load_ghost_button = tk.Button(right_column, text="Load Race Ghost", 
                          command=self.load_ghost_file,
                          bg="#7f8c8d", fg="white", font=("Helvetica", 9),
                          relief="flat", width=18, state="disabled")
        self.load_ghost_button.pack(pady=(int(0 * self.current_scaling), int(10 * self.current_scaling)))

        
        # Save ghost button (add this if it doesn't exist)
        if hasattr(self, 'save_ghost_file'):
            self.save_ghost_button = tk.Button(right_column, text="Save Current Ghost", 
                                              command=self.save_ghost_file,
                                              bg="#7f8c8d", fg="white", font=("Helvetica", 9),
                                              relief="flat", width=18, state="disabled")
            self.save_ghost_button.pack(pady=(int(0 * self.current_scaling), int(10 * self.current_scaling)))
        
        # Configure splits button (enabled only in 'splits' mode)
        self.configure_splits_button = tk.Button(right_column, text="Configure Splits",
                             command=self.open_configure_splits_dialog,
                             bg="#7f8c8d", fg="white", font=("Helvetica", 9),
                             relief="flat", width=18, state="disabled")
        self.configure_splits_button.pack(pady=(int(0 * self.current_scaling), int(4 * self.current_scaling)))

        
        # Debug panel (initially hidden, will be packed below when expanded)
        self.debug_frame = tk.Frame(self.race_panel, bg="#2c3e50",height=120*self.current_scaling)
        # Don't pack it initially
        
        # Create debug panel content
        self._create_debug_panel_content()
    
    def _create_debug_panel_content(self):
        """Create the debug panel content with 2-column layout."""
        if not self.debug_frame:
            return
        
        # Main container for 2-column layout (no padding for borderless look)
        main_container = tk.Frame(self.debug_frame, bg="#2c3e50")
        main_container.pack(fill="both", expand=True, padx=int(5 * self.current_scaling), pady=int(0 * self.current_scaling))
        
        # Title row with debug title and close button
        title_row = tk.Frame(main_container, bg="#2c3e50")
        title_row.pack(fill="x", pady=(int(0 * self.current_scaling), int(3 * self.current_scaling)))
        
        # Debug panel title (left side)
        debug_title = tk.Label(title_row, text="Debug Information", 
                                font=("Helvetica", 11, "bold"), fg="#ecf0f1", bg="#2c3e50")
        debug_title.pack(side="left", anchor="w")
        
        # Close button (right side) - create a new close button for inside debug panel
        self.debug_close_button = tk.Button(title_row, text="✕", font=("Helvetica", 8, "bold"),
                                           bg="#e74c3c", fg="white", width=3, height=1,
                                           command=self.toggle_debug,
                                           relief="flat", bd=1)
        self.debug_close_button.pack(side="right")
        
        # Create 2-column layout container
        info_container = tk.Frame(main_container, bg="#2c3e50")
        info_container.pack(fill="both", expand=True)
        
        # Left column - Performance metrics (reduced gap between columns)
        left_column = tk.Frame(info_container, bg="#2c3e50")
        left_column.pack(side="left", fill="both", expand=True, padx=(int(0 * self.current_scaling), int(10 * self.current_scaling)))
        
        # Performance section title (reduced spacing)
        perf_title = tk.Label(left_column, text="Performance Metrics", 
                     font=("Helvetica", 10, "bold"), fg="#bdc3c7", bg="#2c3e50")
        perf_title.pack(anchor="w", pady=(int(0 * self.current_scaling), int(3 * self.current_scaling)))
        
        # Loop timing
        self.elapsed_label = tk.Label(left_column, text=f"Loop: {self.elapsed_ms:.1f}ms", 
                                font=("Helvetica", 9), fg="#ecf0f1", bg="#2c3e50")
        self.elapsed_label.pack(anchor="w")
        
        # Average loop timing
        self.avg_loop_label = tk.Label(left_column, text="Avg Loop: --", 
                                 font=("Helvetica", 9), fg="#ecf0f1", bg="#2c3e50")
        self.avg_loop_label.pack(anchor="w")
        
        # Inference timing
        self.inference_label = tk.Label(left_column, text="Inference: --", 
                                  font=("Helvetica", 9), fg="#ecf0f1", bg="#2c3e50")
        self.inference_label.pack(anchor="w")
        
        # Average inference
        self.avg_inference_label = tk.Label(left_column, text="Avg Inference: --", 
                                      font=("Helvetica", 9), fg="#ecf0f1", bg="#2c3e50")
        self.avg_inference_label.pack(anchor="w")
        
        # Right column - Game state
        right_column = tk.Frame(info_container, bg="#2c3e50")
        right_column.pack(side="right", fill="both", expand=True)
        
        # Game state section title (reduced spacing)
        state_title = tk.Label(right_column, text="Game State", 
                      font=("Helvetica", 10, "bold"), fg="#bdc3c7", bg="#2c3e50")
        state_title.pack(anchor="w", pady=(int(0 * self.current_scaling), int(3 * self.current_scaling)))
        
        # Timer
        self.time_label = tk.Label(right_column, text=f"Timer: {self.current_timer_display}", 
                             font=("Helvetica", 9), fg="#ecf0f1", bg="#2c3e50")
        self.time_label.pack(anchor="w")
        
        # Distance percentage
        self.percentage_label = tk.Label(right_column, text="Distance: --", 
                                   font=("Helvetica", 9, "bold"), fg="#95a5a6", bg="#2c3e50")
        self.percentage_label.pack(anchor="w")
        
        # Race delta (monospace font to prevent layout jumps)
        self.debug_timer_label = tk.Label(right_column, text="Timer: 00:00.000", 
                                   font=("Courier", 9), fg="#95a5a6", bg="#2c3e50")
        self.debug_timer_label.pack(anchor="w")
    
    def start_ui_thread(self):
        """Start the UI in a separate thread."""
        ui_thread = threading.Thread(target=self.create_ui, daemon=True)
        ui_thread.start()
        return ui_thread
    
    def set_callbacks(self, on_mode_change=None, on_load_ghost=None, on_save_ghost=None, on_save_race=None, on_close=None, on_load_split=None, on_configure_splits=None):
        """Set callback functions for race functionality."""
        self.on_mode_change = on_mode_change
        self.on_load_ghost = on_load_ghost
        self.on_save_ghost = on_save_ghost
        self.on_save_race = on_save_race
        self.on_close = on_close
        # Optional split-related callbacks
        self.on_load_split = on_load_split
        self.on_configure_splits = on_configure_splits
    
    def update_timer(self, timer_display: str):
        """Update timer display."""
        self.current_timer_display = timer_display
    
    def update_delta(self, delta: str):
        """Update delta time display."""
        self.delta_time = delta
    
    def update_percentage(self, percentage: str):
        """Update percentage display."""
        self.percentage = percentage
    
    def update_loop_time(self, elapsed_ms: float, avg_loop_time: float):
        """Update loop timing metrics."""
        self.elapsed_ms = elapsed_ms
        self.avg_loop_time = avg_loop_time
    
    def update_inference_time(self, current_time: float, avg_time: float):
        """Update inference timing metrics."""
        self.current_inference_time = current_time
        self.avg_inference_time = avg_time
    
    def get_current_mode(self) -> str:
        """Get the current race mode."""
        if self.mode_var:
            return self.mode_var.get()
        return "record"
    
    def show_message(self, title: str, message: str, is_error: bool = False):
        """Show a message dialog."""
        if is_error:
            messagebox.showerror(title, message)
        else:
            messagebox.showinfo(title, message)
    
    def close(self):
        """Close the UI."""
        self.close_app()

#from race_data import RaceDataManager
#race_data_manager = RaceDataManager()
#ui = TimingToolUI(race_data_manager)
#ui.create_ui()
