import numpy as np

def calculate_log_distance_path_loss(
    tx_power_dbm: float,
    tx_gain_dbi: float,
    frequency_mhz: float,
    distance_meters: float,
    wall_loss_db: float = 0.0,
    floor_loss_db: float = 0.0
) -> float:
    """
    Calculates RSSI using the Log-Distance Path Loss Model.
    Formula: RSSI = P_tx + G_tx - FSPL - L_walls - L_floors

    :param tx_power_dbm: Transmit power in dBm
    :param tx_gain_dbi: Antenna gain in dBi
    :param frequency_mhz: Frequency in MHz
    :param distance_meters: 3D Distance in meters
    :param wall_loss_db: Cumulative wall loss in dB
    :param floor_loss_db: Cumulative floor penetration loss in dB
    :return: RSSI in dBm
    """
    if distance_meters <= 0:
        distance_meters = 0.1

    # Free Space Path Loss (FSPL) in dB
    # FSPL = 20log10(d) + 20log10(f) - 27.55 (constant for meters and MHz)
    fspl = 20 * np.log10(distance_meters) + 20 * np.log10(frequency_mhz) - 27.55

    rssi = tx_power_dbm + tx_gain_dbi - fspl - wall_loss_db - floor_loss_db
    return rssi

def segments_intersect(p1, p2, p3, p4):
    """
    Checks if line segment p1-p2 intersects with line segment p3-p4.
    p1, p2, p3, p4 are tuples or arrays of (x, y) coordinates.
    Uses vector cross product method.
    """
    def cross_product(a, b):
        return a[0] * b[1] - a[1] * b[0]

    def subtract(a, b):
        return (a[0] - b[0], a[1] - b[1])

    def direction(a, b, c):
        return cross_product(subtract(c, a), subtract(b, a))

    def on_segment(a, b, c):
        return (min(a[0], b[0]) <= c[0] <= max(a[0], b[0]) and
                min(a[1], b[1]) <= c[1] <= max(a[1], b[1]))

    d1 = direction(p3, p4, p1)
    d2 = direction(p3, p4, p2)
    d3 = direction(p1, p2, p3)
    d4 = direction(p1, p2, p4)

    # General case: intersecting if signs differ
    if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and \
       ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)):
        return True

    # Special cases: collinear points
    if d1 == 0 and on_segment(p3, p4, p1): return True
    if d2 == 0 and on_segment(p3, p4, p2): return True
    if d3 == 0 and on_segment(p1, p2, p3): return True
    if d4 == 0 and on_segment(p1, p2, p4): return True

    return False

