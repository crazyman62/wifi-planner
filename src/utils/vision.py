import cv2
import numpy as np

def detect_walls(image_path, outer_material_name, inner_material_name, sensitivity=50):
    """
    Detects walls in a floor plan image using OpenCV.

    Args:
        image_path (str): Path to the floor plan image.
        outer_material_name (str): Material name for the outer walls (largest contour).
        inner_material_name (str): Material name for inner walls.
        sensitivity (int): 0-100, where higher means more sensitive (detects more small lines).

    Returns:
        list: A list of dicts [{'p1': (x,y), 'p2': (x,y), 'material': name}, ...]
              Coordinates are in pixels relative to the image top-left (0,0).
    """
    walls = []

    # 1. Load Image
    img = cv2.imread(image_path)
    if img is None:
        return []

    # Parameters based on Sensitivity
    # Sensitivity 0: Strict (Filters more noise, requires larger structures)
    # Sensitivity 100: Loose (Keeps small structures)

    # 1. Area Threshold for Noise Removal (Text)
    # Low Sensitivity (0) -> High Area Threshold (e.g. 300px)
    # High Sensitivity (100) -> Low Area Threshold (e.g. 10px)
    min_area = int(300 - (sensitivity * 2.9))
    min_area = max(10, min_area)

    # 2. Hough Parameters
    min_line_len = int(100 - (sensitivity * 0.9))
    min_line_len = max(10, min_line_len)

    hough_thresh = int(80 - (sensitivity * 0.6))
    hough_thresh = max(20, hough_thresh)

    # Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 2. Thresholding (Otsu Inverse to get White Walls on Black BG)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # 3. Noise Removal (Connected Components)
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(thresh, connectivity=8)

    cleaned_mask = np.zeros_like(thresh)

    for i in range(1, num_labels): # Skip background
        area = stats[i, cv2.CC_STAT_AREA]
        # Keep if area is large enough (removes text)
        if area > min_area:
            cleaned_mask[labels == i] = 255

    # Close gaps
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3,3))
    cleaned_mask = cv2.morphologyEx(cleaned_mask, cv2.MORPH_CLOSE, kernel)

    # 4. Outer Walls (Largest Contour on Clean Mask)
    # Use RETR_EXTERNAL to find only the outer boundary of the walls
    contours, _ = cv2.findContours(cleaned_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)

    outer_contour = None
    img_area = img.shape[0] * img.shape[1]

    # Find largest contour that looks like a building footprint
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area > img_area * 0.05: # Minimum 5% of image
            epsilon = 0.005 * cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, epsilon, True)
            outer_contour = approx
            break

    if outer_contour is not None:
        pts = outer_contour.reshape(-1, 2)
        num_pts = len(pts)
        for i in range(num_pts):
            p1 = tuple(map(float, pts[i]))
            p2 = tuple(map(float, pts[(i + 1) % num_pts]))
            walls.append({
                'p1': p1,
                'p2': p2,
                'material': outer_material_name
            })

    # 5. Inner Walls (Centerlines of Clean Mask)
    # Use Skeletonization to find the center line of walls
    skeleton = skeletonize(cleaned_mask)

    lines = cv2.HoughLinesP(skeleton, 1, np.pi / 180, threshold=hough_thresh, minLineLength=min_line_len, maxLineGap=10)

    if lines is not None:
        for line in lines:
            x1, y1, x2, y2 = line[0]
            p1 = (float(x1), float(y1))
            p2 = (float(x2), float(y2))

            # Check if this line is close to any outer wall
            is_outer = False
            if outer_contour is not None:
                # Iterate outer walls
                # This is O(N*M), but N (outer) and M (lines) are small enough.
                pts = outer_contour.reshape(-1, 2)
                for i in range(len(pts)):
                    op1 = pts[i]
                    op2 = pts[(i+1)%len(pts)]

                    # Distance from line segment to line segment is complex.
                    # Simpler: check if mid point of new line is close to any outer segment?
                    mid_x = (x1 + x2) / 2
                    mid_y = (y1 + y2) / 2

                    # Point to segment distance
                    dist = point_to_segment_dist((mid_x, mid_y), op1, op2)
                    if dist < 10: # 10 pixels tolerance
                        is_outer = True
                        break

            if not is_outer:
                walls.append({
                    'p1': p1,
                    'p2': p2,
                    'material': inner_material_name
                })

    return walls

def skeletonize(img):
    """
    Morphological skeletonization (iterative thinning).
    img: Binary image (0, 255)
    """
    size = np.size(img)
    skel = np.zeros(img.shape, np.uint8)

    element = cv2.getStructuringElement(cv2.MORPH_CROSS, (3,3))
    temp_img = img.copy()

    # Safety limit
    for _ in range(100):
        eroded = cv2.erode(temp_img, element)
        temp = cv2.dilate(eroded, element)
        temp = cv2.subtract(temp_img, temp)
        skel = cv2.bitwise_or(skel, temp)
        temp_img = eroded.copy()

        if cv2.countNonZero(temp_img) == 0:
            break

    return skel

def point_to_segment_dist(p, s1, s2):
    """Calculates distance from point p to segment s1-s2."""
    px, py = p
    x1, y1 = s1
    x2, y2 = s2

    dx = x2 - x1
    dy = y2 - y1

    if dx == 0 and dy == 0:
        return np.hypot(px - x1, py - y1)

    t = ((px - x1) * dx + (py - y1) * dy) / (dx*dx + dy*dy)

    if t < 0:
        closest_x, closest_y = x1, y1
    elif t > 1:
        closest_x, closest_y = x2, y2
    else:
        closest_x = x1 + t * dx
        closest_y = y1 + t * dy

    return np.hypot(px - closest_x, py - closest_y)
