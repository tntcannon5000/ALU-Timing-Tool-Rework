"""Modules for ALU Timing Tool

Core v5 modules (CE backend) are imported eagerly.
Legacy v4 modules (OCR/CNN/capture) are lazy-loaded on first access
so that v5 works without cv2, torch, dxcam, or easyocr installed.
"""

# --- Core v5 modules (always available) ---
from .ui import TimingToolUI
from .race_data import RaceDataManager
from .ce_client import CheatEngineClient

# --- Legacy v4 modules (lazy-loaded) ---
_V4_MODULES = {
    'TimerRecognizer': '.timer_recognition',
    'ImageProcessor': '.image_processing',
    'CNNPredictor': '.cnn_prediction',
    'FrameCaptureThread': '.frame_capture',
}


def __getattr__(name: str):
    if name in _V4_MODULES:
        import importlib
        module = importlib.import_module(_V4_MODULES[name], __package__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # v5 (CE backend)
    'TimingToolUI',
    'RaceDataManager',
    'CheatEngineClient',
    # v4 (legacy, lazy-loaded)
    'TimerRecognizer',
    'ImageProcessor',
    'CNNPredictor',
    'FrameCaptureThread',
]