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
    frequency_band="5", # "2.4", "5", or "6"
    resolution=10,
    target_z=0.0,
    floors_config=None,
    floor_z_map=None
):
    """
    Generates a heatmap grid for the floor plan.

    :param access_points: List of dicts {'x', 'y', 'z', 'model'} (Z is absolute in meters)
    :param target_z: The Z-height (absolute) of the floor we are rendering.
    :param floors_config: List of Floor objects (to look up materials).
    :param floor_z_map: Dict mapping floor_index -> absolute Z.
    """

    # Grid dimensions
    grid_w = width // resolution
    grid_h = height // resolution

    # Initialize grid with a noise floor (e.g. -100 dBm)
    heatmap = np.full((grid_h, grid_w), -100.0)

    if not access_points:
        return heatmap

    # Frequency mapping
    freq_map = {
        "2.4": 2400,
        "5": 5200,
        "6": 6000
    }
    target_freq = freq_map.get(frequency_band, 5200)

    # Coordinate grids
    # We want the center of each grid cell
    x_coords = np.linspace(resolution/2, width - resolution/2, grid_w)
    y_coords = np.linspace(resolution/2, height - resolution/2, grid_h)

    # Prepare Walls for faster access (Current Floor Only)
    processed_walls = []
    for w in walls:
        mat_name = w['material']
        mat_info = materials_data.get(mat_name, {}) # This might need to look in 'materials' key if raw dict passed
        # Handle if materials_data is the full dict
        if 'materials' in materials_data:
            # Find in list
            found = next((m for m in materials_data['materials'] if m['name'] == mat_name), {})
            mat_info = found

        # Fetch loss for specific band
        loss_dict = mat_info.get('loss', {})
        loss = loss_dict.get(frequency_band, loss_dict.get('5', 0.0))
        processed_walls.append((w['p1'], w['p2'], loss))

    # Prepare Floor Materials Attenuation Map
    floor_loss_val = 15.0 # Default

    # Better Implementation of Floor Loss inside the loop using passed config
    # We need to map Z back to material.
    z_to_mat = {}
    if floors_config and floor_z_map:
        # Assuming floor_z_map keys correspond to floors_config indices
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

        # Check against all known floor Z levels
        # If a floor level Z is within (min_z, max_z], we add loss.
        # The 'Floor 1' (Z=0) is usually base. We don't cross it unless going to -1.
        # So we check if Z > min_z and Z <= max_z.

        for z_level, mat_name in z_to_mat.items():
            if min_z < z_level <= max_z:
                # Add loss for this material
                m_loss = floor_materials_lookup.get(mat_name, {}).get(frequency_band, 15.0)
                loss += m_loss
        return loss

    # Calculate for each AP
    for ap in access_points:
        ap_model_name = ap['model']
        ap_spec = hardware_data.get(ap_model_name)
        if not ap_spec: continue

        band_spec = ap_spec['bands'].get(frequency_band)
        if not band_spec: continue

        tx_power = band_spec['max_tx_power']
        gain = band_spec['gain']
        freq = target_freq # MHz

        ap_x, ap_y = ap['x'], ap['y']
        ap_z = ap.get('z', 0.0)

        # Apply Zone Height / Ceiling Height Offset
        # We need the floor index of this AP to lookup its ceiling/zones.
        # The AP dict has 'z' which is slab level.
        # But we also passed 'floor_z_map'. We can deduce index.
        # Or easier: Pass 'ceiling_offset' in the AP dict from MainWindow?
        # MainWindow knows the floor index of the AP and can lookup zones.
        # Let's assume AP dict now has 'effective_z' or we calculate it here if we passed Zones?
        # Passing zones for all floors is heavy.
        # BETTER: Use 'z' as the *actual* 3D Z of the AP (Slab + Ceiling/Zone).
        # We will update MainWindow to calculate this 'z' correctly before calling this function.

        effective_ap_z = ap_z

        # Floor Loss is constant for this AP -> Target Floor pair
        # (Assuming flat floors)
        f_loss = 0.0
        if floors_config and floor_z_map:
            # We need the slab Z, not the AP Z (which might be suspended).
            # We can find the closest floor Z below the AP Z?
            # Or assume floor_z_map values are the slab Zs.
            # MainWindow should pass 'slab_z' separately if needed, but using AP Z for range is approx OK
            # as long as we don't cross a floor slab *within* the ceiling space (unlikely).
            f_loss = calculate_exact_floor_loss(effective_ap_z, target_z)
        else:
            # Fallback if config missing
            f_loss = (abs(effective_ap_z - target_z) / 3.0) * 15.0

        # Optimization: If f_loss is huge (e.g. > 100dB), skip
        if f_loss > 100:
            continue

        # Vertical distance component squared
        # Receiver is at target_z + 1.0m (User height) approx?
        # Let's assume Receiver is at target_z + 1.0.
        receiver_z = target_z + 1.0
        dz_sq = (effective_ap_z - receiver_z) ** 2

        # 2D Grid Loop
        for r in range(grid_h):
            for c in range(grid_w):
                cell_x = x_coords[c]
                cell_y = y_coords[r]

                dx = cell_x - ap_x
                dy = cell_y - ap_y
                dist_2d_px_sq = dx*dx + dy*dy
                dist_2d_m = np.sqrt(dist_2d_px_sq) / ppm

                # 3D Distance
                dist_3d_m = np.sqrt(dist_2d_m**2 + dz_sq)

                # Wall Loss
                current_wall_loss = 0.0
                # Optim: dist check
                if dist_2d_px_sq > 1:
                    for w_p1, w_p2, w_loss in processed_walls:
                         if segments_intersect((ap_x, ap_y), (cell_x, cell_y), w_p1, w_p2):
                            current_wall_loss += w_loss

                rssi = calculate_log_distance_path_loss(
                    tx_power_dbm=tx_power,
                    tx_gain_dbi=gain,
                    frequency_mhz=freq,
                    distance_meters=dist_3d_m,
                    wall_loss_db=current_wall_loss,
                    floor_loss_db=f_loss
                )

                if rssi > heatmap[r, c]:
                    heatmap[r, c] = rssi

    return heatmap

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
