import json
import os
import urllib.request
import zipfile
import io
import glob
import shutil
import ssl

# Mapping from hardware.json Model Name to URL Key
MODEL_URL_MAP = {
    "UniFi U7 Pro Max": "https://help-center-assets.svc.ui.com/hc/unifi-antenna-files/U7-Pro-Max.zip",
    "UniFi U7 Pro": "https://help-center-assets.svc.ui.com/hc/unifi-antenna-files/U7-Pro.zip",
    "UniFi U7 Pro Wall": "https://help-center-assets.svc.ui.com/hc/unifi-antenna-files/U7-Pro-Wall.zip",
    "UniFi U7 In-Wall": "https://help-center-assets.svc.ui.com/hc/unifi-antenna-files/U7-IW.zip",
    "UniFi U7 Lite": "https://help-center-assets.svc.ui.com/hc/unifi-antenna-files/U7-Lite.zip",
    "UniFi U7 Outdoor": "https://help-center-assets.svc.ui.com/hc/unifi-antenna-files/U7-Outdoor.zip",
    "UniFi U6 Enterprise": "https://help-center-assets.svc.ui.com/hc/unifi-antenna-files/U6-Enterprise.zip",
    "UniFi U6 Enterprise IW": "https://help-center-assets.svc.ui.com/hc/unifi-antenna-files/U6-Enterprise-IW.zip",
    "UniFi U6 Pro": "https://help-center-assets.svc.ui.com/hc/unifi-antenna-files/U6-Pro.zip",
    "UniFi U6 LR": "https://help-center-assets.svc.ui.com/hc/unifi-antenna-files/U6-LR.zip",
    "UniFi U6+": "https://help-center-assets.svc.ui.com/hc/unifi-antenna-files/U6-Plus.zip",
    "UniFi U6 Lite": "https://help-center-assets.svc.ui.com/hc/unifi-antenna-files/U6-Lite.zip",
    "UniFi U6 Mesh": "https://help-center-assets.svc.ui.com/hc/unifi-antenna-files/U6-Mesh.zip",
    "UniFi AC Pro": "https://help-center-assets.svc.ui.com/hc/unifi-antenna-files/UAP-AC-Pro.zip",
    "UniFi NanoHD": "https://help-center-assets.svc.ui.com/hc/unifi-antenna-files/UAP-nanoHD.zip",
    "UniFi FlexHD": "https://help-center-assets.svc.ui.com/hc/unifi-antenna-files/UAP-FlexHD.zip",
    "UniFi AC LR": "https://help-center-assets.svc.ui.com/hc/unifi-antenna-files/UAP-AC-LR.zip",
    "UniFi AC Lite": "https://help-center-assets.svc.ui.com/hc/unifi-antenna-files/UAP-AC-Lite.zip",
    "UniFi AC Mesh": "https://help-center-assets.svc.ui.com/hc/unifi-antenna-files/UAP-AC-M.zip",
    "UniFi AC Mesh Pro": "https://help-center-assets.svc.ui.com/hc/unifi-antenna-files/UAP-AC-M-Pro.zip",
    "UniFi IW-HD": "https://help-center-assets.svc.ui.com/hc/unifi-antenna-files/UAP-IW-HD.zip"
}

TEMP_DIR = "temp_patterns"
HARDWARE_FILE = "src/data/hardware.json"

def download_and_extract(url, output_dir):
    try:
        print(f"Downloading {url}...")
        # Ignore SSL errors
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        with urllib.request.urlopen(url, context=ctx) as response:
            with zipfile.ZipFile(io.BytesIO(response.read())) as z:
                z.extractall(output_dir)
        return True
    except Exception as e:
        print(f"Error downloading/extracting {url}: {e}")
        return False

def parse_ant_file(filepath):
    """
    Parses a .ant file.
    Expects UTF-16 encoding.
    Expects 720 lines of float numbers.
    Lines 0-359: Azimuth (Horizontal)
    Lines 360-719: Elevation (Vertical)
    Returns: {"azimuth": [...], "elevation": [...]}
    """
    try:
        # Try UTF-16 first, fallback to other encodings if needed
        encodings = ['utf-16', 'utf-8', 'ascii']
        content = None
        for enc in encodings:
            try:
                with open(filepath, 'r', encoding=enc) as f:
                    content = f.read()
                # Check if it looks right (numbers)
                if content and any(c.isdigit() for c in content[:20]):
                    break
            except UnicodeError:
                continue

        if not content:
            print(f"Could not read {filepath} with known encodings.")
            return None

        # Split by lines and filter empty or non-numeric
        lines = []
        for l in content.splitlines():
            l = l.strip()
            if not l: continue
            # Basic check if float
            try:
                float(l)
                lines.append(l)
            except ValueError:
                continue

        if len(lines) != 720:
            print(f"Warning: {filepath} has {len(lines)} lines (expected 720). Skipping.")
            return None

        values = [float(l) for l in lines]

        return {
            "azimuth": values[:360],
            "elevation": values[360:]
        }
    except Exception as e:
        print(f"Error parsing {filepath}: {e}")
        return None

def find_ant_file(directory, band_keywords):
    """
    Finds a .ant file in directory matching one of the band keywords.
    """
    for root, dirs, files in os.walk(directory):
        for file in files:
            if not file.endswith(".ant") or file.startswith("._"):
                continue

            # Check for band keywords
            lower_file = file.lower()
            for kw in band_keywords:
                if kw in lower_file:
                    return os.path.join(root, file)
    return None

def main():
    # Load hardware.json
    with open(HARDWARE_FILE, 'r') as f:
        hardware_data = json.load(f)

    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)
    os.makedirs(TEMP_DIR)

    updated_count = 0

    for ap in hardware_data["access_points"]:
        model = ap["model"]
        if model not in MODEL_URL_MAP:
            print(f"Skipping {model} (No URL mapped)")
            continue

        url = MODEL_URL_MAP[model]
        model_safe = model.replace(" ", "_")
        extract_path = os.path.join(TEMP_DIR, model_safe)

        if download_and_extract(url, extract_path):
            # Process bands
            bands_updated = False
            for band in ["2.4", "5", "6"]:
                if band not in ap["bands"]:
                    continue

                # Keywords to search for file
                keywords = []
                if band == "2.4":
                    keywords = ["2.4", "2ghz"]
                elif band == "5":
                    keywords = ["5ghz", "5.15", "5.5", "5.85"]
                    # Note: Unifi sometimes splits 5GHz into Low/Mid/High.
                    # Usually "5GHz" file exists, or we pick one.
                    # We will prefer generic "5GHz" if available.
                elif band == "6":
                    keywords = ["6ghz"]

                ant_file = find_ant_file(extract_path, keywords)

                # Special handling if multiple 5GHz files exist (Low/Mid/High)
                # Ideally we'd average them, but picking "Mid" or generic is fine.

                if ant_file:
                    print(f"  Found {band}GHz pattern: {os.path.basename(ant_file)}")
                    pattern_data = parse_ant_file(ant_file)
                    if pattern_data:
                        ap["bands"][band]["pattern"] = pattern_data
                        bands_updated = True
                else:
                    print(f"  No pattern file found for {model} {band}GHz")

            if bands_updated:
                updated_count += 1

    # Save hardware.json
    with open(HARDWARE_FILE, 'w') as f:
        json.dump(hardware_data, f, indent=4)

    print(f"Updated {updated_count} AP models with patterns.")

    # Cleanup
    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)

if __name__ == "__main__":
    main()
