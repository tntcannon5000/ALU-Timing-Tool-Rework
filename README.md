# ALU Timing Tool - Refactored

A real-time racing timer and distance tracker using computer vision and machine learning.

## Features

- Real-time percentage/distance tracking using CNN
- Timer extraction using template matching  
- Performance-optimized processing loop
- Modern, responsive UI with position persistence
- Race mode with ghost comparison
- Modular, maintainable codebase

## Quick Start

### Windows Users (Recommended)
Double-click `start_alu_timing_tool.bat` - it will:
- Create virtual environment automatically
- Install all dependencies  
- Start the tool
- Keep terminal open for troubleshooting

### Advanced Users
Use `quick_start.bat` if you already have the environment set up.

### Manual Installation
1. Clone the repository:
```bash
git clone <repository-url>
cd ALU-Timing-Tool-Rework
```

2. Create virtual environment:
```bash
Set-ExecutionPolicy RemoteSigned
python -m venv venv
venv\Scripts\activate  # Windows
# or
source venv/bin/activate  # Linux/Mac
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Run the tool:
```bash
python main.py
```

## New Features

### UI Position Persistence
- Window position is automatically saved when you close the tool
- Restores to the same position on next startup
- Validates position to ensure window isn't placed off-screen
- Handles multi-monitor setups gracefully
- Remembers panel expansion states (race controls, debug info)

### Easy Launcher
- `start_alu_timing_tool.bat` - Full setup and launch
- `quick_start.bat` - Quick launch for existing setups  
- Automatic dependency management
- Error handling and troubleshooting

## Project Structure

```
├── main.py                         # Main entry point
├── timer_optimize_py_v4.py         # Main application class
├── requirements.txt                # Dependencies
├── start_alu_timing_tool.bat       # Full launcher (recommended)
├── quick_start.bat                 # Quick launcher
├── ui_config.json                  # UI position settings (auto-created)
├── src/                            # Source code modules
│   ├── models/                     # CNN models
│   │   ├── __init__.py
│   │   └── percentage_cnn.py
│   ├── modules/                    # Application modules
│   │   ├── __init__.py
│   │   ├── timer_recognition.py    # Timer digit recognition
│   │   ├── image_processing.py     # Image processing utilities
│   │   ├── cnn_prediction.py       # CNN prediction logic
│   │   ├── ui.py                   # User interface
│   │   ├── race_data.py            # Race data management
│   │   └── frame_capture.py        # Threaded frame capture
│   └── utils/                      # Utility functions
│       ├── __init__.py
│       ├── helpers.py              # General helper functions
│       ├── windowtools.py          # Window capture utilities
│       └── ui_config.py            # UI configuration management
├── src/assets/                     # Assets and templates
│   ├── models/                     # Pre-trained models
│   └── templates/timer_templates/  # Digit templates
└── old/                            # Legacy files and notebooks
```

## Usage

1. **First Time Setup**: Double-click `start_alu_timing_tool.bat`
2. **Subsequent Runs**: Use either batch file or run manually
3. The tool will:
   - Automatically find your game window  
   - Restore previous UI position
   - Start real-time tracking
   - Save settings when you close

### UI Controls
- **Drag anywhere** to move the window
- **📌 Pin button** - Keep window on top
- **v/^ Race button** - Expand race controls
- **🐛 Debug button** - Show performance metrics  
- **✕ Close button** - Exit and save settings

### Race Mode
- **Record Mode**: Track your times
- **Race Mode**: Compare against loaded ghost
- **Load Ghost**: Load previous race data for comparison
- **Save Ghost**: Save current race as ghost file

## Configuration

### Game Window
Edit `main.py` to match your game:
```python
app = ALUTimingTool(
    window_name="your_game_window",  # Change to match your game
    confidence_threshold=0.65        # Adjust CNN confidence threshold
)
```

### UI Settings
The tool automatically saves:
- Window position and size
- Pin state (always on top)
- Panel expansion states
- UI scaling preferences

Settings are stored in `ui_config.json` (created automatically).

## Troubleshooting

### Common Issues
1. **"Python not found"**: Install Python 3.8+ from python.org
2. **Window not detected**: Change `window_name` in main.py to match your game
3. **Dependencies fail**: Run as administrator or check internet connection
4. **Poor accuracy**: Adjust confidence threshold or check lighting conditions
5. **UI off-screen**: Delete `ui_config.json` to reset position

### Performance Issues
- Ensure GPU drivers are updated for PyTorch
- Close unnecessary applications
- Check debug panel for performance metrics

### Multi-Monitor Setup
- Position validation ensures window stays visible
- Handles monitor disconnection gracefully
- Automatically moves window to primary monitor if needed

## Development

### Architecture
- Modular design with clean separation
- Type hints throughout
- Comprehensive error handling  
- Performance monitoring built-in
- Configuration management system

### Adding Features
1. Follow existing module structure
2. Add appropriate type hints
3. Include error handling
4. Update configuration if needed
5. Test multi-monitor scenarios

## Performance Optimizations

- JIT compilation for CNN models
- Tensor caching and reuse
- Efficient image processing
- 90 FPS UI updates
- Memory management optimizations
- Threaded frame capture with minimal latency

## Model Information

Supports multiple CNN architectures in `src/models/percentage_cnn.py`:
- OptimizedPercentageCNN (recommended)
- LightweightPercentageCNN  
- SimpleCNN (fallback)

## Contributing

When contributing:
1. Test on multiple monitor setups
2. Ensure UI position persistence works
3. Follow modular structure
4. Add appropriate type hints
5. Update documentation
