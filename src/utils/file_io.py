import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from src.engine.project import Project

def save_project(file_path, project_obj):
    """
    Saves the Project object to a ZIP file (.wifi).
    The ZIP contains:
    - project.json: The serialized project data.
    - images/: Directory containing floor plan images.
    """
    try:
        # Create a temporary directory to assemble the package
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            images_dir = temp_path / "images"
            images_dir.mkdir()

            # 1. Get Project Data
            data = project_obj.to_dict()

            # 2. Process Images
            # We need to copy images to the temp dir and update paths in 'data' to be relative
            for floor_data in data.get('floors', []):
                original_path = floor_data.get('image_path')
                if original_path and os.path.exists(original_path):
                    # Generate a unique filename for the archive
                    # We use the floor number or name + extension to avoid collisions
                    # Simple approach: unique index or hash, or just basename if unique.
                    # Let's use basename but handle potential collisions if user used same image twice?
                    # Actually if same image used twice, we can just copy it once.

                    filename = os.path.basename(original_path)
                    target_path = images_dir / filename

                    # Handle duplicate filenames by prepending floor index/uuid if needed?
                    # For now, let's just copy. If overwrite, it's fine if content same.
                    # If different content same name, that's an issue.
                    # Safer: uuid-like naming or prepending floor index.

                    safe_filename = f"{floor_data['floor_number']}_{filename}"
                    target_path = images_dir / safe_filename

                    shutil.copy2(original_path, target_path)

                    # Update data with relative path
                    # We store it as "images/filename"
                    floor_data['image_path'] = f"images/{safe_filename}"
                else:
                    floor_data['image_path'] = None

            # 3. Write project.json
            json_path = temp_path / "project.json"
            with open(json_path, 'w') as f:
                json.dump(data, f, indent=4)

            # 4. Create ZIP
            with zipfile.ZipFile(file_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                # Add project.json
                zf.write(json_path, arcname="project.json")

                # Add images
                for img_file in images_dir.iterdir():
                    zf.write(img_file, arcname=f"images/{img_file.name}")

        return True
    except Exception as e:
        print(f"Error saving project: {e}")
        return False

def load_project(file_path):
    """
    Loads a Project object from a ZIP file (.wifi).
    Extracts contents to a temporary location that persists for the session.
    """
    try:
        # We need a persistent temp directory for the session so images remain accessible
        # The OS typically cleans up temp dirs on reboot, or we can manage it.
        # For simplicity, we extract to a new temp dir every time.

        extract_dir = tempfile.mkdtemp(prefix="wifi_planner_")

        with zipfile.ZipFile(file_path, 'r') as zf:
            zf.extractall(extract_dir)

        json_path = os.path.join(extract_dir, "project.json")
        if not os.path.exists(json_path):
            raise FileNotFoundError("Invalid project file: project.json missing")

        with open(json_path, 'r') as f:
            data = json.load(f)

        # Fix up image paths to be absolute paths in the temp dir
        for floor_data in data.get('floors', []):
            rel_path = floor_data.get('image_path')
            if rel_path:
                # rel_path is like "images/floor1.png"
                # We need to join with extract_dir
                abs_path = os.path.join(extract_dir, rel_path)
                # Normalize separators
                abs_path = os.path.normpath(abs_path)
                floor_data['image_path'] = abs_path

        return Project.from_dict(data)

    except Exception as e:
        print(f"Error loading project: {e}")
        return None
