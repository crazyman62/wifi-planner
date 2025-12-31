import json
import os

class Floor:
    def __init__(self, name, number, material_name, image_path=None):
        self.name = name
        self.floor_number = number # Integer, can be negative for basements
        self.material_name = material_name
        self.image_path = image_path

        # Geometry / Physics
        self.ceiling_height = 3.0 # Default meters
        self.pixels_per_meter = 1.0

        # Alignment (Transform relative to Project Origin)
        self.x_offset = 0.0
        self.y_offset = 0.0
        self.rotation = 0.0 # Degrees
        self.scale_factor = 1.0 # Image specific scaling (if images have different resolutions)

        # Content
        self.walls = [] # List of dicts or objects
        self.access_points = [] # List of dicts or objects
        self.regions = [] # List of regions (e.g. for ceiling height overrides)

    def to_dict(self):
        return {
            'name': self.name,
            'floor_number': self.floor_number,
            'material_name': self.material_name,
            'image_path': self.image_path,
            'ceiling_height': self.ceiling_height,
            'pixels_per_meter': self.pixels_per_meter,
            'x_offset': self.x_offset,
            'y_offset': self.y_offset,
            'rotation': self.rotation,
            'scale_factor': self.scale_factor,
            'walls': self.walls,
            'access_points': self.access_points,
            'regions': self.regions
        }

    @classmethod
    def from_dict(cls, data):
        floor = cls(
            data.get('name', 'Floor'),
            data.get('floor_number', 1),
            data.get('material_name', 'Concrete'),
            data.get('image_path')
        )
        floor.ceiling_height = data.get('ceiling_height', 3.0)
        floor.pixels_per_meter = data.get('pixels_per_meter', 1.0)
        floor.x_offset = data.get('x_offset', 0.0)
        floor.y_offset = data.get('y_offset', 0.0)
        floor.rotation = data.get('rotation', 0.0)
        floor.scale_factor = data.get('scale_factor', 1.0)
        floor.walls = data.get('walls', [])
        floor.access_points = data.get('access_points', [])
        floor.regions = data.get('regions', [])
        return floor


class Project:
    def __init__(self, name="New Project"):
        self.name = name
        self.floors = [] # List of Floor objects
        self.active_floor_index = -1

        # Global Settings
        self.snap_threshold = 15
        self.heatmap_min_dbm = -85
        self.heatmap_max_dbm = -30
        self.next_ap_id = 1

    def add_floor(self, floor):
        self.floors.append(floor)
        # Note: We do NOT sort floors by floor_number anymore.
        # Order is determined by insertion (and thus tab order).
        # self.floors.sort(key=lambda f: f.floor_number)

    def get_floor(self, index):
        if 0 <= index < len(self.floors):
            return self.floors[index]
        return None

    def to_dict(self):
        return {
            'name': self.name,
            'floors': [f.to_dict() for f in self.floors],
            'next_ap_id': self.next_ap_id,
            'settings': {
                'snap_threshold': self.snap_threshold,
                'heatmap_min_dbm': self.heatmap_min_dbm,
                'heatmap_max_dbm': self.heatmap_max_dbm
            }
        }

    @classmethod
    def from_dict(cls, data):
        project = cls(data.get('name', 'New Project'))
        project.next_ap_id = data.get('next_ap_id', 1)

        settings = data.get('settings', {})
        project.snap_threshold = settings.get('snap_threshold', 15)
        project.heatmap_min_dbm = settings.get('heatmap_min_dbm', -85)
        project.heatmap_max_dbm = settings.get('heatmap_max_dbm', -30)

        for f_data in data.get('floors', []):
            project.add_floor(Floor.from_dict(f_data))

        return project
