"""
Main entry point for the ALU Timing Tool.

This script initializes and runs the ALU Timing Tool application.
"""

import sys
import signal
from timer_optimize_py_v4 import ALUTimingTool


def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully."""
    print('\nShutting down ALU Timing Tool...')
    sys.exit(0)


def main():
    """Main function to run the ALU Timing Tool."""
    # Register signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        print("Initializing ALU Timing Tool...")
        print("=" * 50)
        
        # Initialize the application
        app = ALUTimingTool(
            window_name="asphalt",  # Change this to match your game window
            confidence_threshold=0.65
        )
        
        print("=" * 50)
        print("ALU Timing Tool initialized successfully!")
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
