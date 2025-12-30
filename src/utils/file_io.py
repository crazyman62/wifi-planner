import json
import os
from src.engine.project import Project

def save_project(file_path, project_obj):
    """
    Saves the Project object to a JSON file.
    """
    data = project_obj.to_dict()
    try:
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=4)
        return True
    except Exception as e:
        print(f"Error saving project: {e}")
        return False

def load_project(file_path):
    """
    Loads a Project object from a JSON file.
    """
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
            return Project.from_dict(data)
    except Exception as e:
        print(f"Error loading project: {e}")
        return None
