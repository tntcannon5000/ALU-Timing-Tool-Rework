"""
User Interface Module

This module handles the GUI for the ALU Timing Tool.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import sys
import os
from ..utils.ui_config import UIConfigManager


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
        
        # Data to display
        self.current_timer_display = "00:00.000"
        self.elapsed_ms = 0
        self.avg_loop_time = 0
        self.percentage = "0%"
        self.avg_inference_time = 0
        self.current_inference_time = 0
        self.delta_time = "+00.000"  # Default delta time
        
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
                # Get current window geometry
                geometry = self.root.geometry()
                geometry_info = self.config_manager.extract_geometry_from_string(geometry)
                
                # Update configuration
                config = {
                    "window_position": geometry_info["window_position"],
                    "window_size": geometry_info["window_size"],
                    "scaling": self.current_scaling,
                    "is_pinned": self.is_pinned,
                    "panels": {
                        "race_panel_expanded": self.race_panel_expanded,
                        "debug_panel_expanded": self.debug_expanded
                    }
                }
                
                # Save to file
                success = self.config_manager.save_config(config)
                if success:
                    print("UI configuration saved successfully")
                else:
                    print("Failed to save UI configuration")
        except Exception as e:
            print(f"Error saving UI configuration: {e}")
    
    def toggle_pin(self):
        """Toggle window pin state."""
        self.is_pinned = not self.is_pinned
        if self.is_pinned:
            self.root.wm_attributes("-topmost", True)
            self.pin_button.config(text="📌", bg="#4ecdc4")
        else:
            self.root.wm_attributes("-topmost", False)
            self.pin_button.config(text="📍", bg="#95a5a6")
    
    def toggle_race_panel(self):
        """Toggle race panel visibility."""
        self.race_panel_expanded = not self.race_panel_expanded
        if self.race_panel_expanded:
            self.race_panel.pack(side="bottom", fill="x", padx=0, pady=0)
            self.race_button.config(text="^", bg="#e67e22")
            # Show race control indicator in button section (left side)
            self.race_control_indicator.pack(side="left", padx=10, pady=5)
            # Ensure debug button is visible when race panel opens (unless debug is expanded)
            if hasattr(self, 'debug_button') and self.debug_button and not self.debug_expanded:
                self.debug_button.pack(side="right", padx=5, pady=2)
            # Fixed height for race panel (taller than before) - scaled
            panel_height = int(180 * self.current_scaling) if not self.debug_expanded else int(320 * self.current_scaling)
            # Expand window height to accommodate race panel
            current_geometry = self.root.geometry()
            parts = current_geometry.replace('x', '+').replace('+', ' ').split()
            width, height, x, y = parts[0], parts[1], parts[2], parts[3]
            new_height = int(height) + panel_height
            self.root.geometry(f"{width}x{new_height}+{x}+{y}")
        else:
            # Hide race control indicator
            self.race_control_indicator.pack_forget()
            # Calculate height based on debug panel state - scaled
            panel_height = int(180 * self.current_scaling) if not self.debug_expanded else int(320 * self.current_scaling)
            self.race_panel.pack_forget()
            self.race_button.config(text="v", bg="#e67e22")
            # Collapse window height
            current_geometry = self.root.geometry()
            parts = current_geometry.replace('x', '+').replace('+', ' ').split()
            width, height, x, y = parts[0], parts[1], parts[2], parts[3]
            new_height = int(height) - panel_height
            self.root.geometry(f"{width}x{new_height}+{x}+{y}")
            # Also collapse debug if race panel is closed
            if self.debug_expanded:
                # Manually close debug panel (can't use toggle_debug since race panel is closing)
                self.debug_frame.pack_forget()
                self.debug_expanded = False
                # Adjust height calculation to account for debug panel being closed
                panel_height += int(140 * self.current_scaling)  # Add debug panel height to total reduction
            
            # Ensure debug button is visible for next time race panel opens
            if hasattr(self, 'debug_button') and self.debug_button:
                self.debug_button.pack_forget()  # Remove it first
                # It will be re-packed when race panel opens again
    
    def on_mode_changed(self, event=None):
        """Handle mode change."""
        mode = self.mode_var.get()
        
        # Enable/disable load ghost button based on mode
        if mode == "record":
            self.load_ghost_button.config(state="disabled", bg="#7f8c8d")
        else:  # race mode
            self.load_ghost_button.config(state="normal", bg="#3498db")
        
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
            if hasattr(self, 'button_section') and self.button_section:
                self.button_section.configure(bg=bg_color)
            if hasattr(self, 'race_control_indicator') and self.race_control_indicator:
                self.race_control_indicator.configure(bg=bg_color)
    
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
            tk.Label(dialog, text="Race name:", bg="#34495e", fg="white").pack(pady=(10, 5))
            filename_var = tk.StringVar()
            entry = tk.Entry(dialog, textvariable=filename_var, width=30)
            entry.pack(pady=5)
            entry.focus_set()
            
            # Buttons
            button_frame = tk.Frame(dialog, bg="#34495e")
            button_frame.pack(pady=10)
            
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
                     bg="#27ae60", fg="white", width=8).pack(side="left", padx=5)
            tk.Button(button_frame, text="Cancel", command=cancel_and_close, 
                     bg="#e74c3c", fg="white", width=8).pack(side="left", padx=5)
            
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
        # Clamp scaling between 0.5 and 2.0
        self.current_scaling = max(0.5, min(2.0, self.current_scaling))
        
        # Calculate scaling ratio for window size adjustment
        scaling_ratio = self.current_scaling / old_scaling
        
        try:
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
            
            # Store current states
            was_race_expanded = self.race_panel_expanded
            was_debug_expanded = self.debug_expanded
            current_mode = self.get_current_mode() if self.mode_var else "record"
            
            # Destroy current UI elements (but keep root window)
            for widget in self.root.winfo_children():
                widget.destroy()
            
            # Apply new scaling
            self.root.tk.call("tk", "scaling", self.current_scaling)
            
            # Set new window size (start with base size, will be adjusted by panel states)
            base_width = int(300 * self.current_scaling)
            base_height = int(120 * self.current_scaling)
            self.root.geometry(f"{base_width}x{base_height}")
            
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
        button_height = int(30 * self.current_scaling)
        
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
        main_container.pack(fill="both", expand=True)
        
        # Main UI container (center)
        main_ui_frame = tk.Frame(main_container, bg="#2c3e50")
        main_ui_frame.pack(side="left", fill="both", expand=True)
        
        # Bind drag events to main frame for window movement
        main_ui_frame.bind("<Button-1>", self.start_drag)
        main_ui_frame.bind("<B1-Motion>", self.on_drag)
        
        # Main delta display (takes up almost entire UI)
        self.main_display_frame = tk.Frame(main_ui_frame, bg="#2c3e50")
        self.main_display_frame.pack(fill="both", expand=True)
        
        # Make delta frame draggable
        self.main_display_frame.bind("<Button-1>", self.start_drag)
        self.main_display_frame.bind("<B1-Motion>", self.on_drag)
        
        self.delta_label = tk.Label(self.main_display_frame, text=self.delta_time, 
                             font=("Helvetica", 55, "bold"), fg="#ecf0f1", bg="#2c3e50")
        self.delta_label.pack(expand=True, fill="both")
        
        # Make delta label draggable
        self.delta_label.bind("<Button-1>", self.start_drag)
        self.delta_label.bind("<B1-Motion>", self.on_drag)
        
        # Bottom button section (compact)
        button_section = tk.Frame(main_ui_frame, bg="#2c3e50", height=30)
        button_section.pack(fill="x", side="bottom")
        button_section.pack_propagate(False)
        
        # Store reference for background color updates
        self.button_section = button_section
        
        # Make button section draggable
        button_section.bind("<Button-1>", self.start_drag)
        button_section.bind("<B1-Motion>", self.on_drag)
        
        # Race Control indicator (bottom left, initially hidden) - bigger and white
        self.race_control_indicator = tk.Label(button_section, text="Race Control", 
                                              font=("Helvetica", 10, "bold"), fg="white", bg="#2c3e50")
        # Don't pack it initially
        
        # Close button (rightmost)
        self.close_button = tk.Button(button_section, text="✕", command=self.close_app, 
                              bg="#e74c3c", fg="white", font=("Helvetica", 8, "bold"),
                              relief="flat", width=3, height=1)
        self.close_button.pack(side="right", padx=2, pady=2)
        
        # Pin button (second from right)
        self.pin_button = tk.Button(button_section, text="📌", command=self.toggle_pin, 
                              bg="#4ecdc4", fg="white", font=("Helvetica", 8, "bold"),
                              relief="flat", width=3, height=1)
        self.pin_button.pack(side="right", padx=2, pady=2)
        
        # Race panel toggle button (third from right)
        self.race_button = tk.Button(button_section, text="v", command=self.toggle_race_panel, 
                              bg="#e67e22", fg="white", font=("Helvetica", 8, "bold"),
                              relief="flat", width=3, height=1)
        self.race_button.pack(side="right", padx=2, pady=2)
        
        # Race panel (initially hidden, below main UI)
        self.race_panel = tk.Frame(self.root, bg="#2c3e50", height=150)
        # Don't pack it initially
        
        # Create race panel content
        self._create_race_panel_content()
        
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
            self.debug_frame.pack(side="bottom", fill="x", padx=0, pady=(0, 0))
            # Hide the debug button when panel is open
            self.debug_button.pack_forget()
            # Expand window height for debug section (fixed height) - scaled
            current_geometry = self.root.geometry()
            parts = current_geometry.replace('x', '+').replace('+', ' ').split()
            width, height, x, y = parts[0], parts[1], parts[2], parts[3]
            new_height = int(height) + int(140 * self.current_scaling)  # Add scaled debug section height
            self.root.geometry(f"{width}x{new_height}+{x}+{y}")
        else:
            self.debug_frame.pack_forget()
            # Show the debug button again when panel is closed
            self.debug_button.pack(side="right", padx=5, pady=2)
            # Collapse window height - scaled
            current_geometry = self.root.geometry()
            parts = current_geometry.replace('x', '+').replace('+', ' ').split()
            width, height, x, y = parts[0], parts[1], parts[2], parts[3]
            new_height = int(height) - int(140 * self.current_scaling)  # Remove scaled debug section height
            self.root.geometry(f"{width}x{new_height}+{x}+{y}")
    
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
                self.delta_label.config(text="--.---")
            
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
        main_container.pack(fill="both", expand=True)
        
        # Main UI container (center)
        main_ui_frame = tk.Frame(main_container, bg="#2c3e50")
        main_ui_frame.pack(side="left", fill="both", expand=True)
        
        # Bind drag events to main frame for window movement
        main_ui_frame.bind("<Button-1>", self.start_drag)
        main_ui_frame.bind("<B1-Motion>", self.on_drag)
        
        # Main delta display (takes up almost entire UI)
        self.main_display_frame = tk.Frame(main_ui_frame, bg="#2c3e50")
        self.main_display_frame.pack(fill="both", expand=True)
        
        # Make delta frame draggable
        self.main_display_frame.bind("<Button-1>", self.start_drag)
        self.main_display_frame.bind("<B1-Motion>", self.on_drag)
        
        self.delta_label = tk.Label(self.main_display_frame, text=self.delta_time, 
                             font=("Helvetica", 55, "bold"), fg="#ecf0f1", bg="#2c3e50")
        self.delta_label.pack(expand=True, fill="both")
        
        # Make delta label draggable
        self.delta_label.bind("<Button-1>", self.start_drag)
        self.delta_label.bind("<B1-Motion>", self.on_drag)
        
        # Bottom button section (compact)
        button_section = tk.Frame(main_ui_frame, bg="#2c3e50", height=30)
        button_section.pack(fill="x", side="bottom")
        button_section.pack_propagate(False)
        
        # Store reference for background color updates
        self.button_section = button_section
        
        # Make button section draggable
        button_section.bind("<Button-1>", self.start_drag)
        button_section.bind("<B1-Motion>", self.on_drag)
        
        # Race Control indicator (bottom left, initially hidden) - bigger and white
        self.race_control_indicator = tk.Label(button_section, text="Race Control", 
                                              font=("Helvetica", 10, "bold"), fg="white", bg="#2c3e50")
        # Don't pack it initially
        
        # Close button (rightmost)
        self.close_button = tk.Button(button_section, text="✕", command=self.close_app, 
                              bg="#e74c3c", fg="white", font=("Helvetica", 8, "bold"),
                              relief="flat", width=3, height=1)
        self.close_button.pack(side="right", padx=2, pady=2)
        
        # Pin button (second from right)
        self.pin_button = tk.Button(button_section, text="📌", command=self.toggle_pin, 
                              bg="#4ecdc4", fg="white", font=("Helvetica", 8, "bold"),
                              relief="flat", width=3, height=1)
        self.pin_button.pack(side="right", padx=2, pady=2)
        
        # Race panel toggle button (third from right)
        self.race_button = tk.Button(button_section, text="v", command=self.toggle_race_panel, 
                              bg="#e67e22", fg="white", font=("Helvetica", 8, "bold"),
                              relief="flat", width=3, height=1)
        self.race_button.pack(side="right", padx=2, pady=2)
        
        # Race panel (initially hidden, below main UI)
        self.race_panel = tk.Frame(self.root, bg="#2c3e50", height=150)
        # Don't pack it initially
        
        # Create race panel content
        self._create_race_panel_content()
        
        # Restore panel states from config
        self._restore_panel_states_from_config()
        
        # Start the UI update loop
        self.update_ui()
        
        # Make the window appear on top initially
        self.root.lift()
        self.root.focus_force()
        
        self.root.mainloop()
    
    def _restore_panel_states_from_config(self):
        """Restore panel states from saved configuration."""
        try:
            panels_config = self.ui_config.get("panels", {})
            
            # Restore race panel state
            saved_race_panel_expanded = panels_config.get("race_panel_expanded", False)
            if saved_race_panel_expanded and not self.race_panel_expanded:
                self.toggle_race_panel()
            
            # Restore debug panel state (only if race panel is expanded)
            saved_debug_panel_expanded = panels_config.get("debug_panel_expanded", False)
            if saved_debug_panel_expanded and self.race_panel_expanded and not self.debug_expanded:
                self.toggle_debug()
                
        except Exception as e:
            print(f"Error restoring panel states: {e}")
    
    def _create_race_panel_content(self):
        """Create the race panel content with 2-column layout."""
        if not self.race_panel:
            return
        
        # Main container with 2-column layout
        main_container = tk.Frame(self.race_panel, bg="#2c3e50")
        main_container.pack(fill="both", expand=True, padx=15, pady=15)
        
        # Left column - Ghost and Mode controls
        left_column = tk.Frame(main_container, bg="#2c3e50")
        left_column.pack(side="left", fill="both", expand=True, padx=(0, 15))
        
        # Ghost section
        ghost_frame = tk.Frame(left_column, bg="#2c3e50")
        ghost_frame.pack(fill="x", pady=(0, 15))
        
        tk.Label(ghost_frame, text="Ghost Name:", 
                font=("Helvetica", 10, "bold"), fg="#bdc3c7", bg="#2c3e50").pack(anchor="w")
        
        self.ghost_filename_label = tk.Label(ghost_frame, text="No ghost loaded", 
                                           font=("Helvetica", 9), fg="#e74c3c", bg="#2c3e50",
                                           wraplength=200, justify="left")
        self.ghost_filename_label.pack(anchor="w", pady=(2, 0))
        
        # Mode section (reduced bottom spacing)
        mode_frame = tk.Frame(left_column, bg="#2c3e50")
        mode_frame.pack(fill="x", pady=(0, 5))
        
        tk.Label(mode_frame, text="Mode:", 
                font=("Helvetica", 10, "bold"), fg="#bdc3c7", bg="#2c3e50").pack(anchor="w")
        
        self.mode_var = tk.StringVar(value="record")
        self.mode_combobox = ttk.Combobox(mode_frame, textvariable=self.mode_var, 
                                         values=["record", "race"], state="readonly", width=18)
        self.mode_combobox.pack(anchor="w", pady=(2, 0))
        self.mode_combobox.bind('<<ComboboxSelected>>', self.on_mode_changed)
        
        # Right column - Action buttons and status
        right_column = tk.Frame(main_container, bg="#2c3e50")
        right_column.pack(side="right", fill="both", expand=True)
        
        # Load ghost button
        self.load_ghost_button = tk.Button(right_column, text="Load Race Ghost", 
                                          command=self.load_ghost_file,
                                          bg="#7f8c8d", fg="white", font=("Helvetica", 9),
                                          relief="flat", width=18, state="disabled")
        self.load_ghost_button.pack(pady=(0, 10))
        
        # Save ghost button (add this if it doesn't exist)
        if hasattr(self, 'save_ghost_file'):
            self.save_ghost_button = tk.Button(right_column, text="Save Current Ghost", 
                                              command=self.save_ghost_file,
                                              bg="#7f8c8d", fg="white", font=("Helvetica", 9),
                                              relief="flat", width=18, state="disabled")
            self.save_ghost_button.pack(pady=(0, 10))
        
        # Status indicator with debug button
        status_frame = tk.Frame(right_column, bg="#2c3e50")
        status_frame.pack(fill="x", pady=(10, 0))
        
        # Debug button in bottom right instead of status text
        self.debug_button = tk.Button(status_frame, text="🐛", font=("Helvetica", 8, "bold"),
                                     bg="#3498db", fg="white", width=3, height=1,
                                     command=self.toggle_debug,
                                     relief="flat", bd=1)
        self.debug_button.pack(side="right", padx=5, pady=2)
        
        # Debug panel (initially hidden, will be packed below when expanded)
        self.debug_frame = tk.Frame(self.race_panel, bg="#2c3e50")
        # Don't pack it initially
        
        # Create debug panel content
        self._create_debug_panel_content()
    
    def _create_debug_panel_content(self):
        """Create the debug panel content with 2-column layout."""
        if not self.debug_frame:
            return
        
        # Main container for 2-column layout (no padding for borderless look)
        main_container = tk.Frame(self.debug_frame, bg="#2c3e50")
        main_container.pack(fill="both", expand=True, padx=5, pady=3)
        
        # Title row with debug title and close button
        title_row = tk.Frame(main_container, bg="#2c3e50")
        title_row.pack(fill="x", pady=(0, 3))
        
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
        left_column.pack(side="left", fill="both", expand=True, padx=(0, 10))
        
        # Performance section title (reduced spacing)
        perf_title = tk.Label(left_column, text="Performance Metrics", 
                             font=("Helvetica", 10, "bold"), fg="#bdc3c7", bg="#2c3e50")
        perf_title.pack(anchor="w", pady=(0, 3))
        
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
        state_title.pack(anchor="w", pady=(0, 3))
        
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
    
    def set_callbacks(self, on_mode_change=None, on_load_ghost=None, on_save_ghost=None, on_save_race=None, on_close=None):
        """Set callback functions for race functionality."""
        self.on_mode_change = on_mode_change
        self.on_load_ghost = on_load_ghost
        self.on_save_ghost = on_save_ghost
        self.on_save_race = on_save_race
        self.on_close = on_close
    
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
