import sys
import json
import os
import math
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                               QHBoxLayout, QPushButton, QFileDialog, QLabel,
                               QToolBar, QStatusBar, QComboBox, QListWidget, QSpinBox,
                               QInputDialog, QTabWidget, QDoubleSpinBox, QMenu, QMessageBox)
from PySide6.QtGui import QAction, QIcon, QPen, QColor, QImage, QPainter, QMouseEvent
from PySide6.QtCore import Qt, QPointF, QRectF

from PySide6.QtWidgets import QGraphicsLineItem, QGraphicsPixmapItem, QGraphicsRectItem
from src.gui.canvas import PlanCanvas
from src.gui.dialogs import CalibrationDialog, SettingsDialog, AddFloorDialog
from src.gui.items import WallItem, AccessPointItem, WallNodeItem, ZoneItem
from src.engine.heatmap import generate_heatmap, heatmap_to_pixmap
from src.engine.project import Project, Floor
from src.utils.file_io import save_project, load_project
from src.utils.command_invoker import UndoStack, AddWallCommand, AddAPCommand, DeleteCommand, MoveCommand
from src.utils.report_generator import PDFReport

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WiFi Predictive Planner - Phase 2")
        self.resize(1200, 800)

        # Initialize Project
        self.project = Project()

        # Central Widget is now a TabWidget
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(False)
        self.tabs.currentChanged.connect(self.on_tab_changed)

        # Context Menu for Tabs
        self.tabs.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tabs.customContextMenuRequested.connect(self.show_tab_context_menu)

        # Tools Sidebar
        sidebar_widget = QWidget()
        self.sidebar_layout = QVBoxLayout(sidebar_widget)

        container = QWidget()
        main_layout = QHBoxLayout(container)
        main_layout.addWidget(sidebar_widget, stretch=1)
        main_layout.addWidget(self.tabs, stretch=5)
        self.setCentralWidget(container)

        # State
        self.current_mode = "SELECT"
        self.undo_stack = UndoStack()
        self.active_wall_nodes = [] # List of WallNodeItems

        # Materials & Hardware
        self.materials_data = self._load_materials()
        self.floor_materials_data = self.materials_data.get('floor_materials', [])
        if isinstance(self.floor_materials_data, list):
             self.floor_material_names = [m['name'] for m in self.floor_materials_data]
        else:
            self.floor_material_names = ["Concrete", "Wood"]

        self.hardware_data = self._load_hardware()

        # Build UI
        self._create_menus()
        self._create_sidebar()
        self._create_statusbar()

        # Canvas Event Handling State
        self.drawing_start_point = None
        self.temp_line_item = None
        self.temp_rect_item = None
        self.selected_item_start_pos = None

        # Add initial floor
        f1 = Floor("Floor 1", 1, "Concrete")
        self.project.add_floor(f1)
        self._add_tab_for_floor(f1)

    @property
    def current_canvas(self):
        """Returns the PlanCanvas of the currently active tab."""
        widget = self.tabs.currentWidget()
        if isinstance(widget, PlanCanvas):
            return widget
        return None

    @property
    def current_floor(self):
        index = self.tabs.currentIndex()
        return self.project.get_floor(index)

    def _load_materials(self):
        try:
            with open('src/data/materials.json', 'r') as f:
                data = json.load(f)
                return data
        except Exception as e:
            print(f"Error loading materials: {e}")
            return {'materials': [], 'floor_materials': []}

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

        new_floor_action = QAction("Add Floor", self)
        new_floor_action.triggered.connect(self.show_add_floor_dialog)
        file_menu.addAction(new_floor_action)

        save_action = QAction("Save Project", self)
        save_action.triggered.connect(self.save_project)
        file_menu.addAction(save_action)

        open_action = QAction("Open Project", self)
        open_action.triggered.connect(self.open_project)
        file_menu.addAction(open_action)

        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Edit Menu
        edit_menu = menu_bar.addMenu("&Edit")
        undo_action = QAction("Undo", self)
        undo_action.setShortcut("Ctrl+Z")
        undo_action.triggered.connect(self.undo_last_action)
        edit_menu.addAction(undo_action)

    def _create_sidebar(self):
        # Floor Controls
        self.sidebar_layout.addWidget(QLabel("<b>Floor Tools</b>"))
        self.btn_add_floor = QPushButton("Add Floor")
        self.btn_add_floor.clicked.connect(self.show_add_floor_dialog)
        self.sidebar_layout.addWidget(self.btn_add_floor)

        self.sidebar_layout.addSpacing(10)

        # Drawing Tools
        self.sidebar_layout.addWidget(QLabel("<b>Drawing Tools</b>"))
        self.btn_select = QPushButton("Select / Pan")
        self.btn_calibrate = QPushButton("Calibrate Scale")
        self.btn_draw_wall = QPushButton("Draw Wall")
        self.btn_edit_nodes = QPushButton("Edit Wall Nodes") # New
        self.btn_draw_zone = QPushButton("Draw Ceiling Zone") # New
        self.btn_add_ap = QPushButton("Add AP")

        self.btn_select.clicked.connect(lambda: self.set_mode("SELECT"))
        self.btn_calibrate.clicked.connect(lambda: self.set_mode("CALIBRATE"))
        self.btn_draw_wall.clicked.connect(lambda: self.set_mode("DRAW_WALL"))
        self.btn_edit_nodes.clicked.connect(lambda: self.set_mode("EDIT_NODES"))
        self.btn_draw_zone.clicked.connect(lambda: self.set_mode("DRAW_ZONE"))
        self.btn_add_ap.clicked.connect(lambda: self.set_mode("ADD_AP"))

        self.sidebar_layout.addWidget(self.btn_select)
        self.sidebar_layout.addWidget(self.btn_calibrate)
        self.sidebar_layout.addWidget(self.btn_draw_wall)
        self.sidebar_layout.addWidget(self.btn_edit_nodes)
        self.sidebar_layout.addWidget(self.btn_draw_zone)
        self.sidebar_layout.addWidget(self.btn_add_ap)

        self.lbl_ppm = QLabel("Scale: Not Calibrated")
        self.sidebar_layout.addWidget(self.lbl_ppm)

        # Alignment Tools
        self.sidebar_layout.addSpacing(10)
        self.sidebar_layout.addWidget(QLabel("<b>Floor Alignment</b>"))

        align_layout = QVBoxLayout()
        self.spin_x = QDoubleSpinBox()
        self.spin_x.setRange(-5000, 5000)
        self.spin_x.setPrefix("X: ")
        self.spin_x.valueChanged.connect(self.update_floor_transform)
        align_layout.addWidget(self.spin_x)

        self.spin_y = QDoubleSpinBox()
        self.spin_y.setRange(-5000, 5000)
        self.spin_y.setPrefix("Y: ")
        self.spin_y.valueChanged.connect(self.update_floor_transform)
        align_layout.addWidget(self.spin_y)

        # Rotation Controls with 90 deg buttons
        rot_layout = QHBoxLayout()
        self.btn_rot_left = QPushButton("-90°")
        self.btn_rot_left.clicked.connect(self.rotate_left)

        self.spin_rot = QDoubleSpinBox()
        self.spin_rot.setRange(-360, 360)
        self.spin_rot.setPrefix("Rot: ")
        self.spin_rot.valueChanged.connect(self.update_floor_transform)

        self.btn_rot_right = QPushButton("+90°")
        self.btn_rot_right.clicked.connect(self.rotate_right)

        rot_layout.addWidget(self.btn_rot_left)
        rot_layout.addWidget(self.spin_rot)
        rot_layout.addWidget(self.btn_rot_right)

        align_layout.addLayout(rot_layout)

        self.spin_scale = QDoubleSpinBox()
        self.spin_scale.setRange(0.01, 100.0)
        self.spin_scale.setSingleStep(0.1)
        self.spin_scale.setValue(1.0)
        self.spin_scale.setPrefix("Scale: ")
        self.spin_scale.valueChanged.connect(self.update_floor_transform)
        align_layout.addWidget(self.spin_scale)

        self.chk_ghost = QPushButton("Toggle Ghost Floor")
        self.chk_ghost.setCheckable(True)
        self.chk_ghost.clicked.connect(self.toggle_ghost_floor)
        align_layout.addWidget(self.chk_ghost)

        self.sidebar_layout.addLayout(align_layout)

        # Wall Material
        self.sidebar_layout.addSpacing(10)
        self.sidebar_layout.addWidget(QLabel("<b>Wall Material</b>"))
        self.combo_materials = QComboBox()
        # Parse material names from complex structure
        wall_mats = self.materials_data.get('materials', [])
        self.combo_materials.addItems([m['name'] for m in wall_mats])
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

        self.sidebar_layout.addStretch()

        # Settings
        self.btn_settings = QPushButton("Settings")
        self.btn_settings.clicked.connect(self.open_settings)
        self.sidebar_layout.addWidget(self.btn_settings)

    def _create_statusbar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

    # --- Floor Management ---

    def show_tab_context_menu(self, position):
        index = self.tabs.tabBar().tabAt(position)
        if index >= 0:
            menu = QMenu()
            edit_action = menu.addAction("Edit Floor")
            delete_action = menu.addAction("Delete Floor")

            action = menu.exec(self.tabs.mapToGlobal(position))

            if action == edit_action:
                self.edit_floor(index)
            elif action == delete_action:
                self.delete_floor(index)

    def edit_floor(self, index):
        floor = self.project.get_floor(index)
        if not floor: return

        initial_data = floor.to_dict()
        dialog = AddFloorDialog(self.floor_material_names, self, initial_data=initial_data)

        if dialog.exec():
            data = dialog.get_data()

            # Update Object
            floor.name = data['name']
            floor.floor_number = data['number']
            floor.material_name = data['material']
            floor.ceiling_height = data['ceiling_height']

            if data['image_path'] and data['image_path'] != floor.image_path:
                # Image Changed: Sync old items to model first?
                # If we rely on model being source of truth for items during reload,
                # we must ensure model is up to date with scene.
                canvas = self.tabs.widget(index)
                if canvas:
                    # Sync scene -> floor object
                    self._sync_canvas_to_floor(canvas, floor)

                    floor.image_path = data['image_path']

                    # Clear Scene Items (except background which load_image handles, but we need to clear walls/aps)
                    canvas.scene.clear()

                    # Reload Image
                    canvas.load_image(floor.image_path,
                                      floor.x_offset, floor.y_offset,
                                      floor.rotation, floor.scale_factor)

                    # Re-populate items
                    self._populate_canvas_items(canvas, floor)

            # Update Tab Text
            self.tabs.setTabText(index, floor.name)
            self.status_bar.showMessage(f"Updated floor: {floor.name}")
            self.trigger_heatmap()

    def _sync_canvas_to_floor(self, canvas, floor):
        """Helper to save current scene items to the floor object."""
        # Walls
        walls = []
        for item in canvas.scene.items():
            if isinstance(item, WallItem):
                l = item.line()
                walls.append({
                    'p1': (l.x1(), l.y1()),
                    'p2': (l.x2(), l.y2()),
                    'material': item.material_name
                })
        floor.walls = walls

        # APs
        aps = []
        for item in canvas.scene.items():
            if isinstance(item, AccessPointItem):
                aps.append({
                    'x': item.scenePos().x(),
                    'y': item.scenePos().y(),
                    'model': item.model_name,
                    'name': item.name
                })
        floor.access_points = aps

        # Zones
        zones = []
        for item in canvas.scene.items():
            if isinstance(item, ZoneItem):
                 r = item.rect()
                 zones.append({
                     'rect': [r.x(), r.y(), r.width(), r.height()],
                     'height': item.ceiling_height
                 })
        floor.regions = zones

    def delete_floor(self, index):
        floor = self.project.get_floor(index)
        if not floor: return

        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Are you sure you want to delete '{floor.name}'? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            # Remove from Project
            self.project.floors.pop(index)
            # Remove Tab
            self.tabs.removeTab(index)
            self.status_bar.showMessage(f"Deleted floor: {floor.name}")
            self.trigger_heatmap()

    def show_add_floor_dialog(self):
        dialog = AddFloorDialog(self.floor_material_names, self)
        if dialog.exec():
            data = dialog.get_data()
            new_floor = Floor(
                name=data['name'],
                number=data['number'],
                material_name=data['material'],
                image_path=data['image_path']
            )
            new_floor.ceiling_height = data['ceiling_height']

            self.project.add_floor(new_floor)
            self._add_tab_for_floor(new_floor)

            self.status_bar.showMessage(f"Added floor: {new_floor.name}")

    def _add_tab_for_floor(self, floor):
        canvas = PlanCanvas()

        # Connect signals
        canvas.point_clicked.connect(self.handle_canvas_click)
        canvas.right_clicked.connect(self.handle_canvas_right_click) # Connect new signal
        canvas.mouse_moved.connect(self.handle_canvas_move)
        canvas.mouse_released.connect(self.handle_canvas_release)
        canvas.scene.selectionChanged.connect(self.on_selection_changed)

        # Load Image
        if floor.image_path:
            canvas.load_image(floor.image_path,
                              floor.x_offset, floor.y_offset,
                              floor.rotation, floor.scale_factor)

        # Re-populate items (if loading from file)
        self._populate_canvas_items(canvas, floor)

        # Set current mode
        canvas.mode = self.current_mode

        self.tabs.addTab(canvas, floor.name)
        self.tabs.setCurrentWidget(canvas)

        # Ensure heatmap_item exists (fix attribute error)
        canvas.heatmap_item = None

    def _populate_canvas_items(self, canvas, floor):
        # Walls
        wall_mats = {m['name']: m for m in self.materials_data.get('materials', [])}
        for w in floor.walls:
            # Helper to normalize access
            def get_val(item, key, default):
                return item.get(key, default) if isinstance(item, dict) else getattr(item, key, default)

            p1 = get_val(w, 'p1', (0,0))
            p2 = get_val(w, 'p2', (0,0))
            mat = get_val(w, 'material', 'Concrete')

            color_hex = wall_mats.get(mat, {}).get('color', '#000000')
            wall_item = WallItem((p1[0], p1[1]), (p2[0], p2[1]), mat, color_hex)
            canvas.scene.addItem(wall_item)

        # APs
        for ap in floor.access_points:
            x = ap['x'] if isinstance(ap, dict) else ap.x
            y = ap['y'] if isinstance(ap, dict) else ap.y
            model = ap['model'] if isinstance(ap, dict) else ap.model
            name = ap['name'] if isinstance(ap, dict) else ap.name

            ap_item = AccessPointItem(x, y, model, name)
            canvas.scene.addItem(ap_item)

        # Zones
        for z in floor.regions:
            # z is dict from JSON
            x, y, w, h = z.get('rect', [0,0,10,10])
            height = z.get('height', 3.0)

            zone_item = ZoneItem(QRectF(x, y, w, h), height)
            canvas.scene.addItem(zone_item)

    def on_tab_changed(self, index):
        floor = self.project.get_floor(index)
        if floor:
            # Sync mode
            if self.current_canvas:
                self.current_canvas.mode = self.current_mode

            # Update UI controls for this floor
            self.blockSignals(True) # Prevent feedback loops
            self.spin_x.setValue(floor.x_offset)
            self.spin_y.setValue(floor.y_offset)
            self.spin_rot.setValue(floor.rotation)
            self.spin_scale.setValue(floor.scale_factor)

            if floor.pixels_per_meter:
                self.lbl_ppm.setText(f"Scale: {floor.pixels_per_meter:.2f} px/m")
            else:
                self.lbl_ppm.setText("Scale: Not Calibrated")

            self.blockSignals(False)

            # If Ghost Mode is on, update it
            if self.chk_ghost.isChecked():
                self.update_ghost_view(index)

    def update_floor_transform(self):
        floor = self.current_floor
        canvas = self.current_canvas
        if floor and canvas:
            floor.x_offset = self.spin_x.value()
            floor.y_offset = self.spin_y.value()
            floor.rotation = self.spin_rot.value()
            floor.scale_factor = self.spin_scale.value()

            canvas.update_image_transform(floor.x_offset, floor.y_offset, floor.rotation, floor.scale_factor)

            # Trigger Heatmap Update? Maybe too heavy.
            pass

    def rotate_left(self):
        val = self.spin_rot.value()
        self.spin_rot.setValue(val - 90)

    def rotate_right(self):
        val = self.spin_rot.value()
        self.spin_rot.setValue(val + 90)

    def toggle_ghost_floor(self):
        idx = self.tabs.currentIndex()
        if self.chk_ghost.isChecked():
            self.update_ghost_view(idx)
        else:
            if self.current_canvas:
                self.current_canvas.set_ghost_image(None)

    def update_ghost_view(self, current_idx):
        if current_idx > 0:
            target_idx = current_idx - 1
            target_floor = self.project.get_floor(target_idx)
            if target_floor and target_floor.image_path:
                self.current_canvas.set_ghost_image(
                    target_floor.image_path,
                    target_floor.x_offset,
                    target_floor.y_offset,
                    target_floor.rotation,
                    target_floor.scale_factor
                )
        else:
            self.status_bar.showMessage("No floor below to display.")
            self.current_canvas.set_ghost_image(None)

    # --- Mode & Canvas Interaction ---

    def set_mode(self, mode):
        # Exit previous mode logic
        if self.current_mode == "EDIT_NODES" and mode != "EDIT_NODES":
            self.clear_wall_nodes()

        self.current_mode = mode

        # Propagate mode to current canvas
        if self.current_canvas:
            self.current_canvas.mode = mode

        self.status_bar.showMessage(f"Mode: {mode}")
        self.reset_drawing_state()

        if mode == "EDIT_NODES":
            self.spawn_wall_nodes()

    def reset_drawing_state(self):
        self.drawing_start_point = None
        if self.temp_line_item:
            try:
                if self.temp_line_item.scene():
                    self.temp_line_item.scene().removeItem(self.temp_line_item)
            except RuntimeError:
                pass
            self.temp_line_item = None

        if self.temp_rect_item:
            try:
                if self.temp_rect_item.scene():
                    self.temp_rect_item.scene().removeItem(self.temp_rect_item)
            except RuntimeError:
                pass
            self.temp_rect_item = None

    def spawn_wall_nodes(self):
        """
        Creates WallNodeItems at every unique wall endpoint in the scene.
        """
        self.clear_wall_nodes()

        if not self.current_canvas: return

        # Map location -> Node Item
        # to merge shared nodes
        loc_map = {}

        walls = []
        for item in self.current_canvas.scene.items():
            if isinstance(item, WallItem):
                walls.append(item)

        threshold = 5.0 # pixels to merge

        for w in walls:
            line = w.line()
            p1 = line.p1()
            p2 = line.p2()

            # Check p1
            node1 = None
            for loc, node in loc_map.items():
                if math.sqrt((loc.x()-p1.x())**2 + (loc.y()-p1.y())**2) < threshold:
                    node1 = node
                    break
            if not node1:
                node1 = WallNodeItem(p1)
                self.current_canvas.scene.addItem(node1)
                loc_map[p1] = node1
                self.active_wall_nodes.append(node1)

            # Check p2
            node2 = None
            for loc, node in loc_map.items():
                if math.sqrt((loc.x()-p2.x())**2 + (loc.y()-p2.y())**2) < threshold:
                    node2 = node
                    break
            if not node2:
                node2 = WallNodeItem(p2)
                self.current_canvas.scene.addItem(node2)
                loc_map[p2] = node2
                self.active_wall_nodes.append(node2)

            # Link wall to nodes
            w.start_node = node1
            w.end_node = node2

    def clear_wall_nodes(self):
        for node in self.active_wall_nodes:
            if node.scene():
                node.scene().removeItem(node)
        self.active_wall_nodes.clear()

        # Unlink walls
        if self.current_canvas:
            for item in self.current_canvas.scene.items():
                if isinstance(item, WallItem):
                    item.start_node = None
                    item.end_node = None

    def handle_canvas_click(self, point):
        # Handle Right Click logic if needed, but standard Qt events separate Press/Click.
        # But this method is called by a Signal from PlanCanvas.
        # We need to update PlanCanvas to distinguish clicks or buttons.
        # Currently, PlanCanvas only emits point_clicked on LeftButton.

        # Delegate to existing logic but using current_canvas
        if self.current_mode == "DRAW_WALL":
            point = self.find_snap_point(point)

        if self.current_mode == "CALIBRATE":
            self._handle_calibrate_click(point)
        elif self.current_mode == "DRAW_WALL":
            self._handle_wall_click(point)
        elif self.current_mode == "ADD_AP":
            self._handle_ap_click(point)
        elif self.current_mode == "DRAW_ZONE":
            self._handle_zone_click(point)

    def _handle_calibrate_click(self, point):
        if not self.drawing_start_point:
            self.drawing_start_point = point
        else:
            end_point = point
            dist_px = math.sqrt((end_point.x() - self.drawing_start_point.x())**2 +
                                (end_point.y() - self.drawing_start_point.y())**2)

            self.reset_drawing_state()

            if dist_px < 5:
                return

            dialog = CalibrationDialog(dist_px, self)
            if dialog.exec():
                real_dist = dialog.real_distance
                ppm = dist_px / real_dist

                # Update Floor Scale
                self.current_floor.pixels_per_meter = ppm
                self.lbl_ppm.setText(f"Scale: {ppm:.2f} px/m")
                self.status_bar.showMessage(f"Calibrated: {ppm:.2f} px/m")
                self.set_mode("SELECT")

    def _handle_wall_click(self, point):
        if not self.drawing_start_point:
            self.drawing_start_point = point
        else:
            end_point = point
            # Create Wall
            mat_name = self.combo_materials.currentText()
            wall_mats = {m['name']: m for m in self.materials_data.get('materials', [])}
            color = wall_mats.get(mat_name, {}).get('color', '#000000')

            wall_item = WallItem(
                (self.drawing_start_point.x(), self.drawing_start_point.y()),
                (end_point.x(), end_point.y()),
                mat_name,
                color
            )

            cmd = AddWallCommand(self.current_canvas.scene, wall_item)
            self.undo_stack.push(cmd)

            # Reset temp line but keep drawing from new end point if polyline desired
            # But the user asked for: "if I right click, I should be able to draw a new wall not associated to the old node."
            # This implies by default it IS associated.
            # So here we want to CONTINUE drawing.

            if self.temp_line_item:
                if self.temp_line_item.scene():
                    self.temp_line_item.scene().removeItem(self.temp_line_item)
                self.temp_line_item = None

            self.drawing_start_point = point # Start next wall from end of this one
            self.trigger_heatmap()

            # Status update
            self.status_bar.showMessage("Wall added. Click to continue, Right-click to stop.")

    def _handle_ap_click(self, point):
        model = self.combo_aps.currentText()
        name = f"AP{self.project.next_ap_id:02}"
        self.project.next_ap_id += 1

        ap_item = AccessPointItem(point.x(), point.y(), model, name)

        cmd = AddAPCommand(self.current_canvas.scene, ap_item)
        self.undo_stack.push(cmd)

        self.trigger_heatmap()

    def _handle_zone_click(self, point):
        if not self.drawing_start_point:
            self.drawing_start_point = point
        else:
            end_point = point

            rect = QRectF(self.drawing_start_point, end_point).normalized()

            self.reset_drawing_state()

            # Prompt for Height
            h, ok = QInputDialog.getDouble(self, "Ceiling Height", "Enter Ceiling Height (m):", 3.0, 1.0, 50.0, 2)

            if ok:
                zone_item = ZoneItem(rect, h)
                self.current_canvas.scene.addItem(zone_item)
                self.status_bar.showMessage("Zone Added.")

    def handle_canvas_move(self, point):
        # Update Wall Nodes logic (Handled by WallItem.update_positions called via itemChange in Node)
        # We need to make sure update positions is called.
        # WallNodeItem sends geometry changes, but WallItem needs to listen?
        # In my items.py code, I didn't implement the listener fully.
        # But here in handle_canvas_move, we are tracking mouse movement for drawing tools.
        # Node dragging is handled by QGraphicsItem standard movable flags and ItemChange.
        # We need to hook into the scene update or implement the link.

        # Let's fix the Node dragging update in the loop below or via signal.
        # Since QGraphicsItem doesn't emit signals easily, we can check selection/movement here?
        # Actually, `handle_canvas_move` is called on mouseMoveEvent of View.

        if self.current_mode == "EDIT_NODES":
            # Check if any node is moving?
            # Better: iterate walls and call update_positions()
            # This is inefficient but works for Phase 2.
            if self.current_canvas:
                for item in self.current_canvas.scene.items():
                    if isinstance(item, WallItem):
                        item.update_positions()

        if self.current_mode in ["CALIBRATE", "DRAW_WALL"] and self.drawing_start_point:
            if self.current_mode == "DRAW_WALL":
                point = self.find_snap_point(point)

            if not self.temp_line_item:
                self.temp_line_item = QGraphicsLineItem()
                pen = QPen()
                if self.current_mode == "CALIBRATE":
                    pen.setColor(Qt.red)
                else:
                    pen.setColor(Qt.blue)
                pen.setWidth(2)
                self.temp_line_item.setPen(pen)
                self.current_canvas.scene.addItem(self.temp_line_item)

            line = self.temp_line_item.line()
            line.setP1(self.drawing_start_point)
            line.setP2(point)
            self.temp_line_item.setLine(line)

        elif self.current_mode == "DRAW_ZONE" and self.drawing_start_point:
            if not self.temp_rect_item:
                self.temp_rect_item = QGraphicsRectItem()
                self.temp_rect_item.setPen(QPen(Qt.blue, 1, Qt.DashLine))
                self.current_canvas.scene.addItem(self.temp_rect_item)

            rect = QRectF(self.drawing_start_point, point).normalized()
            self.temp_rect_item.setRect(rect)

    def handle_canvas_release(self, point):
        # Handle Move AP
        scene = self.current_canvas.scene
        selected = scene.selectedItems()
        if len(selected) == 1 and isinstance(selected[0], AccessPointItem):
            item = selected[0]
            if self.selected_item_start_pos is not None:
                new_pos = item.pos()
                if new_pos != self.selected_item_start_pos:
                    cmd = MoveCommand(item, self.selected_item_start_pos, new_pos)
                    self.undo_stack.push(cmd)
                    self.selected_item_start_pos = new_pos
                    self.trigger_heatmap()

    def on_selection_changed(self):
        if not self.current_canvas: return
        selected = self.current_canvas.scene.selectedItems()
        if len(selected) == 1 and isinstance(selected[0], AccessPointItem):
            self.selected_item_start_pos = selected[0].pos()
        else:
            self.selected_item_start_pos = None

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete:
            if not self.current_canvas: return
            scene = self.current_canvas.scene
            selected_items = scene.selectedItems()
            if selected_items:
                # Use Command
                cmd = DeleteCommand(scene, selected_items)
                self.undo_stack.push(cmd)
                self.status_bar.showMessage(f"Deleted {len(selected_items)} items.")
                self.trigger_heatmap()
        else:
            super().keyPressEvent(event)

    def handle_canvas_right_click(self, point):
        # Stop drawing
        if self.current_mode == "DRAW_WALL" and self.drawing_start_point:
            self.reset_drawing_state()
            self.status_bar.showMessage("Wall drawing stopped.")

    # --- Utility ---
    def find_snap_point(self, pos):
        if not self.current_canvas: return pos
        threshold = self.project.snap_threshold
        closest = None
        min_dist = float('inf')

        endpoints = []
        for item in self.current_canvas.scene.items():
            if isinstance(item, WallItem):
                l = item.line()
                endpoints.append((l.x1(), l.y1()))
                endpoints.append((l.x2(), l.y2()))

        for ep in endpoints:
            dist = math.sqrt((pos.x()-ep[0])**2 + (pos.y()-ep[1])**2)
            if dist < threshold and dist < min_dist:
                min_dist = dist
                closest = QPointF(ep[0], ep[1])

        return closest if closest else pos

    def trigger_heatmap(self):
        # Multi-floor Heatmap Logic
        if not self.current_canvas or not self.current_floor: return
        if self.current_floor.pixels_per_meter <= 0: return # No scale

        current_walls = []
        for item in self.current_canvas.scene.items():
            if isinstance(item, WallItem):
                l = item.line()
                current_walls.append({
                    'p1': (l.x1(), l.y1()),
                    'p2': (l.x2(), l.y2()),
                    'material': item.material_name
                })

        # Calculate Floor Z Levels
        sorted_floors = sorted(enumerate(self.project.floors), key=lambda x: x[1].floor_number)
        floor_z_map = {}
        current_z = 0.0
        for idx, f in sorted_floors:
            floor_z_map[idx] = current_z
            current_z += f.ceiling_height # Accumulate floor height

        target_floor_idx = self.tabs.currentIndex()
        target_z = floor_z_map.get(target_floor_idx, 0.0)

        # Collect APs with Accurate Z (Slab + Ceiling/Zone)
        all_aps = []

        for idx, floor in enumerate(self.project.floors):
            canvas = self.tabs.widget(idx) # PlanCanvas
            floor_slab_z = floor_z_map.get(idx, 0.0)

            # Identify Zones for this floor (if open in canvas, use items; else floor data)
            zones = []
            if canvas:
                 for item in canvas.scene.items():
                    if isinstance(item, ZoneItem):
                        zones.append(item)

            floor_aps = []
            if canvas:
                for item in canvas.scene.items():
                    if isinstance(item, AccessPointItem):
                        pos = item.scenePos()

                        # Calculate effective Z (Ceiling Height override)
                        ap_z_offset = floor.ceiling_height # Default

                        # Check Zones
                        for z_item in zones:
                            if z_item.mapToScene(z_item.boundingRect()).contains(pos):
                                ap_z_offset = z_item.ceiling_height
                                break

                        floor_aps.append({
                            'x': pos.x(),
                            'y': pos.y(),
                            'z': floor_slab_z + ap_z_offset, # Absolute Z
                            'model': item.model_name
                        })
            else:
                # Fallback to stored data if tab not active?
                # For robust multi-floor, we should read stored APs if canvas closed,
                # but currently we keep all tabs open.
                pass
            all_aps.extend(floor_aps)

        if not all_aps:
            return

        self.status_bar.showMessage("Generating Heatmap...")
        QApplication.processEvents()

        # Ensure heatmap_item attribute exists if we init tabs dynamically
        if not hasattr(self.current_canvas, 'heatmap_item'):
            self.current_canvas.heatmap_item = None

        # Remove existing heatmap before calculating bounds
        if self.current_canvas.heatmap_item:
            if self.current_canvas.heatmap_item.scene() == self.current_canvas.scene:
                self.current_canvas.scene.removeItem(self.current_canvas.heatmap_item)
            self.current_canvas.heatmap_item = None

        # Update to use the full scene rect (including moved images)
        # We use itemsBoundingRect to get the extent of all items (Image, Walls, APs)
        rect = self.current_canvas.scene.itemsBoundingRect()
        width = int(rect.width())
        height = int(rect.height())

        # Also need top-left offset to place the pixmap correctly
        offset_x = rect.x()
        offset_y = rect.y()

        if width <= 0 or height <= 0: return

        rssi_grid = generate_heatmap(
            width, height,
            self.current_floor.pixels_per_meter,
            all_aps,
            current_walls,
            self.hardware_data,
            self.materials_data,
            frequency_band=self.combo_band.currentText(),
            resolution=20,
            target_z=target_z,
            floors_config=self.project.floors,
            floor_z_map=floor_z_map,
            origin_offset=(offset_x, offset_y) # Pass origin
        )

        pixmap = heatmap_to_pixmap(rssi_grid, width, height,
                                   self.project.heatmap_min_dbm,
                                   self.project.heatmap_max_dbm)

        self.current_canvas.heatmap_item = QGraphicsPixmapItem(pixmap)

        # Position heatmap correctly at the top-left of the bounding rect
        self.current_canvas.heatmap_item.setPos(offset_x, offset_y)

        self.current_canvas.heatmap_item.setZValue(10)
        self.current_canvas.scene.addItem(self.current_canvas.heatmap_item)
        self.status_bar.showMessage("Heatmap generated.")

    def save_project(self):
        # Sync Scene items back to Floor objects before saving
        for idx, floor in enumerate(self.project.floors):
            canvas = self.tabs.widget(idx)
            if canvas:
                # Walls
                walls = []
                for item in canvas.scene.items():
                    if isinstance(item, WallItem):
                        l = item.line()
                        walls.append({
                            'p1': (l.x1(), l.y1()),
                            'p2': (l.x2(), l.y2()),
                            'material': item.material_name
                        })
                floor.walls = walls

                # APs
                aps = []
                for item in canvas.scene.items():
                    if isinstance(item, AccessPointItem):
                        aps.append({
                            'x': item.scenePos().x(),
                            'y': item.scenePos().y(),
                            'model': item.model_name,
                            'name': item.name
                        })
                floor.access_points = aps

                # Zones
                zones = []
                for item in canvas.scene.items():
                    if isinstance(item, ZoneItem):
                         r = item.rect()
                         zones.append({
                             'rect': [r.x(), r.y(), r.width(), r.height()],
                             'height': item.ceiling_height
                         })
                floor.regions = zones

        file_path, _ = QFileDialog.getSaveFileName(self, "Save Project", "", "WiFi Project (*.wifi)")
        if file_path:
            save_project(file_path, self.project)
            self.status_bar.showMessage(f"Saved to {file_path}")

    def open_project(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Project", "", "WiFi Project (*.wifi)")
        if file_path:
            proj = load_project(file_path)
            if proj:
                self.project = proj
                # Clear UI
                self.tabs.clear()
                # Rebuild UI
                for floor in self.project.floors:
                    self._add_tab_for_floor(floor)
                self.status_bar.showMessage(f"Loaded {file_path}")

    def undo_last_action(self):
        if self.undo_stack.undo():
            self.trigger_heatmap()

    def open_settings(self):
        dialog = SettingsDialog(self.project.heatmap_min_dbm,
                                self.project.heatmap_max_dbm,
                                self.project.snap_threshold, self)
        if dialog.exec():
            v = dialog.get_values()
            self.project.heatmap_min_dbm = v[0]
            self.project.heatmap_max_dbm = v[1]
            self.project.snap_threshold = v[2]

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
