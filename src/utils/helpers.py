import cv2
import re
import numpy as np

def pre_process(region: np.ndarray) -> np.ndarray:
    """
    Preprocesses the given image region by:
    1. Converting to grayscale (if not already).
    2. Applying a binary threshold where light grays/whites become white, everything else black.
    3. Inverting the result to produce black text on white background.

    Parameters:
        region (np.ndarray): RGB or grayscale image region (as a NumPy array).

    Returns:
        np.ndarray: Preprocessed binary image (uint8) ready for OCR.
    """

    gray = cv2.cvtColor(region, cv2.COLOR_RGB2GRAY)


    # Binary threshold: treat anything above ~200 as white
    _, thresh = cv2.threshold(gray, 225, 255, cv2.THRESH_BINARY)

    # Invert: white becomes black, black becomes white
    inverted = cv2.bitwise_not(thresh)

    return thresh

def pre_process_distbox(region: np.ndarray) -> np.ndarray:
    """
    Preprocesses the given image region by:
    1. Converting to grayscale (if not already).
    2. Applying a binary threshold where light grays/whites become white, everything else black.
    3. Inverting the result to produce black text on white background.

    Parameters:
        region (np.ndarray): RGB or grayscale image region (as a NumPy array).

    Returns:
        np.ndarray: Preprocessed binary image (uint8) ready for OCR.
    """

    gray = cv2.cvtColor(region, cv2.COLOR_RGB2GRAY)


    # Invert: white becomes black, black becomes white
    inverted = cv2.bitwise_not(gray)

    return inverted

def extract_dist_percentage(text: str) -> str:
    """
    Extracts the distance percentage from OCR'd text.

    Args:
        text: The input string from OCR.

    Returns:
        A string representing the extracted 1 or 2 digit distance,
        or an empty string if extraction is not successful.
    """

    dist_pattern = r"D[iI1]ST"
    touch_pattern = r"T[O0]UCH(?:E|Ei)?"

    dist_match = re.search(dist_pattern, text, re.IGNORECASE)
    if not dist_match:
        return ""

    text_after_dist = text[dist_match.end():]

    touch_match = re.search(touch_pattern, text_after_dist, re.IGNORECASE)
    candidate_segment = text_after_dist[:touch_match.start()] if touch_match else text_after_dist

    numeric_match = re.search(r'\d+', candidate_segment)
    if not numeric_match:
        return ""

    num_str = numeric_match.group(0)

    if len(num_str) == 3:
        return num_str[:2]
    elif len(num_str) in (1, 2):
        return num_str
    else:
        return ""


import numpy as np
import cv2

def get_dist_box(region_rgb: np.ndarray,
                 reader,
                 pre_process) -> np.ndarray | None:
    """
    Find the bounding box from 'DIST' through the next word ending in '%' or '7'
    in a single OCR pass, and return the cropped sub-image.

    Args:
        region_rgb:   np.ndarray of shape (H, W, 3), the RGB image to search.
        reader:       an initialized easyocr.Reader,
        pre_process:  function that takes a gray image and returns a preprocessed gray image.

    Returns:
        A numpy array of the cropped ROI (in RGB), or None if no box found.
    """
    # 1. OCR on preprocessed gray image
    gray = cv2.cvtColor(region_rgb, cv2.COLOR_RGB2GRAY)
    prep = pre_process(gray)
    results = reader.readtext(prep)

    # 2. Locate 'DIST'
    for i, (bbox, text, _) in enumerate(results):
        if "dist" in text.lower():
            # convert bbox to min/max
            box = np.array(bbox)
            x0, y0 = box[:,0].min(), box[:,1].min()
            x1, y1 = box[:,0].max(), box[:,1].max()

            # 3. Find the next %/7 on same line, to the right
            for _, (next_bbox, next_text, _) in enumerate(results[i+1:], start=i+1):
                nb = np.array(next_bbox)
                nx0, ny0 = nb[:,0].min(), nb[:,1].min()
                nx1, ny1 = nb[:,0].max(), nb[:,1].max()

                # same line?
                if abs(ny0 - y0) < 0.2*(y1 - y0) and nx0 > x1:
                    if next_text.strip().endswith('%') or next_text.strip().endswith('7'):
                        # extend
                        x0, y0 = min(x0, nx0), min(y0, ny0)
                        x1, y1 = max(x1, nx1), max(y1, ny1)
                        break

            # 4. crop and return
            x0, y0, x1, y1 = map(int, (x0, y0, x1, y1))
            return region_rgb[y0:y1, x0:x1]

    # nothing found
    return None