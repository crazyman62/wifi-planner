import cv2
import numpy as np

def detect_walls(image_path, outer_material_name, inner_material_name):
    """
    Detects walls in a floor plan image using OpenCV.

    Args:
        image_path (str): Path to the floor plan image.
        outer_material_name (str): Material name for the outer walls (largest contour).
        inner_material_name (str): Material name for inner walls.

    Returns:
        list: A list of dicts [{'p1': (x,y), 'p2': (x,y), 'material': name}, ...]
              Coordinates are in pixels relative to the image top-left (0,0).
    """
    walls = []

    # 1. Load Image
    img = cv2.imread(image_path)
    if img is None:
        return []

    # Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 2. Preprocessing
    # Gaussian Blur to reduce noise
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    # Canny Edge Detection
    # Thresholds can be tuned.
    # Usually floorplans have high contrast lines.
    edges = cv2.Canny(blurred, 50, 150)

    # 3. Find Contours
    contours, hierarchy = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        return []

    # 4. Identify Outer Walls (Largest Contour)
    # We assume the largest closed contour is the building outline
    # Sort by area
    contours = sorted(contours, key=cv2.contourArea, reverse=True)

    # Use the largest contour that has a significant area
    outer_contour = None
    outer_idx = -1
    img_area = img.shape[0] * img.shape[1]

    for i, cnt in enumerate(contours):
        # Approximate to simplify
        epsilon = 0.005 * cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, epsilon, True)

        area = cv2.contourArea(approx)

        # Heuristic: Outer wall should be reasonably large but not the whole image box
        if area > img_area * 0.05 and area < img_area * 0.99:
            outer_contour = approx
            outer_idx = i
            break

    if outer_contour is not None:
        # Create walls from outer contour segments
        pts = outer_contour.reshape(-1, 2)
        num_pts = len(pts)
        for i in range(num_pts):
            p1 = tuple(map(float, pts[i]))
            p2 = tuple(map(float, pts[(i + 1) % num_pts])) # Close the loop
            walls.append({
                'p1': p1,
                'p2': p2,
                'material': outer_material_name
            })

    # 5. Identify Inner Walls using HoughLinesP
    # We mask out the outer contour to avoid duplicating it or detecting it again
    # Actually, simpler to just detect all lines and filter those close to outer contour?
    # Or just use HoughLinesP on the whole edge map and filter out those that are part of the outer contour?

    # Alternative: Use all other contours as inner walls if they are open?
    # Floorplan inner walls are often double lines.
    # For a simple "Phase 2" implementation, let's use HoughLinesP on the edge map.

    # Create a mask for outer contour if it exists
    mask = np.zeros_like(edges)
    if outer_contour is not None:
        cv2.drawContours(mask, [outer_contour], -1, 255, thickness=5) # Thick line to cover edges

    # Remove outer contour edges from the edge map
    # edges_internal = cv2.bitwise_and(edges, cv2.bitwise_not(mask))
    # Actually, let's just use HoughLinesP on the original edges,
    # and maybe filter out lines that coincide with outer contour segments?

    # Let's try a simpler approach:
    # 1. Outer contour is definitely walls.
    # 2. Use HoughLinesP for everything.
    # 3. Add lines that are NOT close to outer contour segments.

    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=50, minLineLength=30, maxLineGap=10)

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
