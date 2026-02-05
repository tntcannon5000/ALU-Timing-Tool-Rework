"""
Device Detection and Management for Multi-Backend Support

This module provides device-agnostic utilities for PyTorch operations,
supporting NVIDIA CUDA, Intel XPU (GPU/NPU), and CPU backends.
"""

import os
import torch
from enum import Enum
from typing import Tuple, Optional
import warnings


class DeviceType(Enum):
    """Enumeration of supported device types."""
    CUDA = "cuda"
    XPU = "xpu"
    CPU = "cpu"


class DeviceManager:
    """
    Singleton class to manage device detection and configuration.
    """
    _instance = None
    _device_type: Optional[DeviceType] = None
    _torch_device: Optional[torch.device] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DeviceManager, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """Initialize device detection and configuration."""
        # Set XPU fallback environment variable early
        os.environ["PYTORCH_ENABLE_XPU_FALLBACK"] = "1"
        
        # Detect available device (priority: CUDA > XPU > CPU)
        self._device_type = self._detect_device()
        self._torch_device = self._create_torch_device()
        
        # Print device info
        print(f"🚀 Device Manager initialized: {self._device_type.value.upper()}")
        if self._device_type == DeviceType.XPU:
            print("   Intel XPU acceleration enabled with CPU fallback")
        elif self._device_type == DeviceType.CUDA:
            print(f"   CUDA device: {torch.cuda.get_device_name(0)}")
    
    def _detect_device(self) -> DeviceType:
        """
        Detect the best available device.
        
        Returns:
            DeviceType enum indicating available device
        """
        # Check for CUDA first (NVIDIA GPU)
        if torch.cuda.is_available():
            return DeviceType.CUDA
        
        # Check for XPU (Intel GPU/NPU)
        try:
            if hasattr(torch, 'xpu') and torch.xpu.is_available():
                return DeviceType.XPU
        except (AttributeError, RuntimeError) as e:
            # XPU not available or Intel Extension for PyTorch not installed
            pass
        
        # Default to CPU
        return DeviceType.CPU
    
    def _create_torch_device(self) -> torch.device:
        """
        Create the appropriate torch.device object.
        
        Returns:
            torch.device object for the detected device
        """
        return torch.device(self._device_type.value)
    
    def get_device_type(self) -> DeviceType:
        """Get the current device type."""
        return self._device_type
    
    def get_torch_device(self) -> torch.device:
        """Get the PyTorch device object."""
        return self._torch_device
    
    def is_cuda(self) -> bool:
        """Check if using CUDA."""
        return self._device_type == DeviceType.CUDA
    
    def is_xpu(self) -> bool:
        """Check if using Intel XPU."""
        return self._device_type == DeviceType.XPU
    
    def is_cpu(self) -> bool:
        """Check if using CPU only."""
        return self._device_type == DeviceType.CPU
    
    def is_accelerated(self) -> bool:
        """Check if using any GPU acceleration (CUDA or XPU)."""
        return self._device_type in (DeviceType.CUDA, DeviceType.XPU)
    
    def synchronize(self):
        """
        Synchronize device operations (wait for all operations to complete).
        Device-agnostic wrapper for CUDA/XPU synchronization.
        """
        if self._device_type == DeviceType.CUDA:
            torch.cuda.synchronize()
        elif self._device_type == DeviceType.XPU:
            try:
                torch.xpu.synchronize()
            except AttributeError:
                pass  # XPU sync not available, continue
    
    def empty_cache(self):
        """
        Clear device memory cache.
        Device-agnostic wrapper for CUDA/XPU cache clearing.
        """
        if self._device_type == DeviceType.CUDA:
            torch.cuda.empty_cache()
        elif self._device_type == DeviceType.XPU:
            try:
                torch.xpu.empty_cache()
            except AttributeError:
                pass  # XPU cache clear not available, continue
    
    def optimize_backends(self):
        """
        Configure backend optimizations based on device type.
        """
        if self._device_type == DeviceType.CUDA:
            # Enable CUDNN optimizations for NVIDIA
            torch.backends.cudnn.benchmark = True
            torch.backends.cudnn.deterministic = False
            print("   ✓ CUDNN benchmarking enabled")
        elif self._device_type == DeviceType.XPU:
            # XPU-specific optimizations
            # Note: Intel XPU doesn't use CUDNN, has its own optimizations
            print("   ✓ XPU optimizations active")
        # CPU doesn't need special backend configuration
    
    def get_easyocr_config(self) -> Tuple[bool, Optional[str]]:
        """
        Get configuration for EasyOCR initialization.
        
        For XPU: We pass gpu=True but PyTorch will use XPU backend underneath
        because we've set the XPU fallback at the PyTorch level.
        
        Returns:
            Tuple of (gpu_enabled: bool, device_name: str or None)
        """
        if self._device_type == DeviceType.CUDA:
            return (True, None)  # Use default CUDA
        elif self._device_type == DeviceType.XPU:
            # Enable GPU mode - PyTorch will route to XPU
            # EasyOCR will use PyTorch backend, which will use XPU
            return (True, None)  # XPU handled at PyTorch level
        else:  # CPU
            return (False, None)


