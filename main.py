"""
Main entry point for the ALU Timing Tool (CE Backend).

This script initializes and runs the ALU Timing Tool application,
receiving game telemetry from Cheat Engine via a shared temp file.

Prerequisites:
  1. ALU_Trainer_v2.CT open in Cheat Engine (auto-attaches to Asphalt 9)
     OR: ALU_Trainer_v2.exe trainer running
"""

import sys
import signal
from timer_v5_pymem import ALUTimingTool


def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully."""
    print('\nShutting down ALU Timing Tool...')
    sys.exit(0)


def main():
    """Main function to run the ALU Timing Tool."""
    # Register signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        print("Initializing ALU Timing Tool (CE Backend)...")
        print("=" * 50)
        
        # Initialize the application — reads CE bridge file
        app = ALUTimingTool()
        
        print("=" * 50)
        print("ALU Timing Tool initialized successfully!")
        print("Reading game telemetry from CE bridge file.")
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
