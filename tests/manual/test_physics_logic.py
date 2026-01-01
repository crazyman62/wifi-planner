import unittest
import numpy as np
from src.engine.physics import get_antenna_gain

class TestPhysicsLogic(unittest.TestCase):
    def test_antenna_gain_ceiling_mount(self):
        # Mock Pattern: High gain at 0 deg el (Front/Down), Low gain at 180 deg el (Back/Up)
        # Azimuth uniform.
        pattern = {
            'azimuth': [0.0] * 360,
            'elevation': [0.0] * 360
        }
        # Set elevation 0 to 10.0, elevation 180 to -10.0
        pattern['elevation'][0] = 10.0
        pattern['elevation'][180] = -10.0

        # Case 1: Directly below AP (dz > 0)
        # AP at Z=3, Rx at Z=1 -> dz = 2
        dx = np.array([0.0])
        dy = np.array([0.0])
        dz = 2.0

        gain = get_antenna_gain(dx, dy, dz, "Ceiling", pattern)
        # Should be close to Elevation 0 (10.0) + Azimuth 0 (0.0) - Max(10.0) = 0.0 relative?
        # Logic in physics.py: g_az + g_el - peak.
        # peak = max(0, 10) = 10.
        # g_az[0] = 0.
        # g_el[0] = 10.
        # Result = 0 + 10 - 10 = 0.
        # This seems to normalize it to 0.
        # If the file data was 10, and peak was 10, we get 0 delta.
        # If we add this to isotropic gain (say 5), total is 5. Correct.

        self.assertAlmostEqual(gain[0], 0.0, places=1)

        # Case 2: Above AP (Through ceiling)
        # AP at Z=3, Rx at Z=5 -> dz = -2
        dx = np.array([0.0])
        dy = np.array([0.0])
        dz = -2.0 # Negative means AP is BELOW Rx.
        # Vector AP->Rx has Z component (-dz) = 2. (Up)
        # Angle from Down (0,0,-1) to (0,0,2) is 180 deg.

        gain = get_antenna_gain(dx, dy, dz, "Ceiling", pattern)
        # Should use Elevation 180 (-10.0).
        # g_az[0] = 0.
        # g_el[180] = -10.
        # Peak = 10.
        # Result = 0 + (-10) - 10 = -20.
        self.assertAlmostEqual(gain[0], -20.0, places=1)

    def test_antenna_gain_wall_mount(self):
        # Mock Pattern: Directional
        # El 0 (Front) = 10. El 180 (Back) = -20.
        pattern = {
            'azimuth': [0.0] * 360,
            'elevation': [0.0] * 360
        }
        pattern['elevation'][0] = 10.0
        pattern['elevation'][180] = -20.0

        # Wall Mount: Facing +Y.

        # Case 1: Rx in front (along +Y)
        dx = np.array([0.0])
        dy = np.array([5.0]) # 5m in front
        dz = 0.0 # Same height

        # Vector AP->Rx = (0, 5, 0).
        # Elevation Angle (from Boresight +Y) should be 0.

        gain = get_antenna_gain(dx, dy, dz, "Wall", pattern)
        # g_el[0] = 10.
        # Result = 0 + 10 - 10 = 0.
        self.assertAlmostEqual(gain[0], 0.0, places=1)

        # Case 2: Rx behind (along -Y)
        dx = np.array([0.0])
        dy = np.array([-5.0])
        dz = 0.0

        # Angle from Boresight should be 180.
        gain = get_antenna_gain(dx, dy, dz, "Wall", pattern)
        # g_el[180] = -20.
        # Result = 0 + (-20) - 10 = -30.
        self.assertAlmostEqual(gain[0], -30.0, places=1)

if __name__ == '__main__':
    unittest.main()
