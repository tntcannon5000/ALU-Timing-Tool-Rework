"""
Frame Capture Module

This module provides a threaded frame capture system using dxcam to eliminate
game stutters by separating capture from processing.
"""

import threading
import queue
import time
import numpy as np
from typing import Optional
from .capture_config import FrameCaptureConfig


class FrameCaptureThread:
    """
    Dedicated thread for continuous frame capture using dxcam.
    Feeds captured frames into a queue for processing by the main thread.
    """
    
    def __init__(self, camera, max_queue_size: Optional[int] = None, target_fps: int = 90):
        """
        Initialize the frame capture thread.
        
        Args:
            camera: DXCam camera instance
            max_queue_size: Maximum number of frames to buffer in queue (auto-optimized if None)
            target_fps: Target FPS for optimization
        """
        self.camera = camera
        self.target_fps = target_fps
        
        # Auto-optimize queue size if not specified
        if max_queue_size is None:
            max_queue_size = FrameCaptureConfig.get_optimized_queue_size(target_fps)
        self.max_queue_size = min(max_queue_size, FrameCaptureConfig.MAX_QUEUE_SIZE)
        
        # Get optimized sleep time
        self.capture_sleep_time = FrameCaptureConfig.get_capture_sleep_time(target_fps)
        
        # Thread control
        self._thread = None
        self._running = False
        self._stop_event = threading.Event()
        
        # Frame queue - small size to minimize latency
        self._frame_queue = queue.Queue(maxsize=self.max_queue_size)
        
        # Statistics
        self.frames_captured = 0
        self.frames_dropped = 0
        self.capture_errors = 0
        self.last_capture_time = 0
        
        # Performance tracking
        self._capture_times = []
        self.avg_capture_time = 0.0
        
    def start(self):
        """Start the capture thread."""
        if self._running:
            return
            
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        print("Frame capture thread started")
        
    def stop(self):
        """Stop the capture thread."""
        if not self._running:
            return
            
        print("Stopping frame capture thread...")
        self._running = False
        self._stop_event.set()
        
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=FrameCaptureConfig.THREAD_JOIN_TIMEOUT)
            
        # Clear any remaining frames in queue
        self._clear_queue()
        print("Frame capture thread stopped")
        
    def get_latest_frame(self) -> Optional[np.ndarray]:
        """
        Get the most recent frame from the capture queue.
        This method is non-blocking and will return the latest available frame.
        
        Returns:
            Latest captured frame or None if no frame is available
        """
        latest_frame = None
        
        # Get all available frames, keeping only the latest
        try:
            while True:
                frame = self._frame_queue.get_nowait()
                if latest_frame is not None:
                    # We had a previous frame, so this one is newer - count the old one as processed
                    pass
                latest_frame = frame
        except queue.Empty:
            pass
            
        return latest_frame
        
    def get_frame_timeout(self, timeout: float = 0.1) -> Optional[np.ndarray]:
        """
        Get a frame with a timeout.
        
        Args:
            timeout: Maximum time to wait for a frame
            
        Returns:
            Captured frame or None if timeout occurred
        """
        try:
            return self._frame_queue.get(timeout=timeout)
        except queue.Empty:
            return None
            
    def _capture_loop(self):
        """Main capture loop running in separate thread."""
        print("Frame capture loop started")
        
        while not self._stop_event.is_set():
            try:
                # Capture frame with timing
                capture_start = time.perf_counter()
                frame = self.camera.get_latest_frame()
                capture_end = time.perf_counter()
                
                if frame is not None:
                    # Update timing statistics
                    capture_time = (capture_end - capture_start) * 1000  # Convert to ms
                    self._update_capture_timing(capture_time)
                    
                    # Try to put frame in queue
                    try:
                        # Use put_nowait to avoid blocking
                        self._frame_queue.put_nowait(frame)
                        self.frames_captured += 1
                        self.last_capture_time = time.time()
                        
                    except queue.Full:
                        # Queue is full - drop oldest frame and add new one
                        try:
                            self._frame_queue.get_nowait()  # Remove oldest
                            self._frame_queue.put_nowait(frame)  # Add new
                            self.frames_dropped += 1
                            self.frames_captured += 1
                            self.last_capture_time = time.time()
                        except queue.Empty:
                            # Race condition - queue became empty, just add new frame
                            try:
                                self._frame_queue.put_nowait(frame)
                                self.frames_captured += 1
                                self.last_capture_time = time.time()
                            except queue.Full:
                                # Still full somehow, drop this frame
                                self.frames_dropped += 1
                else:
                    self.capture_errors += 1
                    
            except Exception as e:
                print(f"Error in capture loop: {e}")
                self.capture_errors += 1
                
            # Small sleep to prevent excessive CPU usage (only if configured)
            # For gaming mode, no sleep to maximize responsiveness
            if self.capture_sleep_time > 0:
                time.sleep(self.capture_sleep_time)
            # For zero sleep time, yield CPU briefly to prevent complete thread starvation
            elif self.capture_sleep_time == 0:
                time.sleep(0.0001)  # Minimal 0.1ms yield for thread cooperation
            
        print("Frame capture loop ended")
        
    def _update_capture_timing(self, capture_time: float):
        """Update capture timing statistics."""
        self._capture_times.append(capture_time)
        
        # Keep only last N measurements for rolling average
        if len(self._capture_times) > FrameCaptureConfig.STATS_WINDOW_SIZE:
            self._capture_times.pop(0)
            
        self.avg_capture_time = sum(self._capture_times) / len(self._capture_times)
        
    def _clear_queue(self):
        """Clear all frames from the queue."""
        try:
            while True:
                self._frame_queue.get_nowait()
        except queue.Empty:
            pass
            
    def get_stats(self) -> dict:
        """
        Get capture thread statistics.
        
        Returns:
            Dictionary with capture statistics
        """
        return {
            'running': self._running,
            'frames_captured': self.frames_captured,
            'frames_dropped': self.frames_dropped,
            'capture_errors': self.capture_errors,
            'queue_size': self._frame_queue.qsize(),
            'max_queue_size': self.max_queue_size,
            'avg_capture_time': self.avg_capture_time,
            'last_capture_time': self.last_capture_time,
            'drop_rate': (self.frames_dropped / max(self.frames_captured, 1)) * 100
        }
        
    def is_running(self) -> bool:
        """Check if capture thread is running."""
        return self._running and self._thread and self._thread.is_alive()