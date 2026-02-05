"""
CNN Prediction Module

This module handles CNN-based percentage prediction with optimizations.
"""

import torch
import torch.nn as nn
import time as systime
from typing import Optional, Tuple, List
from src.models import get_model, get_default_model_type
from src.utils.helpers import get_model_path
from src.utils.device import (
    get_device,
    synchronize_device,
    empty_device_cache,
    optimize_backends,
    is_accelerated
)


class CNNPredictor:
    """
    CNN predictor for percentage recognition with performance optimizations.
    """
    
    def __init__(self, confidence_threshold: float = 0.65):
        """
        Initialize the CNN predictor.
        
        Args:
            confidence_threshold: Minimum confidence threshold for predictions
        """
        self.device = get_device()
        self.confidence_threshold = confidence_threshold
        self.model = None
        self.model_name = "unknown"
        self._tensor_cache = None
        self.inference_times: List[float] = []
        self.avg_inference_time = 0.0
        
        self._load_model()
        self._optimize_model()
    
    def _load_model(self):
        """Load the trained model with fallback options."""
        try:
            # First try the centralized model system
            self.model = get_model()
            self.model_name = get_default_model_type()
            
            # Try to load the optimized model weights
            try:
                self.model.load_state_dict(torch.load(get_model_path('percentage_cnn_optimized.pth'), map_location=self.device))
            except FileNotFoundError:
                self.model.load_state_dict(torch.load(get_model_path('percentage_cnn.pth'), map_location=self.device))
            
            self.model = self.model.to(self.device)
            
        except Exception as e:
            # Fallback to hardcoded model loading
            try:
                # Legacy SimpleCNN fallback
                class SimpleCNN(nn.Module):
                    def __init__(self, num_classes=100):
                        super(SimpleCNN, self).__init__()
                        self.conv1 = nn.Conv2d(in_channels=1, out_channels=16, kernel_size=3, padding=1)
                        self.pool = nn.MaxPool2d(kernel_size=2, stride=2)
                        self.conv2 = nn.Conv2d(in_channels=16, out_channels=32, kernel_size=3, padding=1)
                        self.fc1 = nn.Linear(32 * 16 * 16, 512)
                        self.fc2 = nn.Linear(512, num_classes)
                        self.relu = nn.ReLU()

                    def forward(self, x):
                        x = self.pool(self.relu(self.conv1(x)))
                        x = self.pool(self.relu(self.conv2(x)))
                        x = x.view(-1, 32 * 16 * 16)
                        x = self.relu(self.fc1(x))
                        x = self.fc2(x)
                        return x
                
                self.model = SimpleCNN(num_classes=100).to(self.device)
                try:
                    self.model.load_state_dict(torch.load(get_model_path('percentage_cnn_optimized.pth'), map_location=self.device))
                    self.model_name = "SimpleCNN (fallback with optimized weights)"
                except FileNotFoundError:
                    self.model.load_state_dict(torch.load(get_model_path('percentage_cnn.pth'), map_location=self.device))
                    self.model_name = "SimpleCNN (fallback with legacy weights)"
            except Exception as fallback_error:
                self.model = None
                print(f"Failed to load model: {fallback_error}")
    
    def _optimize_model(self):
        """Apply performance optimizations to the model."""
        if self.model is not None:
            self.model.eval()  # Set the model to evaluation mode
            
            # 🚀 PERFORMANCE OPTIMIZATIONS 🚀
            
            # 1. Configure backend optimizations (CUDA/XPU specific)
            optimize_backends()
            
            # 2. Disable gradient computation globally
            torch.set_grad_enabled(False)
            
            # 3. Try to compile the model with torch.jit for optimization
            try:
                # Create a dummy input for scripting
                dummy_input = torch.randn(1, 1, 64, 64).to(self.device)
                self.model = torch.jit.script(self.model)
                
                # Warm up the compiled model
                for _ in range(5):
                    with torch.no_grad():
                        _ = self.model(dummy_input)
                
            except Exception as jit_error:
                pass  # Continue with eager mode
            
            # 4. Set memory allocation strategy
            empty_device_cache()
    
    def predict(self, tensor_image: torch.Tensor) -> Optional[Tuple[int, float]]:
        """
        Use the trained CNN to predict the percentage from a tensor.
        
        Args:
            tensor_image: Preprocessed tensor image
            
        Returns:
            Tuple of (predicted_percentage, confidence) or None if prediction fails
        """
        if self.model is None:
            return None
            
        try:
            # Start timing - more precise timing
            if is_accelerated():
                synchronize_device()  # Ensure all previous operations are complete
            inference_start = systime.perf_counter()
            
            # Reuse tensor cache if possible (optimization)
            if self._tensor_cache is None or self._tensor_cache.shape[0] != 1:
                self._tensor_cache = tensor_image.to(self.device, non_blocking=True)
            else:
                self._tensor_cache.copy_(tensor_image, non_blocking=True)
            
            # Make prediction with minimal overhead
            outputs = self.model(self._tensor_cache)
            _, predicted = torch.max(outputs, 1)
            confidence = torch.softmax(outputs, 1)[0][predicted].item()
            
            # End timing with synchronization
            if is_accelerated():
                synchronize_device()  # Wait for GPU operations to complete
            inference_end = systime.perf_counter()
            inference_time = (inference_end - inference_start) * 1000  # Convert to ms
            
            # Update inference time tracking
            self.inference_times.append(inference_time)
            if len(self.inference_times) > 100:  # Keep only last 100 measurements
                self.inference_times.pop(0)
            
            # Calculate new average
            self.avg_inference_time = sum(self.inference_times) / len(self.inference_times)
                
            return predicted.item(), confidence
        except Exception as e:
            print(f"CNN prediction error: {e}")
            return None
    
    def is_confident(self, confidence: float) -> bool:
        """
        Check if the prediction confidence meets the threshold.
        
        Args:
            confidence: Prediction confidence
            
        Returns:
            True if confidence is above threshold
        """
        return confidence >= self.confidence_threshold
    
    def get_stats(self) -> dict:
        """
        Get prediction statistics.
        
        Returns:
            Dictionary with prediction statistics
        """
        return {
            'model_name': self.model_name,
            'device': str(self.device),
            'avg_inference_time': self.avg_inference_time,
            'confidence_threshold': self.confidence_threshold,
            'total_predictions': len(self.inference_times)
        }
