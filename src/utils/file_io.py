import json
import os

def save_project(filepath, image_path, ppm, walls, access_points):
    """
    Saves the project state to a JSON file.
    """
    data = {
        "image_path": image_path,
        "pixels_per_meter": ppm,
        "walls": walls,
        "access_points": access_points
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
