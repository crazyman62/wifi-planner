import math
from PySide6.QtCore import QPointF

def calculate_radio_configs(project, hardware_data):
    """
    Recalculates Channel and Power settings for all APs in the project
    that are set to 'Auto' and not manually locked.

    This is a simplified implementation:
    1. Collect all APs (global coords).
    2. Build interference graph (distance based).
    3. Assign channels to minimize overlap.
    4. Adjust power based on neighbor density.
    """

    # 1. Flatten all APs with global coordinates
    # We need to access floor offsets.

    all_aps = []

    # Pre-calculate floor Z and offsets
    sorted_floors = sorted(enumerate(project.floors), key=lambda x: x[1].floor_number)
    floor_z_map = {}
    current_z = 0.0
    for idx, f in sorted_floors:
        floor_z_map[idx] = current_z
        current_z += f.ceiling_height

    for idx, floor in enumerate(project.floors):
        # We need to access the AP objects themselves to update them.
        # But wait, the AP objects are in the UI (QGraphicsItems) or in the Floor data (dicts)?
        # The prompt says "This application should do the calculations when an AP is moved".
        # If we are in the UI, we update the items.
        # If we are saving, we update the data.
        # The `project` object has `floors` which have `access_points` as dicts OR objects?
        # In `MainWindow._sync_canvas_to_floor`, we save them as dicts.
        # But while editing, we manipulate Items.
        # If this function is called from MainWindow, we should probably pass the ITEMS from the scene?
        # But we have multiple scenes (tabs).
        # We need a way to access all AP items across all tabs.
        pass

    # Re-thinking strategy:
    # MainWindow has access to all tabs.
    # Let's pass a list of AP Objects (wrappers) that contain:
    # - Global X, Y, Z
    # - Reference to the actual data object (AccessPointItem or dict) to update.
    # - Current Radio Config

    pass

def run_auto_planner(main_window):
    """
    Main entry point called from UI.
    Iterates all tabs to find AP Items.
    """

    # 1. Collect APs
    aps_nodes = []

    # Calculate global offsets
    # sorted_floors logic duplicated from main_window
    sorted_floors = sorted(enumerate(main_window.project.floors), key=lambda x: x[1].floor_number)
    floor_z_map = {}
    current_z = 0.0
    for idx, f in sorted_floors:
        floor_z_map[idx] = current_z
        current_z += f.ceiling_height

    from src.gui.items import AccessPointItem

    for i in range(main_window.tabs.count()):
        canvas = main_window.tabs.widget(i)
        if not canvas: continue

        floor = main_window.project.get_floor(i)
        z_base = floor_z_map.get(i, 0.0)

        # Pixmap transform?
        # Items are parented to pixmap.
        # scenePos() returns Global Scene Coords.
        # We treat Scene Coords as "Real World" (scaled by pixels_per_meter).
        # Wait, pixels_per_meter is per floor.
        # If floors have different scales, we need to convert to Meters.

        scale = floor.pixels_per_meter
        if scale <= 0: scale = 1.0 # Avoid div zero

        for item in canvas.scene.items():
            if isinstance(item, AccessPointItem):
                pos = item.scenePos()

                # Convert to Meters for Physics
                mx = pos.x() / scale
                my = pos.y() / scale
                mz = z_base + floor.ceiling_height # Simple approx

                aps_nodes.append({
                    'item': item,
                    'x': mx, 'y': my, 'z': mz,
                    'floor_idx': i
                })

    # 2. Run Logic per Band
    for band in ['2.4', '5', '6']:
        _optimize_band(aps_nodes, band)

def _optimize_band(nodes, band):
    # Filter nodes that have this band enabled (always true for now)
    # and are set to 'Auto' and not manual.

    # Available Channels
    if band == '2.4':
        channels = [1, 6, 11]
    elif band == '5':
        channels = [36, 40, 44, 48, 149, 153, 157, 161] # Simplified list
    else:
        channels = [1, 5, 9, 13, 17, 21]

    # Build Graph
    # Distance threshold for interference (e.g. 15 meters)
    threshold = 15.0

    # Simple Greedy Color
    # Sort by density (degree)?

    # Calc neighbors
    for n in nodes:
        n['neighbors'] = []

    for i in range(len(nodes)):
        for j in range(i+1, len(nodes)):
            n1 = nodes[i]
            n2 = nodes[j]
            dist = math.sqrt((n1['x']-n2['x'])**2 + (n1['y']-n2['y'])**2 + (n1['z']-n2['z'])**2)

            if dist < threshold:
                n1['neighbors'].append(n2)
                n2['neighbors'].append(n1)

    # Assign Channels
    # Only for Auto items
    for n in nodes:
        item = n['item']
        config = item.radios.get(band, {})

        if config.get('manual', False):
            continue # Skip locked

        if config.get('channel') != 'Auto' and isinstance(config.get('channel'), int):
             # User set specific channel but didn't lock?
             # Prompt says: "UNLESS it has been manually modified by the user".
             # We treat non-Auto as modified.
             continue

        # Pick best channel
        used_channels = set()
        for neighbor in n['neighbors']:
            n_item = neighbor['item']
            n_conf = n_item.radios.get(band, {})
            ch = n_conf.get('channel')
            if ch != 'Auto':
                used_channels.add(ch)

        # Pick first available
        chosen = channels[0]
        for c in channels:
            if c not in used_channels:
                chosen = c
                break

        # Update Item
        # AccessPointItem radios dict
        item.radios[band]['channel'] = chosen

    # Assign Power
    # Density based
    for n in nodes:
        item = n['item']
        config = item.radios.get(band, {})

        if config.get('manual', False):
            continue

        if config.get('power') != 'Auto':
            continue

        # Count close neighbors (e.g. < 8m)
        close_neighbors = 0
        for neighbor in n['neighbors']:
            dist = math.sqrt((n['x']-neighbor['x'])**2 + (n['y']-neighbor['y'])**2 + (n['z']-neighbor['z'])**2)
            if dist < 8.0:
                close_neighbors += 1

        if close_neighbors >= 3:
            pwr = "Low"
        elif close_neighbors >= 1:
            pwr = "Medium"
        else:
            pwr = "High"

        item.radios[band]['power'] = pwr
