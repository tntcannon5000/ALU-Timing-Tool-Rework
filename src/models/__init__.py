"""
CNN Models for Percentage Recognition

This module provides optimized CNN architectures for real-time percentage recognition.
"""

from .percentage_cnn import (
    OptimizedPercentageCNN,
    LightweightPercentageCNN,
    SimpleCNN,
    get_model,
    get_default_model_type,
    set_default_model_type,
    get_model_info,
    count_parameters,
    benchmark_model,
    DEFAULT_MODEL_TYPE
)

__all__ = [
    'OptimizedPercentageCNN',
    'LightweightPercentageCNN', 
    'SimpleCNN',
    'get_model',
    'get_default_model_type',
    'set_default_model_type', 
    'get_model_info',
    'count_parameters',
    'benchmark_model',
    'DEFAULT_MODEL_TYPE'
]
