"""
Main entry point for the ALU Timing Tool (pymem Backend).

This script initializes and runs the ALU Timing Tool application.
Game telemetry is read by directly hooking Asphalt 9 process memory
via DataExtractor — no Cheat Engine required.

Prerequisites:
  1. Asphalt 9 (Steam x64) running
  2. Run this script — it attaches to the process automatically
"""

import sys
import os
import signal
from src.timer_v5_pymem import ALUTimingTool


def _setup_exe_logging():
    """When running as a frozen PyInstaller exe (no console window), redirect
    stdout and stderr to runs/debug_log.txt next to the executable so all
    print() and error output is preserved for debugging.
    """
    if not getattr(sys, "frozen", False):
        return  # source run: console already captures output
    runs_dir = os.path.join(os.path.dirname(sys.executable), "runs")
    os.makedirs(runs_dir, exist_ok=True)
    log_path = os.path.join(runs_dir, "debug_log.txt")
    try:
        log_file = open(log_path, "w", encoding="utf-8", buffering=1)
        sys.stdout = log_file
        sys.stderr = log_file
    except Exception:
        pass  # if redirect fails, silently continue without logging


def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully."""
    print('\nShutting down ALU Timing Tool...')
    sys.exit(0)


def main():
    """Main function to run the ALU Timing Tool."""
    _setup_exe_logging()
    # Register signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        print("Initializing ALU Timing Tool (pymem Backend)...")
        print("=" * 50)

        app = ALUTimingTool()

        print("=" * 50)
        print("ALU Timing Tool initialized successfully! ")
        print("Reading game telemetry via direct process memory hooks.")
        print("Press Ctrl+C to stop the application.")
        print("=" * 50)
        
        # Run the main loop
        app.run_main_loop()
        
    except KeyboardInterrupt:
        print("\nReceived keyboard interrupt.")
    except Exception as e:
        print(f"Error running ALU Timing Tool: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if 'app' in locals():
            app.stop()
        print("ALU Timing Tool has been stopped.")


if __name__ == "__main__":
    main()