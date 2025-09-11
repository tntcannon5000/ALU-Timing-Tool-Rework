#!/usr/bin/env python3
"""
Test script for the new UI design.
"""

import time
from src.modules.ui import TimingToolUI


def main():
    """Test the new UI."""
    print("Testing new UI design...")
    print("Features to test:")
    print("1. Close button (✕) should be in top-right corner with no gap")
    print("2. Pin button (📌) should be in bottom-right corner")
    print("3. Debug button (+) should be in bottom-left corner")
    print("4. Delta text should be large and prominent")
    print("5. Pin button should show 🚫 when unpinned")
    print("6. Debug panel should expand without progress bar")
    
    # Create UI instance
    ui = TimingToolUI()
    
    # Start UI in thread
    ui_thread = ui.start_ui_thread()
    
    # Simulate some data updates
    try:
        counter = 0
        while True:
            # Update delta with some test values
            if counter % 4 == 0:
                ui.update_delta("+1.234")
            elif counter % 4 == 1:
                ui.update_delta("-0.567")
            elif counter % 4 == 2:
                ui.update_delta("+12.345")
            else:
                ui.update_delta("-99.999")
            
            # Update some debug info
            ui.update_timer(f"{12 + counter % 10}:{34 + counter % 60}.{567 + counter % 1000:03d}")
            ui.update_percentage(f"{75 + counter % 25}%")
            ui.update_loop_time(15.5 + counter % 10, 14.2 + counter % 5)
            ui.update_inference_time(8.3 + counter % 5, 7.9 + counter % 3)
            
            counter += 1
            time.sleep(1.5)  # Update every 1.5 seconds for testing
            
    except KeyboardInterrupt:
        print("Stopping UI test...")
    finally:
        ui.close()
        

if __name__ == "__main__":
    main()