import numpy as np
import cv2
from src.engine.physics import calculate_log_distance_path_loss, segments_intersect

def generate_heatmap(
    width, height,
    ppm,
    access_points,
    walls,
    hardware_data,
    materials_data,
    resolution=10
):
    """
    Generates a heatmap grid for the floor plan.

    :param width: Image width in pixels
    :param height: Image height in pixels
    :param ppm: Pixels per meter
    :param access_points: List of AP dicts
    :param walls: List of Wall dicts
    :param hardware_data: Dict of hardware specs
    :param materials_data: Dict of material specs
    :param resolution: Grid resolution in pixels (lower = higher res but slower)
    :return: 2D numpy array of RSSI values (dBm), origin at top-left
    """

    # Grid dimensions
    grid_w = width // resolution
    grid_h = height // resolution

    # Initialize grid with a noise floor (e.g. -100 dBm)
    heatmap = np.full((grid_h, grid_w), -100.0)

    if not access_points:
        return heatmap

    # Coordinate grids
    # We want the center of each grid cell
    x_coords = np.linspace(resolution/2, width - resolution/2, grid_w)
    y_coords = np.linspace(resolution/2, height - resolution/2, grid_h)

    # Prepare Walls for faster access
    # Convert list of dicts to list of tuples: ((x1, y1), (x2, y2), loss_5ghz)
    processed_walls = []
    for w in walls:
        mat_name = w['material']
        mat_info = materials_data.get(mat_name, {})
        # Use 5GHz loss for Phase 1
        loss = mat_info.get('loss', {}).get('5', 0.0)
        processed_walls.append((w['p1'], w['p2'], loss))

    # Calculate for each AP
    for ap in access_points:
        ap_model_name = ap['model']
        ap_spec = hardware_data.get(ap_model_name)
        if not ap_spec:
            continue

        # 5GHz Phase 1
        band_spec = ap_spec['bands'].get('5')
        if not band_spec:
            continue

        tx_power = band_spec['max_tx_power']
        gain = band_spec['gain']
        freq = 5200 # MHz

        ap_x, ap_y = ap['x'], ap['y']

        # Iterate over grid
        # Optimization: Could use meshgrid and vectorized operations for distance,
        # but wall intersection is hard to vectorize purely with numpy without spatial indexing.
        # For Phase 1, a simple loop is fine.

        for r in range(grid_h):
            for c in range(grid_w):
                cell_x = x_coords[c]
                cell_y = y_coords[r]

                # Distance in pixels
                dx = cell_x - ap_x
                dy = cell_y - ap_y
                dist_px = np.sqrt(dx*dx + dy*dy)
                dist_m = dist_px / ppm

                # Wall Loss Calculation
                # Check line segment from (ap_x, ap_y) to (cell_x, cell_y)
                current_wall_loss = 0.0

                # Simple optimization: if distance is very small, skip wall checks
                if dist_px > 1:
                    for w_p1, w_p2, w_loss in processed_walls:
                        if segments_intersect((ap_x, ap_y), (cell_x, cell_y), w_p1, w_p2):
                            current_wall_loss += w_loss

                rssi = calculate_log_distance_path_loss(
                    tx_power_dbm=tx_power,
                    tx_gain_dbi=gain,
                    frequency_mhz=freq,
                    distance_meters=dist_m,
                    wall_loss_db=current_wall_loss
                )

                # Combine signals (Max Hold for multiple APs covers the area best)
                if rssi > heatmap[r, c]:
                    heatmap[r, c] = rssi

    return heatmap

def heatmap_to_pixmap(heatmap, width, height):
    """
    Converts a 2D RSSI grid to a QPixmap with a color map.
    """
    from PySide6.QtGui import QImage, QPixmap

    # Normalize or clamp for visualization
    # User Request: Red = Poor (-80), Blue = Great (-50)
    # Standard Jet: 0 (Blue) -> 255 (Red)
    # So we want -50 (High) -> 0 (Blue)
    # And -80 (Low) -> 255 (Red)

    min_dbm = -80.0 # Poor
    max_dbm = -50.0 # Great

    # Clamp first
    clamped = np.clip(heatmap, min_dbm, max_dbm)

    # Calculate normalization
    # If val = -50 (max), we want norm = 0
    # If val = -80 (min), we want norm = 1
    # Formula: (max_dbm - val) / (max_dbm - min_dbm)
    # Check: (-50 - (-50)) / 30 = 0
    # Check: (-50 - (-80)) / 30 = 30/30 = 1

    norm = (max_dbm - clamped) / (max_dbm - min_dbm)

    # OpenCV applies colormaps to 8-bit images (0-255)
    img_u8 = (norm * 255).astype(np.uint8)

    # cv2.applyColorMap expects BGR, so we get BGR out
    # COLORMAP_JET is standard rainbow (Blue->Red)
    # With our inverted norm:
    # High signal (-50) -> 0 -> Blue
    # Low signal (-80) -> 255 -> Red
    color_img = cv2.applyColorMap(img_u8, cv2.COLORMAP_JET)

    # Mask transparent for very low signal
    # If signal is <= min_dbm, make it transparent
    # We can create an alpha channel
    alpha = np.where(heatmap <= min_dbm + 1.0, 0, 128) # 128 = 50% opacity
    alpha = alpha.astype(np.uint8)

    # Merge Alpha
    b, g, r = cv2.split(color_img)
    rgba = cv2.merge([r, g, b, alpha]) # RGB order for QImage

    # Resize to full image size (heatmap is low res)
    # cv2.resize uses interpolation, which smooths the blocks
    rgba_full = cv2.resize(rgba, (width, height), interpolation=cv2.INTER_LINEAR)

    h, w, ch = rgba_full.shape
    bytes_per_line = ch * w
    qimg = QImage(rgba_full.data, w, h, bytes_per_line, QImage.Format_RGBA8888)

    return QPixmap.fromImage(qimg)