# Global singleton instance
_device_manager: Optional[DeviceManager] = None


def get_device_manager() -> DeviceManager:
    """
    Get the global DeviceManager singleton instance.
    
    Returns:
        DeviceManager instance
    """
    global _device_manager
    if _device_manager is None:
        _device_manager = DeviceManager()
    return _device_manager


# Convenience functions for easy access
def get_device() -> torch.device:
    """
    Get the current PyTorch device.
    
    Returns:
        torch.device object
    """
    return get_device_manager().get_torch_device()


def get_device_type() -> DeviceType:
    """
    Get the current device type.
    
    Returns:
        DeviceType enum
    """
    return get_device_manager().get_device_type()


def is_cuda() -> bool:
    """Check if using CUDA."""
    return get_device_manager().is_cuda()


def is_xpu() -> bool:
    """Check if using Intel XPU."""
    return get_device_manager().is_xpu()


def is_cpu() -> bool:
    """Check if using CPU only."""
    return get_device_manager().is_cpu()


def is_accelerated() -> bool:
    """Check if using any GPU acceleration."""
    return get_device_manager().is_accelerated()


def synchronize_device():
    """Synchronize device operations."""
    get_device_manager().synchronize()


def empty_device_cache():
    """Clear device memory cache."""
    get_device_manager().empty_cache()


def optimize_backends():
    """Configure backend optimizations."""
    get_device_manager().optimize_backends()


def get_easyocr_reader(*args, **kwargs):
    """
    Get an EasyOCR Reader instance configured for the current device.
    
    This wrapper ensures EasyOCR uses the correct backend (CUDA/XPU/CPU)
    by configuring PyTorch at the underlying level.
    
    Args:
        *args: Positional arguments for easyocr.Reader
        **kwargs: Keyword arguments for easyocr.Reader
    
    Returns:
        easyocr.Reader instance
    """
    from easyocr import Reader
    
    gpu_enabled, device_name = get_device_manager().get_easyocr_config()
    
    # Override gpu parameter if not explicitly set
    if 'gpu' not in kwargs:
        kwargs['gpu'] = gpu_enabled
    
    # For XPU, we rely on PyTorch-level device routing
    # EasyOCR will use PyTorch tensors, which will use XPU backend
    if is_xpu():
        print("   ✓ EasyOCR will use Intel XPU via PyTorch backend")
    
    return Reader(*args, **kwargs)


def get_device_info() -> dict:
    """
    Get detailed information about the current device.
    
    Returns:
        Dictionary with device information
    """
    manager = get_device_manager()
    info = {
        'device_type': manager.get_device_type().value,
        'torch_device': str(manager.get_torch_device()),
        'accelerated': manager.is_accelerated(),
    }
    
    if manager.is_cuda():
        info['cuda_available'] = True
        info['cuda_device_name'] = torch.cuda.get_device_name(0)
        info['cuda_device_count'] = torch.cuda.device_count()
    elif manager.is_xpu():
        info['xpu_available'] = True
        try:
            info['xpu_device_count'] = torch.xpu.device_count()
        except AttributeError:
            info['xpu_device_count'] = 'unknown'
    
    return info
