# WiFi Predictive Planner (Phase 3)

## Description

A desktop application for planning Wi-Fi network deployments. It allows users to upload floor plans, draw walls with different material properties, place Access Points (APs), and visualize signal coverage (heatmap) across multiple floors. It supports 2.4, 5, and 6 GHz bands.

## Features

- **Multi-Floor Support:** Manage multiple floors with alignment tools (Ghost Floor) to visualize how signals propagate between floors.
- **Floor Plan Import:** Load images (PNG, JPG) for floor plans.
- **Scale Calibration:** Calibrate floor plan scale using known distances (pixels per meter).
- **Wall Drawing:** Draw walls with specific materials (Concrete, Drywall, Glass, etc.) that affect signal propagation.
- **Access Points:** Place APs from a hardware database with realistic 3D antenna patterns.
- **Heatmap Visualization:** Real-time signal strength simulation based on the log-distance path loss model, accounting for wall attenuation, floor attenuation, and antenna patterns.
- **Auto Channel/Power Planning:** Automatically assigns channels and power levels to minimize interference.
- **PDF Export:** Generate comprehensive reports with heatmaps and Bill of Materials (BOM) for each floor and band.
- **Project Management:** Save and load projects (`.wifi` files).
- **Interactive UI:** Zoom, pan, snap-to-grid/wall, undo/redo, and "Ghost Floor" overlay.

## Installation

1.  **Clone the repository:**
    ```bash
    git clone <repository_url>
    cd <repository_name>
    ```

2.  **Install dependencies:**
    It is recommended to use a virtual environment.
    ```bash
    pip install -r requirements.txt
    ```
    *Dependencies include: `PySide6`, `numpy`, `opencv-python-headless`, `reportlab`.*

3.  **Run the application:**
    ```bash
    python main.py
    ```

## Usage

1.  **Start the Application:** Run `python main.py`.
2.  **Add a Floor:** Click "Add Floor" in the sidebar or File menu. Provide a name, number (level), and upload a floor plan image.
3.  **Calibrate Scale:**
    - Click the "Calibrate Scale" button.
    - Click two points on the floor plan with a known distance between them.
    - Enter the real-world distance (in meters) in the dialog.
4.  **Draw Walls:**
    - Select "Draw Wall".
    - Choose a material from the "Wall Material" dropdown in the top toolbar.
    - Click to start drawing, click to place corners.
    - Right-click to stop the current wall segment.
5.  **Place Access Points:**
    - Select "Add AP".
    - Choose an AP Model from the dropdown.
    - Click on the map to place the AP.
    - Select the AP to edit its properties (Mounting type, Rotation, Channel, Tx Power) in the sidebar.
6.  **Simulate:**
    - The heatmap updates automatically as you make changes.
    - Switch between **2.4**, **5**, and **6** GHz bands using the dropdown in the top toolbar to see coverage for each band.
    - Hover over the heatmap to see signal strength (dBm) at that point.
7.  **Export Report:**
    - Go to `File > Export Report (PDF)`.
    - Choose a location to save the report. The report includes heatmaps for all floors and bands, plus a BOM.

## Controls

-   **Left Click:** Draw, Select, Place items.
-   **Right Click:** Stop drawing wall, Open context menu (on floor tabs).
-   **Mouse Wheel:** Zoom in/out.
-   **Ctrl + Wheel / Middle Click Drag:** Pan the view.
-   **Delete Key:** Delete selected items (Walls, APs, Zones).
-   **Ctrl + Z:** Undo last action.

## Project Structure

-   `main.py`: Application entry point.
-   `src/`: Source code directory.
    -   `data/`: JSON configuration files (`hardware.json`, `materials.json`).
    -   `engine/`: Core logic (`heatmap.py`, `physics.py`, `project.py`, `auto_planner.py`).
    -   `gui/`: User Interface implementation (`main_window.py`, `canvas.py`, `items.py`, `dialogs.py`).
    -   `utils/`: Utility scripts (`file_io.py`, `report_generator.py`).
-   `tests/`: Unit tests.

## Configuration

-   **Hardware:** AP models and antenna patterns are defined in `src/data/hardware.json`.
-   **Materials:** Wall and floor material attenuation properties are defined in `src/data/materials.json`.
