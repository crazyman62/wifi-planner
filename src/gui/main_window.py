import sys
import json
import os
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                               QHBoxLayout, QPushButton, QFileDialog, QLabel,
                               QToolBar, QStatusBar, QComboBox, QListWidget)
from PySide6.QtGui import QAction, QIcon, QPen, QColor
from PySide6.QtCore import Qt, QPointF

from PySide6.QtWidgets import QGraphicsLineItem, QGraphicsPixmapItem
from src.gui.canvas import PlanCanvas
from src.gui.dialogs import CalibrationDialog
from src.gui.items import WallItem, AccessPointItem
from src.engine.heatmap import generate_heatmap, heatmap_to_pixmap
from src.utils.file_io import save_project, load_project
import math
import json

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WiFi Predictive Planner - Phase 1")
        self.resize(1200, 800)

        # Central Widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Layouts
        main_layout = QHBoxLayout(central_widget)

        # Sidebar (Tools)
        self.sidebar_layout = QVBoxLayout()
        main_layout.addLayout(self.sidebar_layout, stretch=1)

        # Canvas Area
        self.canvas = PlanCanvas()
        main_layout.addWidget(self.canvas, stretch=5)

        # Application State
        self.current_image_path = None
        self.pixels_per_meter = 1.0 # Default
        self.current_mode = "SELECT" # SELECT, CALIBRATE, DRAW_WALL, ADD_AP

        self.materials_data = self._load_materials()
        self.hardware_data = self._load_hardware()

        # Build UI (Needs data loaded first)
        self._create_menus()
        self._create_sidebar()
        self._create_statusbar()

        # Temp Drawing State
        self.temp_line_item = None
        self.drawing_start_point = None

        # Connect Canvas Signals
        self.canvas.point_clicked.connect(self.handle_canvas_click)
        self.canvas.mouse_moved.connect(self.handle_canvas_move)

    def _load_materials(self):
        try:
            with open('src/data/materials.json', 'r') as f:
                data = json.load(f)
                return {m['name']: m for m in data['materials']}
        except Exception as e:
            print(f"Error loading materials: {e}")
            return {}

    def _load_hardware(self):
        try:
            with open('src/data/hardware.json', 'r') as f:
                data = json.load(f)
                return {ap['model']: ap for ap in data['access_points']}
        except Exception as e:
            print(f"Error loading hardware: {e}")
            return {}

    def _create_menus(self):
        menu_bar = self.menuBar()

        # File Menu
        file_menu = menu_bar.addMenu("&File")

        load_img_action = QAction("Load Image", self)
        load_img_action.triggered.connect(self.load_image)
        file_menu.addAction(load_img_action)

        save_action = QAction("Save Project", self)
        save_action.triggered.connect(self.save_project)
        file_menu.addAction(save_action)

        open_action = QAction("Open Project", self)
        open_action.triggered.connect(self.open_project)
        file_menu.addAction(open_action)

        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

    def _create_sidebar(self):
        # Mode Buttons
        self.btn_select = QPushButton("Select / Pan")
        self.btn_calibrate = QPushButton("Calibrate Scale")
        self.btn_draw_wall = QPushButton("Draw Wall")
        self.btn_add_ap = QPushButton("Add AP")

        # Connect buttons
        self.btn_select.clicked.connect(lambda: self.set_mode("SELECT"))
        self.btn_calibrate.clicked.connect(lambda: self.set_mode("CALIBRATE"))
        self.btn_draw_wall.clicked.connect(lambda: self.set_mode("DRAW_WALL"))
        self.btn_add_ap.clicked.connect(lambda: self.set_mode("ADD_AP"))

        self.sidebar_layout.addWidget(QLabel("<b>Tools</b>"))
        self.sidebar_layout.addWidget(self.btn_select)
        self.sidebar_layout.addWidget(self.btn_calibrate)
        self.sidebar_layout.addWidget(self.btn_draw_wall)
        self.sidebar_layout.addWidget(self.btn_add_ap)

        self.lbl_ppm = QLabel("Scale: Not Calibrated")
        self.sidebar_layout.addWidget(self.lbl_ppm)

        # Wall Materials Config
        self.sidebar_layout.addWidget(QLabel("<b>Wall Material</b>"))
        self.combo_materials = QComboBox()
        if self.materials_data:
            self.combo_materials.addItems(list(self.materials_data.keys()))
        self.sidebar_layout.addWidget(self.combo_materials)

        # AP Selection
        self.sidebar_layout.addWidget(QLabel("<b>AP Model</b>"))
        self.combo_aps = QComboBox()
        if self.hardware_data:
            self.combo_aps.addItems(list(self.hardware_data.keys()))
        self.sidebar_layout.addWidget(self.combo_aps)

        # Band Selection
        self.sidebar_layout.addWidget(QLabel("<b>Frequency Band</b>"))
        self.combo_band = QComboBox()
        self.combo_band.addItems(["2.4", "5", "6"])
        self.combo_band.setCurrentText("5")
        self.sidebar_layout.addWidget(self.combo_band)

        # Calculate Button
        self.btn_calculate = QPushButton("Generate Heatmap")
        self.btn_calculate.clicked.connect(self.run_heatmap)
        self.sidebar_layout.addWidget(self.btn_calculate)

        self.sidebar_layout.addStretch()

        # Heatmap Item
        self.heatmap_item = None

    def reset_drawing_state(self):
        self.drawing_start_point = None
        if self.temp_line_item:
            try:
                # Check if item is still valid and in a scene
                if self.temp_line_item.scene():
                    self.temp_line_item.scene().removeItem(self.temp_line_item)
            except RuntimeError:
                # Object already deleted by C++
                pass
            self.temp_line_item = None

    def set_mode(self, mode):
        self.current_mode = mode
        self.status_bar.showMessage(f"Mode: {mode}")
        self.reset_drawing_state()

    def _create_statusbar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

    def load_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Floor Plan", "", "Images (*.png *.jpg *.jpeg *.bmp)"
        )
        if file_path:
            # Reset state before loading new image which clears scene
            self.reset_drawing_state()

            success = self.canvas.load_image(file_path)
            if success:
                self.current_image_path = file_path
                self.status_bar.showMessage(f"Loaded: {os.path.basename(file_path)}")

                self.pixels_per_meter = 1.0
                self.heatmap_item = None
            else:
                self.status_bar.showMessage("Failed to load image.")

    def save_project(self):
        if not self.current_image_path:
            self.status_bar.showMessage("Nothing to save.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Project", "", "WiFi Project (*.wifi)"
        )

        # Gather data from Scene Items
        walls_to_save = []
        aps_to_save = []

        for item in self.canvas.scene.items():
            if isinstance(item, WallItem):
                line = item.line()
                p1 = (line.x1(), line.y1())
                p2 = (line.x2(), line.y2())
                walls_to_save.append({
                    'p1': p1,
                    'p2': p2,
                    'material': item.material_name
                })
            elif isinstance(item, AccessPointItem):
                # Center position
                rect = item.rect()
                # rect is relative to item pos if item pos is set,
                # OR we just use scenePos() if we move using setPos
                # AccessPointItem uses setPos? No, we need to check how QGraphicsEllipseItem works.
                # If we just create it at x,y, its pos() is 0,0 usually unless we moved it.
                # Since we set flags ItemIsMovable, QGraphicsScene updates item.pos().

                # Correct way to get center:
                # The item rect is defined as (x-r, y-r, 2r, 2r) relative to local (0,0) usually if we set it that way?
                # Actually in AccessPointItem.__init__: super().__init__(x - r, y - r, 2 * r, 2 * r)
                # This constructs the rect in item coordinates. The item's origin is (0,0).
                # When moved, pos() changes.
                # Center in Scene Coords = mapToScene(center_of_rect)

                center_local = item.rect().center()
                center_scene = item.mapToScene(center_local)

                aps_to_save.append({
                    'x': center_scene.x(),
                    'y': center_scene.y(),
                    'model': item.model_name
                })

        if file_path:
            save_project(file_path, self.current_image_path, self.pixels_per_meter,
                         walls_to_save, aps_to_save)
            self.status_bar.showMessage(f"Saved to {file_path}")

    def open_project(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Project", "", "WiFi Project (*.wifi)"
        )
        if file_path:
            data = load_project(file_path)
            if data:
                # Reset state before loading
                self.reset_drawing_state()

                # Load Image
                self.current_image_path = data.get("image_path")
                if self.current_image_path:
                    self.canvas.load_image(self.current_image_path)

                self.pixels_per_meter = data.get("pixels_per_meter", 1.0)

                # Redraw UI elements (Walls)

                # Re-add walls
                for w in data.get("walls", []):
                    p1 = w['p1']
                    p2 = w['p2']
                    mat = w['material']
                    color_hex = self.materials_data.get(mat, {}).get('color', '#000000')

                    wall_item = WallItem((p1[0], p1[1]), (p2[0], p2[1]), mat, color_hex)
                    self.canvas.scene.addItem(wall_item)

                # Re-add APs
                for ap in data.get("access_points", []):
                    ap_item = AccessPointItem(ap['x'], ap['y'], ap['model'])
                    self.canvas.scene.addItem(ap_item)

                self.lbl_ppm.setText(f"Scale: {self.pixels_per_meter:.2f} px/m")
                self.status_bar.showMessage(f"Project loaded: {os.path.basename(file_path)}")
            else:
                self.status_bar.showMessage("Failed to load project.")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete:
            scene = self.canvas.scene
            selected_items = scene.selectedItems()
            if selected_items:
                for item in selected_items:
                    scene.removeItem(item)
                self.status_bar.showMessage(f"Deleted {len(selected_items)} items.")
        else:
            super().keyPressEvent(event)

    def run_heatmap(self):
        if not self.canvas.pixmap_item:
            self.status_bar.showMessage("No image loaded.")
            return

        if self.pixels_per_meter <= 0:
            self.status_bar.showMessage("Please calibrate first.")
            return

        # Gather data from Scene
        current_walls = []
        current_aps = []
        for item in self.canvas.scene.items():
            if isinstance(item, WallItem):
                line = item.line()
                current_walls.append({
                    'p1': (line.x1(), line.y1()),
                    'p2': (line.x2(), line.y2()),
                    'material': item.material_name
                })
            elif isinstance(item, AccessPointItem):
                center_local = item.rect().center()
                center_scene = item.mapToScene(center_local)
                current_aps.append({
                    'x': center_scene.x(),
                    'y': center_scene.y(),
                    'model': item.model_name
                })

        if not current_aps:
            self.status_bar.showMessage("Place at least one AP.")
            return

        self.status_bar.showMessage("Generating Heatmap...")
        QApplication.processEvents() # Force UI update

        width = int(self.canvas.pixmap_item.pixmap().width())
        height = int(self.canvas.pixmap_item.pixmap().height())

        band = self.combo_band.currentText()

        # Run Calculation
        rssi_grid = generate_heatmap(
            width, height,
            self.pixels_per_meter,
            current_aps,
            current_walls,
            self.hardware_data,
            self.materials_data,
            frequency_band=band,
            resolution=20 # Lower res for speed
        )

        # Convert to Pixmap
        pixmap = heatmap_to_pixmap(rssi_grid, width, height)

        # Display
        if self.heatmap_item:
            self.canvas.scene.removeItem(self.heatmap_item)

        self.heatmap_item = QGraphicsPixmapItem(pixmap)
        self.heatmap_item.setZValue(10) # Above map, below APs/Walls if we set their Z higher
        self.canvas.scene.addItem(self.heatmap_item)

        self.status_bar.showMessage("Heatmap generated.")

    def find_snap_point(self, pos, threshold=15):
        """
        Finds the closest existing wall endpoint to 'pos' from Scene Items.
        """
        closest_point = None
        min_dist = float('inf')

        # Collect all endpoints from Scene Items
        endpoints = []
        for item in self.canvas.scene.items():
            if isinstance(item, WallItem):
                line = item.line()
                endpoints.append((line.x1(), line.y1()))
                endpoints.append((line.x2(), line.y2()))

        for ep in endpoints:
            dx = pos.x() - ep[0]
            dy = pos.y() - ep[1]
            dist = math.sqrt(dx*dx + dy*dy)
            if dist < threshold:
                if dist < min_dist:
                    min_dist = dist
                    closest_point = QPointF(ep[0], ep[1])

        if closest_point:
            return closest_point
        return pos

    def handle_canvas_click(self, point):
        # Apply snapping if applicable
        if self.current_mode in ["DRAW_WALL"]:
            point = self.find_snap_point(point)

        if self.current_mode == "CALIBRATE":
            if not self.drawing_start_point:
                self.drawing_start_point = point
            else:
                # Finish calibration line
                end_point = point
                dist_px = math.sqrt((end_point.x() - self.drawing_start_point.x())**2 +
                                    (end_point.y() - self.drawing_start_point.y())**2)

                # Remove temp line
                if self.temp_line_item:
                    self.canvas.scene.removeItem(self.temp_line_item)
                    self.temp_line_item = None
                self.drawing_start_point = None

                if dist_px < 5:
                    self.status_bar.showMessage("Distance too short for calibration.")
                    return

                dialog = CalibrationDialog(dist_px, self)
                if dialog.exec():
                    real_dist = dialog.real_distance
                    self.pixels_per_meter = dist_px / real_dist
                    self.lbl_ppm.setText(f"Scale: {self.pixels_per_meter:.2f} px/m")
                    self.status_bar.showMessage(f"Calibrated: {self.pixels_per_meter:.2f} px/m")
                    self.set_mode("SELECT")

        elif self.current_mode == "DRAW_WALL":
            if not self.drawing_start_point:
                self.drawing_start_point = point
            else:
                end_point = point
                # Save Wall to Scene
                material_name = self.combo_materials.currentText()
                color_hex = self.materials_data.get(material_name, {}).get('color', '#000000')

                # Create WallItem
                wall_item = WallItem(
                    (self.drawing_start_point.x(), self.drawing_start_point.y()),
                    (end_point.x(), end_point.y()),
                    material_name,
                    color_hex
                )
                self.canvas.scene.addItem(wall_item)

                # Remove temp line
                if self.temp_line_item:
                    self.canvas.scene.removeItem(self.temp_line_item)
                    self.temp_line_item = None

                # Continue drawing (Polyline behavior)
                self.drawing_start_point = point
                self.status_bar.showMessage(f"Wall added. Click to continue, or change tool to stop.")

        elif self.current_mode == "ADD_AP":
            model_name = self.combo_aps.currentText()
            ap_item = AccessPointItem(point.x(), point.y(), model_name)
            self.canvas.scene.addItem(ap_item)
            self.status_bar.showMessage(f"Added AP: {model_name}")

    def handle_canvas_move(self, point):
        if self.current_mode in ["CALIBRATE", "DRAW_WALL"] and self.drawing_start_point:
            # Snap logic for move
            if self.current_mode == "DRAW_WALL":
                point = self.find_snap_point(point)

            # Defensive: Check if temp_line_item was deleted externally
            if self.temp_line_item:
                try:
                    # Check validity by accessing a property
                    _ = self.temp_line_item.scene()
                except RuntimeError:
                    self.temp_line_item = None

            if not self.temp_line_item:
                self.temp_line_item = QGraphicsLineItem()
                pen = self.temp_line_item.pen()

                if self.current_mode == "CALIBRATE":
                    pen.setColor(Qt.red)
                    pen.setWidth(2)
                elif self.current_mode == "DRAW_WALL":
                    # Use material color
                    material_name = self.combo_materials.currentText()
                    color_hex = self.materials_data.get(material_name, {}).get('color', '#0000FF')
                    pen.setColor(QColor(color_hex))
                    pen.setWidth(4)
                else:
                    pen.setColor(Qt.blue)
                    pen.setWidth(2)

                self.temp_line_item.setPen(pen)
                self.canvas.scene.addItem(self.temp_line_item)

            # If drawing wall, check if material changed mid-draw?
            # It's better to update pen on move if needed, but for now only on init is fine
            # unless user changes combo while dragging (unlikely).

            line = self.temp_line_item.line()
            line.setP1(self.drawing_start_point)
            line.setP2(point)
            self.temp_line_item.setLine(line)

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
