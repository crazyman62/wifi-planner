import unittest
import numpy as np
from src.engine.physics import calculate_log_distance_path_loss, segments_intersect

class TestPhysicsEngine(unittest.TestCase):

    def test_fspl_calculation(self):
        # Known value check
        # At 1 meter, 2400 MHz:
        # FSPL = 20log10(1) + 20log10(2400) - 27.55
        #      = 0 + 67.60 - 27.55 = 40.05 dB
        # RSSI = Tx(20) + Gain(0) - 40.05 = -20.05
        rssi = calculate_log_distance_path_loss(
            tx_power_dbm=20,
            tx_gain_dbi=0,
            frequency_mhz=2400,
            distance_meters=1.0,
            wall_loss_db=0.0
        )
        self.assertAlmostEqual(rssi, -20.05, places=1)

    def test_wall_loss_subtraction(self):
        rssi_no_wall = calculate_log_distance_path_loss(20, 0, 2400, 10, 0)
        rssi_with_wall = calculate_log_distance_path_loss(20, 0, 2400, 10, 10)
        self.assertAlmostEqual(rssi_with_wall, rssi_no_wall - 10, places=5)

    def test_segments_intersect_cross(self):
        # Simple cross
        p1, p2 = (0, 0), (10, 10)
        p3, p4 = (0, 10), (10, 0)
        self.assertTrue(segments_intersect(p1, p2, p3, p4))

    def test_segments_intersect_parallel_no_touch(self):
        p1, p2 = (0, 0), (10, 0)
        p3, p4 = (0, 5), (10, 5)
        self.assertFalse(segments_intersect(p1, p2, p3, p4))

    def test_segments_intersect_touching_tip(self):
        # Touching at tip (5,5)
        p1, p2 = (0, 0), (5, 5)
        p3, p4 = (5, 5), (10, 0)
        self.assertTrue(segments_intersect(p1, p2, p3, p4))

    def test_segments_intersect_no_intersect(self):
        p1, p2 = (0, 0), (5, 5)
        p3, p4 = (6, 6), (10, 10)
        self.assertFalse(segments_intersect(p1, p2, p3, p4))

if __name__ == '__main__':
    unittest.main()
