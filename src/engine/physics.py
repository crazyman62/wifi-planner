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
    pattern: dict,
    rotation_deg: float = 0.0
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
    :param rotation_deg: AP Rotation in degrees (Counter-Clockwise).

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
    dist_3d = np.sqrt(dx*dx + dy*dy + dz*dz)
    # Avoid division by zero
    dist_3d = np.maximum(dist_3d, 1e-6)

    # Local Angles (theta, phi)
    # We need to map Global (dx, dy, dz) to Antenna Local (az_angle, el_angle)

    # Unifi Convention:
    # Elevation: 0 = Down (Front), 90 = Horizon, 180 = Up (Back)
    # Azimuth: 0..360 around the axis.

    if mounting == "Ceiling":
        # AP is mounted on Ceiling, facing Down.
        # Local "Down" (0 deg el) corresponds to Global -Z direction.

        # Elevation Angle alpha from the "Down" vector (0, 0, -1).
        cos_theta = dz / dist_3d
        cos_theta = np.clip(cos_theta, -1.0, 1.0)
        theta_rad = np.arccos(cos_theta)
        theta_deg = np.degrees(theta_rad) # 0 to 180

        # Azimuth: Angle in XY plane.
        # phi = atan2(dy, dx)
        phi_rad = np.arctan2(dy, dx)
        phi_deg = np.degrees(phi_rad)

        # Apply Rotation to Azimuth
        # Counter-Clockwise rotation of AP means we subtract angle from coordinate?
        # If AP rotates +90 (CCW), point at 0 becomes point at -90 relative to AP.
        phi_deg = (phi_deg - rotation_deg)
        phi_deg = (phi_deg + 360) % 360

    elif mounting == "Wall":
        # Wall Mount:
        # AP is vertical. "Front" (0 deg el) points Horizontally.
        # We define "Front" based on rotation_deg.
        # If rotation=0, Front = +Y (90 deg on unit circle).
        # Wait, usually 0 deg rotation means Front = +X?
        # Let's align with standard unit circle: 0 deg = +X.
        # But earlier I assumed +Y. Let's stick to Unit Circle: 0 = +X.

        # Global Vector V = (dx, dy, -dz) (AP to Rx)

        # We need to express V in AP's local coordinate system.
        # Local Z (Boresight) = (cos(rot), sin(rot), 0)
        # Local Y (Top) = (0, 0, 1)  (Antenna Top points Global Z)
        # Local X (Right) = Cross(Y, Z)

        # Or simply: Rotate (dx, dy) by -rotation to align with +X axis.
        # Then calculate angles relative to +X.

        rot_rad = np.radians(rotation_deg)
        # Rotate vector V_xy by -rot
        # x' = x cos(-r) - y sin(-r) = x cos(r) + y sin(r)
        # y' = x sin(-r) + y cos(-r) = -x sin(r) + y cos(r)

        dx_prime = dx * np.cos(rot_rad) + dy * np.sin(rot_rad)
        dy_prime = -dx * np.sin(rot_rad) + dy * np.cos(rot_rad)

        # Now "Front" is +X axis in primed coords.

        # Elevation Angle (theta): Angle from Boresight (+X).
        # cos(theta) = x' / |V|
        # Note: dz component is still -dz.
        # |V| is same.

        # Wait, is Boresight +X?
        # Unifi Elevation 0 = Front.
        # So we check angle from +X axis (assuming Boresight is +X after rotation).
        # The vector component along Boresight is dx_prime.
        # Wait, Elevation 0 means Boresight.
        # cos(theta) = Projection / Norm.
        # If Rx is at (10, 0, 0) relative to AP, dx_prime=10. cos=1. theta=0. Correct.

        cos_theta = dx_prime / dist_3d
        cos_theta = np.clip(cos_theta, -1.0, 1.0)
        theta_rad = np.arccos(cos_theta)
        theta_deg = np.degrees(theta_rad)

        # Azimuth Angle (phi): Angle in the plane perpendicular to Boresight.
        # The perpendicular plane is Y'-Z (Global Z).
        # Vectors in this plane are (dy_prime, -dz).
        # phi = atan2(-dz, dy_prime)
        # We need to map this to 0-360.

        phi_rad = np.arctan2(-dz, dy_prime)
        phi_deg = np.degrees(phi_rad)
        phi_deg = (phi_deg + 360) % 360

    else:
        return np.zeros_like(dx)

    # Lookups
    idx_az = np.round(phi_deg).astype(int) % 360
    idx_el = np.round(theta_deg).astype(int) % 360

    g_az = az_data[idx_az]
    g_el = el_data[idx_el]

    max_az = np.max(az_data)
    max_el = np.max(el_data)
    peak_gain = max(max_az, max_el)

    # Composite Gain
    gain_grid = g_az + g_el - peak_gain

    return gain_grid
