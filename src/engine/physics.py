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
