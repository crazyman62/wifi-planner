import json
import os

def save_project(filepath, image_path, ppm, walls, access_points,
                 snap_dist=15, heatmap_min=-85, heatmap_max=-30,
                 metadata=None):
    """
    Saves the project state to a JSON file.
    """
    if metadata is None:
        metadata = {}

    data = {
        "metadata": metadata,
        "image_path": image_path,
        "pixels_per_meter": ppm,
        "walls": walls,
        "access_points": access_points,
        "settings": {
            "snap_distance": snap_dist,
            "heatmap_min_dbm": heatmap_min,
            "heatmap_max_dbm": heatmap_max
        }
    }

    with open(filepath, 'w') as f:
        json.dump(data, f, indent=4)

def load_project(filepath):
    """
    Loads the project state from a JSON file.
    """
    if not os.path.exists(filepath):
        return None

    with open(filepath, 'r') as f:
        data = json.load(f)

    return data
