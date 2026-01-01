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

        # --- OPTIMIZATION: Shadow Casting for Wall Loss ---
        # Original logic was O(Walls * Pixels) with heavy vector math.
        # Shadow casting reduces this to O(Walls * GridResolution) via rasterization (cv2.fillPoly).

        # Scratch buffer for shadow polygons (reused)
        shadow_mask = np.zeros((grid_h, grid_w), dtype=np.uint8)

        # Pre-calculate AP position in grid coordinates
        ap_gx = (ap_x - off_x) / resolution
        ap_gy = (ap_y - off_y) / resolution

        # Scene bounds for projection (in grid coordinates)
        # 0,0 is top left. grid_w, grid_h is bottom right.

        def project_to_bounds(origin_x, origin_y, target_x, target_y, w, h):
            """Project ray from origin through target to the box boundary"""
            dx = target_x - origin_x
            dy = target_y - origin_y

            if dx == 0 and dy == 0:
                return target_x, target_y

            # Intersections with 4 lines: x=0, x=w, y=0, y=h
            # t values for each
            t_candidates = []

            if dx != 0:
                t1 = (0 - origin_x) / dx
                if t1 > 0: t_candidates.append(t1)
                t2 = (w - origin_x) / dx
                if t2 > 0: t_candidates.append(t2)

            if dy != 0:
                t3 = (0 - origin_y) / dy
                if t3 > 0: t_candidates.append(t3)
                t4 = (h - origin_y) / dy
                if t4 > 0: t_candidates.append(t4)

            if not t_candidates:
                return target_x, target_y # Should not happen if target is inside/near box

            # We want the smallest t that is >= 1 (since target is at t=1)
            # Actually target is wall endpoint. We want to extend BEYOND wall.
            # So we want smallest t > 1?
            # If wall is outside box, t could be < 1?
            # Let's just take the smallest t that puts us on the boundary and is "forward".
            # The ray is P -> W. We want points "behind" W. So t >= 1.

            best_t = None
            for t in t_candidates:
                # Tolerance for float
                if t >= 0.999:
                    if best_t is None or t < best_t:
                        best_t = t

            if best_t is None:
                # Maybe wall is already outside?
                # Just return target
                return target_x, target_y

            return origin_x + dx * best_t, origin_y + dy * best_t

        for w_p1, w_p2, w_loss in processed_walls:
            # Wall coordinates in grid space
            w1x = (w_p1[0] - off_x) / resolution
            w1y = (w_p1[1] - off_y) / resolution
            w2x = (w_p2[0] - off_x) / resolution
            w2y = (w_p2[1] - off_y) / resolution

            # Project W1 and W2 to boundaries
            p1_proj = project_to_bounds(ap_gx, ap_gy, w1x, w1y, grid_w, grid_h)
            p2_proj = project_to_bounds(ap_gx, ap_gy, w2x, w2y, grid_w, grid_h)

            # Construct Polygon: W1, W2, P2_proj, P1_proj
            # Ensure integer coordinates for cv2
            pts = np.array([
                [w1x, w1y],
                [w2x, w2y],
                [p2_proj[0], p2_proj[1]],
                [p1_proj[0], p1_proj[1]]
            ], dtype=np.int32)

            # Reset mask
            shadow_mask.fill(0)

            # Draw shadow
            # Note: fillPoly expects list of polygons
            cv2.fillPoly(shadow_mask, [pts], 1)

            # Accumulate loss
            # Optimization: Use mask to add scalar
            # current_wall_loss[shadow_mask == 1] += w_loss
            # Vectorized add with mask
            current_wall_loss += (shadow_mask * w_loss)

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