def get_antenna_gain(
    dx: np.ndarray,
    dy: np.ndarray,
    dz: float,
    mounting: str,
    pattern: dict
) -> np.ndarray:
    """
    Calculates the antenna gain for each point in the grid based on the 3D pattern.

    :param dx: Grid of X distances from AP (Pixel coordinates, already scaled/centered?)
               No, usually meters?
               Wait, heatmap.py passes grid_x - ap_x. This is in pixels if not scaled.
               BUT heatmap.py divides by ppm to get meters.
               Here we expect dx, dy, dz in METERS.
    :param dy: Grid of Y distances from AP (Meters)
    :param dz: Z distance (AP_Z - Receiver_Z) in Meters.
               Note: Positive dz means AP is ABOVE receiver (if Z grows up).
               Let's assume standard physics: Z axis points UP.
               AP at Z=3, Receiver at Z=1. dz = 2.
    :param mounting: "Ceiling" or "Wall"
    :param pattern: Dictionary with 'azimuth' and 'elevation' lists (360 floats each).
                    If None, returns 0.0 (isotropic).

    Returns: Grid of Gain values in dBi.
    """
    if not pattern:
        return np.zeros_like(dx)

    az_data = np.array(pattern.get('azimuth', [0]*360))
    el_data = np.array(pattern.get('elevation', [0]*360))

    # Calculate Spherical Coordinates relative to AP Local Frame
    # Global Frame: X, Y (Horizontal), Z (Vertical Up)

    # Distance in 3D
    dist_xy = np.sqrt(dx*dx + dy*dy)
    # dist_3d = np.sqrt(dist_xy*dist_xy + dz*dz) # Not strictly needed for angles

    # Local Angles (theta, phi)
    # We need to map Global (dx, dy, dz) to Antenna Local (az_angle, el_angle)

    # Unifi Convention:
    # Elevation: 0 = Down (Front), 90 = Horizon, 180 = Up (Back)
    # Azimuth: 0..360 around the axis.

    if mounting == "Ceiling":
        # AP is mounted on Ceiling, facing Down.
        # Local "Down" (0 deg el) corresponds to Global -Z direction.
        # Local "Horizon" (90 deg el) corresponds to Global XY plane.

        # Calculate Elevation Angle alpha from the "Down" vector (0, 0, -1).
        # Vector V = (dx, dy, -dz)  (Vector from AP to Receiver)
        # Note: input dz is (AP_Z - Receiver_Z).
        # If AP is at 3m, Rx at 1m, AP->Rx vector has z = -2.
        # But we passed dz = 2. So Vector Z component is -dz.

        # Angle from (0,0,-1) to (dx, dy, -dz).
        # cos(alpha) = (V . Down) / (|V| * |Down|)
        # V . Down = (dx*0 + dy*0 + (-dz)*(-1)) = dz
        # |V| = sqrt(dx^2 + dy^2 + dz^2)
        # alpha = acos(dz / |V|)

        # This gives 0 to 90 degrees if dz > 0 (AP above Rx).
        # If dz < 0 (AP below Rx), dz is negative. acos will be > 90.
        # This matches the Unifi convention perfectly:
        # Below AP -> Angle ~ 0.
        # Horizontal -> Angle 90.
        # Above AP -> Angle ~ 180.

        dist_3d = np.sqrt(dx*dx + dy*dy + dz*dz)
        # Avoid division by zero
        dist_3d = np.maximum(dist_3d, 1e-6)

        cos_theta = dz / dist_3d
        # Clip for safety
        cos_theta = np.clip(cos_theta, -1.0, 1.0)
        theta_rad = np.arccos(cos_theta)
        theta_deg = np.degrees(theta_rad) # 0 to 180

        # Azimuth: Angle in XY plane.
        # phi = atan2(dy, dx)
        phi_rad = np.arctan2(dy, dx)
        phi_deg = np.degrees(phi_rad)
        phi_deg = (phi_deg + 360) % 360

    elif mounting == "Wall":
        # Wall Mount:
        # AP is vertical. "Front" (0 deg el) points Horizontally.
        # Which way? Let's assume +Y for now (User faces North).
        # Ideally we need a rotation angle.
        # If mounting on "North Wall", AP faces South (-Y).
        # If mounting on "South Wall", AP faces North (+Y).
        # Without explicit rotation, let's assume default orientation is Facing +Y (North).
        # Or maybe +X?
        # Let's assume +Y.

        # Local "Front" (0 el) = Global +Y (0, 1, 0)
        # Local "Up" (top of unit) = Global +Z (0, 0, 1) ?
        # Wait, for wall mount, the "Azimuth" plane is the vertical plane parallel to wall?
        # No, Azimuth is usually "around the equator".
        # For a saucer on wall:
        # The "Front" is the main lobe.
        # The "Equator" (Azimuth scan) is the plane containing Top/Bottom/Left/Right.

        # Let's treat the transform as a rotation of the Ceiling coord system.
        # Ceiling: Local Z_ant = Global -Z.
        # Wall: Local Z_ant = Global +Y (Front points Y).
        # Local X_ant = Global X.
        # Local Y_ant = Global Z (Top points Z).

        # So we map Global (dx, dy, dz) to Local (x', y', z').
        # x' = dx
        # y' = dz  (Local Y corresponds to Global Z)
        # z' = -dy (Local Z corresponds to Global -Y? No, if Front is +Y, then Vector TO Rx relative to AP...)

        # Vector V = (dx, dy, -dz) (AP to Rx).
        # Let's project V onto Antenna Axes.
        # Antenna Axis Z (Boresight) = (0, 1, 0) [Global]
        # Antenna Axis Y (Top) = (0, 0, 1) [Global]
        # Antenna Axis X (Right) = (1, 0, 0) [Global]

        # Elevation Angle (theta): Angle from Boresight.
        # cos(theta) = (V . Boresight) / |V|
        # V . (0,1,0) = dy.
        # theta = acos(dy / |V|)
        # Note: dy is (Rx_y - AP_y).
        # If Rx is in front (+Y), dy > 0 -> theta < 90.
        # If Rx is behind (-Y), dy < 0 -> theta > 90.

        # Azimuth Angle (phi): Angle in the plane perpendicular to Boresight (X-Z plane).
        # Vector projected on X-Z plane: (dx, -dz).
        # phi = atan2(-dz, dx).

        dist_3d = np.sqrt(dx*dx + dy*dy + dz*dz)
        dist_3d = np.maximum(dist_3d, 1e-6)

        # Assume Facing +Y
        # If we wanted rotation, we'd rotate dx, dy first.

        # Use dy for elevation check (Front/Back)
        # Note: "Elevation" in pattern means angle from Boresight.

        # Wait, Unifi pattern:
        # 0 deg = Front. 90 = Horizon (Side). 180 = Back.
        # This matches acos(projection onto normal).

        # But wait, dz in Global is (AP_Z - Rx_Z). Vector AP->Rx has z component (Rx_Z - AP_Z) = -dz.

        # V = (dx, dy, -dz)
        # Boresight = (0, 1, 0) -> dy

        cos_theta = dy / dist_3d
        cos_theta = np.clip(cos_theta, -1.0, 1.0)
        theta_rad = np.arccos(cos_theta)
        theta_deg = np.degrees(theta_rad)

        # Azimuth: Angle around the Boresight axis.
        # Plane is X-Z (Global).
        # Project V onto X-Z: (dx, -dz).
        # phi = atan2(-dz, dx)
        phi_rad = np.arctan2(-dz, dx)
        phi_deg = np.degrees(phi_rad)
        phi_deg = (phi_deg + 360) % 360

    else:
        return np.zeros_like(dx)

    # Lookups
    # Indices must be integers
    idx_az = np.round(phi_deg).astype(int) % 360
    idx_el = np.round(theta_deg).astype(int) % 360 # Usually el is 0-180?
    # Unifi El patterns are 0-360 in file?
    # Usually files cover full 360. 0-180 is one side, 180-360 is other?
    # Unifi docs: "Radius represents elevation... 0 straight under... 90 horizon".
    # Usually it's symmetric or defined fully.
    # Our file has 360 lines for elevation.
    # We will assume 0-360 mapping.

    # Wait, if we use separable approximation: Gain = G_az(phi) + G_el(theta) - G_peak?
    # Or just use the dominant cut based on angle?
    # Usually: Total Gain = G_el(theta) + (G_az(phi) - G_az_avg) ?
    # Simple approach: Gain = G_az(phi) + G_el(theta) ?
    # But max gain is already included in both? That would double count.

    # "The patterns are reciprocal...".
    # Standard approximation for separable patterns (HV cuts):
    # G(theta, phi) approx G_theta(theta) + G_phi(phi) - G_max
    # Assuming both cuts pass through the maximum.
    # Let's check max of the arrays.

    g_az = az_data[idx_az]
    g_el = el_data[idx_el]

    # We need to know G_max to normalize.
    # Let's assume the max of the arrays is the peak gain specified in spec.
    # Or we can compute it on the fly (fast for 360 size).

    # Optimization: Calculate max once per AP?
    # For now, calculate max of the loaded arrays.
    max_az = np.max(az_data)
    max_el = np.max(el_data)
    # They should be roughly equal (the peak gain).
    peak_gain = max(max_az, max_el)

    # Composite Gain
    # This formula is common for H/V cut approximation.
    gain_grid = g_az + g_el - peak_gain

    return gain_grid
