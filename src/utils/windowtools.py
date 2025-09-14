import win32gui
import win32api

def fuzzy_window_search(search_term):
    results = []
    def callback(hwnd, extra):
        
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if search_term.lower() in title.lower():
                rect = win32gui.GetWindowRect(hwnd)
                # Handle slightly negative coordinates by clamping to 0
                x1 = max(0, rect[0]+8)
                y1 = max(0, rect[1]+8)
                x2 = rect[2]-8
                y2 = rect[3]-8
                coords = (x1, y1, x2, y2)
                results.append(coords)
    
    win32gui.EnumWindows(callback, None)
    
    print(results)
    print(len(results))

    if len(results) > 1:
        raise ValueError("Too many matching windows found")
    elif len(results) == 0:
        raise ValueError("No matching windows found")
    elif len(results)==1:
        return results[0]
    

def calculate_aspect_ratio(coords):
    x1, y1, x2, y2 = coords
    width = x2 - x1
    height = y2 - y1
    return width / height


def check_aspect_ratio_validity(aspect_ratio):
    if aspect_ratio < 1.15 or aspect_ratio > 2.3334:
        raise ValueError("The aspect ratio is unreasonable.")
    else:
        print("The aspect ratio is reasonable.")

def get_monitor_number_from_coords(coords):
    """
    Returns the monitor number (0-based) that contains the center of the given window coordinates.
    """
    x1, y1, x2, y2 = coords
    center_x = (x1 + x2) // 2
    center_y = (y1 + y2) // 2

    monitors = win32api.EnumDisplayMonitors()
    for idx, (handle, hdc, monitor_rect) in enumerate(monitors):
        mx1, my1, mx2, my2 = monitor_rect
        if mx1 <= center_x < mx2 and my1 <= center_y < my2:
            return idx
    raise ValueError("Window is not on any detected monitor.")

def normalise_coords_to_monitor(coords, monitor_number):
    """
    Normalises the coordinates of a window to the specified monitor.
    Ensures coordinates are within valid monitor bounds.
    """
    x1, y1, x2, y2 = coords
    monitors = win32api.EnumDisplayMonitors()
    monitor_rect = monitors[monitor_number][2]
    mx1, my1, mx2, my2 = monitor_rect

    # Calculate the offset of the monitor
    offset_x = mx1
    offset_y = my1

    # Normalise the coordinates
    norm_x1 = x1 - offset_x
    norm_y1 = y1 - offset_y
    norm_x2 = x2 - offset_x
    norm_y2 = y2 - offset_y
    
    # Get monitor dimensions
    monitor_width = mx2 - mx1
    monitor_height = my2 - my1
    
    # Clamp coordinates to monitor bounds
    norm_x1 = max(0, min(norm_x1, monitor_width))
    norm_y1 = max(0, min(norm_y1, monitor_height))
    norm_x2 = max(0, min(norm_x2, monitor_width))
    norm_y2 = max(0, min(norm_y2, monitor_height))
    
    # Ensure x2 > x1 and y2 > y1 (valid rectangle)
    if norm_x2 <= norm_x1:
        norm_x2 = norm_x1 + 1
    if norm_y2 <= norm_y1:
        norm_y2 = norm_y1 + 1
    
    norm_coords = (norm_x1, norm_y1, norm_x2, norm_y2)
    
    return norm_coords