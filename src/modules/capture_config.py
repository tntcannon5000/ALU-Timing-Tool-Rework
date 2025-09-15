"""
Frame Capture Configuration

This module provides configuration options for the threaded frame capture system.
"""

class FrameCaptureConfig:
    """Configuration settings for frame capture optimized for ultra-low latency realtime gaming."""
    
    # Queue settings - ULTRA LOW LATENCY for realtime gaming
    DEFAULT_QUEUE_SIZE = 1  # Minimal queue for absolute lowest latency
    MAX_QUEUE_SIZE = 2     # Absolute maximum - never buffer more than 2 frames
    
    # Timing settings - OPTIMIZED FOR GAMING PERFORMANCE
    CAPTURE_SLEEP_MS = 0    # NO sleep in capture loop for maximum responsiveness
    FRAME_TIMEOUT_MS = 1    # Very short timeout - don't wait for frames
    
    # Performance settings
    STATS_WINDOW_SIZE = 30  # Smaller window for faster stats calculation
    
    # Thread settings
    THREAD_JOIN_TIMEOUT = 1.0  # Faster shutdown
    
    @classmethod
    def get_optimized_queue_size(cls, target_fps: int) -> int:
        """
        Get optimized queue size for ultra-low latency gaming.
        
        Args:
            target_fps: Target frames per second
            
        Returns:
            Recommended queue size (always minimal for gaming)
        """
        # For realtime gaming, always use minimal queue regardless of FPS
        return 1  # Always 1 frame queue for absolute minimum latency
    
    @classmethod
    def get_capture_sleep_time(cls, target_fps: int) -> float:
        """
        Get optimized capture sleep time for gaming performance.
        
        Args:
            target_fps: Target frames per second
            
        Returns:
            Sleep time in seconds (always 0 for gaming)
        """
        # For realtime gaming, never sleep in capture thread
        return 0.0  # Maximum responsiveness