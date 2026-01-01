import numpy as np
import cv2
from src.engine.physics import calculate_log_distance_path_loss, segments_intersect, get_antenna_gain

def generate_heatmap(
    width, height,
    ppm,
    access_points,
    walls,
    hardware_data,
    materials_data,
    frequency_band="5", # "2.4", "5", or "6"
    resolution=10,
    target_z=0.0,
    floors_config=None,
    floor_z_map=None,
    origin_offset=(0, 0)
):
    """
    Generates a heatmap grid for the floor plan.

    :param access_points: List of dicts {'x', 'y', 'z', 'model'} (Z is absolute in meters)
    :param target_z: The Z-height (absolute) of the floor we are rendering.
    :param floors_config: List of Floor objects (to look up materials).
    :param floor_z_map: Dict mapping floor_index -> absolute Z.
    :param origin_offset: Tuple (x, y) indicating the top-left coordinate of the grid relative to the scene (0,0).

    :return: Tuple (heatmap_max_grid, ap_grids_dict)
             heatmap_max_grid: 2D array of max RSSI
             ap_grids_dict: Dict {ap_name: 2D_RSSI_array}
    """

    # Grid dimensions
    grid_w = width // resolution
    grid_h = height // resolution

    # Initialize grid with a noise floor (e.g. -100 dBm)
    heatmap_max = np.full((grid_h, grid_w), -100.0)

    # Store individual grids
    ap_grids = {}

    if not access_points:
        return heatmap_max, ap_grids

    # Frequency mapping
    freq_map = {
        "2.4": 2400,
        "5": 5200,
        "6": 6000
    }
    target_freq = freq_map.get(frequency_band, 5200)

    # Coordinate grids
    off_x, off_y = origin_offset
    x_coords = np.linspace(off_x + resolution/2, off_x + width - resolution/2, grid_w)
    y_coords = np.linspace(off_y + resolution/2, off_y + height - resolution/2, grid_h)

    # Vectorized Grid
    grid_x, grid_y = np.meshgrid(x_coords, y_coords)

    # Prepare Walls for faster access (Current Floor Only)
    processed_walls = []
    for w in walls:
        mat_name = w['material']
        mat_info = materials_data.get(mat_name, {})
        if 'materials' in materials_data:
            found = next((m for m in materials_data['materials'] if m['name'] == mat_name), {})
            mat_info = found

        loss_dict = mat_info.get('loss', {})
        loss = loss_dict.get(frequency_band, loss_dict.get('5', 0.0))
        processed_walls.append((w['p1'], w['p2'], loss))

    # Prepare Floor Materials Attenuation Map
    z_to_mat = {}
    if floors_config and floor_z_map:
        for idx, z in floor_z_map.items():
            if idx < len(floors_config):
                z_to_mat[z] = floors_config[idx].material_name

    floor_materials_lookup = {}
    if 'floor_materials' in materials_data:
        for m in materials_data['floor_materials']:
            floor_materials_lookup[m['name']] = m.get('loss', {})

    def calculate_exact_floor_loss(z_start, z_end):
        loss = 0.0
        min_z = min(z_start, z_end)
        max_z = max(z_start, z_end)
        for z_level, mat_name in z_to_mat.items():
            if min_z < z_level <= max_z:
                m_loss = floor_materials_lookup.get(mat_name, {}).get(frequency_band, 15.0)
                loss += m_loss
        return loss

    # Calculate for each AP
    for ap in access_points:
        ap_model_name = ap['model']
        ap_name = ap.get('name', 'Unknown')
        ap_spec = hardware_data.get(ap_model_name)
        if not ap_spec: continue

        band_spec = ap_spec['bands'].get(frequency_band)
        if not band_spec: continue

        tx_power = band_spec['max_tx_power']
        gain_isotropic = band_spec['gain']
        pattern_data = band_spec.get('pattern', None)

        freq = target_freq # MHz

        ap_x, ap_y = ap['x'], ap['y']
        ap_z = ap.get('z', 0.0)
        mounting = ap.get('mounting', 'Ceiling')
        rotation = ap.get('rotation', 0.0)

        effective_ap_z = ap_z

        f_loss = 0.0
        if floors_config and floor_z_map:
            f_loss = calculate_exact_floor_loss(effective_ap_z, target_z)
        else:
            f_loss = (abs(effective_ap_z - target_z) / 3.0) * 15.0

        if f_loss > 100:
            continue

        receiver_z = target_z + 1.0
        dz = effective_ap_z - receiver_z # Z diff in meters (AP - Rx)

        # --- Vectorized Calculations ---
        # Grid X/Y in scene pixels
        dx_px = grid_x - ap_x
        dy_px = grid_y - ap_y

        # Convert to meters
        dx_m = dx_px / ppm
        dy_m = dy_px / ppm

        dist_2d_px_sq = dx_px*dx_px + dy_px*dy_px
        dist_2d_m = np.sqrt(dist_2d_px_sq) / ppm
        dist_3d_m = np.sqrt(dist_2d_m**2 + dz**2)

        # Antenna Pattern Gain
        current_antenna_gain = get_antenna_gain(dx_m, dy_m, dz, mounting, pattern_data, rotation)

        total_gain = gain_isotropic + current_antenna_gain

        # Vectorized Wall Loss
        current_wall_loss = np.zeros_like(grid_x)

        for w_p1, w_p2, w_loss in processed_walls:
            w1x, w1y = w_p1
            w2x, w2y = w_p2

            # Vector W1->W2
            v_wall_x = w2x - w1x
            v_wall_y = w2y - w1y

            # AP - W1
            ap_w1_x = ap_x - w1x
            ap_w1_y = ap_y - w1y

            d1 = ap_w1_x * v_wall_y - ap_w1_y * v_wall_x

            # Pixel - W1
            pix_w1_x = grid_x - w1x
            pix_w1_y = grid_y - w1y

            d2 = pix_w1_x * v_wall_y - pix_w1_y * v_wall_x

            # W1 - AP = - (AP - W1)
            w1_ap_x = -ap_w1_x
            w1_ap_y = -ap_w1_y

            # Pixel - AP
            d3 = w1_ap_x * dy_px - w1_ap_y * dx_px

            # W2 - AP
            w2_ap_x = w2x - ap_x
            w2_ap_y = w2y - ap_y

            d4 = w2_ap_x * dy_px - w2_ap_y * dx_px

            cond1 = (d1 * d2) < 0
            cond2 = (d3 * d4) < 0

            mask = np.logical_and(cond1, cond2)

            # Add loss where mask is True
            current_wall_loss += (mask * w_loss)

        # Vectorized RSSI Calculation
        dist_safe = np.maximum(dist_3d_m, 0.1)
        fspl = 20 * np.log10(dist_safe) + 20 * np.log10(freq) - 27.55

        rssi_grid = tx_power + total_gain - fspl - current_wall_loss - f_loss

        # Store individual grid
        ap_grids[ap_name] = rssi_grid

        # Update Max Heatmap
        heatmap_max = np.maximum(heatmap_max, rssi_grid)

    return heatmap_max, ap_grids

def heatmap_to_pixmap(heatmap, width, height, min_dbm=-85.0, max_dbm=-30.0):
    """
    Converts a 2D RSSI grid to a QPixmap with a color map.

    :param min_dbm: RSSI value for Red (Poor signal)
    :param max_dbm: RSSI value for Blue (Strong signal)
    """
    from PySide6.QtGui import QImage, QPixmap

    # Invert Normalization for JET Colormap
    # Standard Jet: 0=Blue, 255=Red
    # We want: Max Signal -> Blue (0), Min Signal -> Red (255)

    # Clamp first
    clamped = np.clip(heatmap, min_dbm, max_dbm)

    # Calculate normalization
    # If val = max_dbm, we want norm = 0
    # If val = min_dbm, we want norm = 1
    # Formula: (max_dbm - val) / (max_dbm - min_dbm)

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
