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
import signal
from src.timer_v5_pymem import ALUTimingTool


def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully."""
    print('\nShutting down ALU Timing Tool...')
    sys.exit(0)


def main():
    """Main function to run the ALU Timing Tool."""
    # Register signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        print("Initializing ALU Timing Tool (pymem Backend)...")
        print("=" * 50)

        app = ALUTimingTool()

        print("=" * 50)
        print("ALU Timing Tool initialized successfully!")
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
