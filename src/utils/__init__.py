"""
Utilities for ALU Timing Tool

This package contains utility modules for the timing tool.
"""

from .helpers import *
from .windowtools import *
from .ui_config import UIConfigManager
from .device import (
    get_device,
    get_device_type,
    get_device_manager,
    is_cuda,
    is_xpu,
    is_cpu,
    is_accelerated,
    synchronize_device,
    empty_device_cache,
    optimize_backends,
    get_easyocr_reader,
    get_device_info,
    DeviceType
)

__all__ = [
    'UIConfigManager',
    'get_device',
    'get_device_type',
    'get_device_manager',
    'is_cuda',
    'is_xpu',
    'is_cpu',
    'is_accelerated',
    'synchronize_device',
    'empty_device_cache',
    'optimize_backends',
    'get_easyocr_reader',
    'get_device_info',
    'DeviceType'
]