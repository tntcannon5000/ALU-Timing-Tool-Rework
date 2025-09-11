# ALU Timing Tool - Refactored

A real-time racing timer and distance tracker using computer vision and machine learning.

## Features

- Real-time percentage/distance tracking using CNN
- Timer extraction using template matching
- Performance-optimized processing loop
- Modern, responsive UI
- Modular, maintainable codebase

## Project Structure

```
├── main.py                     # Main entry point
├── timer_optimize_py_v4.py     # Main application class
├── requirements.txt            # Dependencies
├── src/                        # Source code modules
│   ├── models/                 # CNN models
│   │   ├── __init__.py
│   │   └── percentage_cnn.py
│   ├── modules/                # Application modules
│   │   ├── __init__.py
│   │   ├── timer_recognition.py    # Timer digit recognition
│   │   ├── image_processing.py     # Image processing utilities
│   │   ├── cnn_prediction.py       # CNN prediction logic
│   │   └── ui.py                   # User interface
│   └── utils/                  # Utility functions
│       ├── __init__.py
│       ├── helpers.py          # General helper functions
│       └── windowtools.py      # Window capture utilities
├── timer_templates/            # Digit templates for recognition
│   ├── 0.png
│   ├── 1.png
│   └── ...
└── old/                        # Legacy files and notebooks
```

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd ALU-Timing-Tool-Rework
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Ensure you have the model weights file:
   - `percentage_cnn_optimized.pth` (preferred)
   - OR `percentage_cnn.pth` (fallback)

## Usage

1. Start your racing game/application
2. Run the timing tool:
```bash
python main.py
```

3. The tool will automatically:
   - Find the game window
   - Start capturing and processing frames
   - Display real-time metrics in the UI

4. To stop, press `Ctrl+C` in the terminal

## Configuration

Edit the main function in `main.py` to customize:

```python
app = ALUTimingTool(
    window_name="your_game_window",  # Change to match your game
    confidence_threshold=0.65        # Adjust CNN confidence threshold
)
```

## Modules Overview

### Timer Recognition (`src/modules/timer_recognition.py`)
- Template matching for digit recognition
- Handles italic text correction
- Converts timer strings to milliseconds

### Image Processing (`src/modules/image_processing.py`)
- Timer ROI extraction
- Image preprocessing for CNN
- Blue mask detection for timer location

### CNN Prediction (`src/modules/cnn_prediction.py`)
- Optimized CNN inference
- Performance monitoring
- Confidence thresholding

### UI (`src/modules/ui.py`)
- Real-time metrics display
- Progress tracking
- Draggable, pinnable window

## Performance Optimizations

- JIT compilation for CNN models
- Tensor caching and reuse
- Efficient image processing
- 90 FPS UI updates
- Memory management optimizations

## Development

The codebase is now modular and maintainable:

- Each module has a single responsibility
- Clean separation of concerns
- Type hints throughout
- Comprehensive error handling
- Performance monitoring built-in

## Legacy Files

The `old/` directory contains the original Jupyter notebooks and experimental code for reference.

## Model Information

The tool supports multiple CNN architectures defined in `src/models/percentage_cnn.py`:
- OptimizedPercentageCNN (recommended)
- LightweightPercentageCNN
- SimpleCNN (fallback)

## Troubleshooting

1. **Window not found**: Ensure the game window name matches the `window_name` parameter
2. **Poor accuracy**: Adjust the `confidence_threshold` or retrain the model
3. **Performance issues**: Check GPU availability and reduce processing resolution
4. **Timer not detected**: Verify timer templates are in the `timer_templates/` directory

## Contributing

When adding new features:
1. Follow the modular structure
2. Add appropriate type hints
3. Include error handling
4. Update this README if needed
