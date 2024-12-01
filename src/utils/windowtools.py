import win32gui

def fuzzy_window_search(search_term):
    results = []
    def callback(hwnd, extra):
        
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if search_term.lower() in title.lower():
                rect = win32gui.GetWindowRect(hwnd)
                x1 = rect[0]
                y1 = rect[1]
                x2 = rect[2]
                y2 = rect[3]
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
    if aspect_ratio < 1.15 or aspect_ratio > 1.95:
        print("The aspect ratio is unreasonable.")
    else:
        print("The aspect ratio is reasonable.")