import sys
import json
import os
import math
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                               QHBoxLayout, QPushButton, QFileDialog, QLabel,
                               QToolBar, QStatusBar, QComboBox, QListWidget, QSpinBox,
                               QInputDialog, QTabWidget, QDoubleSpinBox, QMenu, QMessageBox, QFormLayout, QCheckBox)
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
from src.engine.auto_planner import run_auto_planner

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WiFi Predictive Planner - Phase 3")
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

        # Top Toolbar
        self.top_toolbar_widget = QWidget()
        self.top_toolbar_layout = QHBoxLayout(self.top_toolbar_widget)
        self.top_toolbar_layout.setContentsMargins(0, 0, 0, 0)

        # Right Side (Toolbar + Tabs)
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(self.top_toolbar_widget)
        right_layout.addWidget(self.tabs)

        container = QWidget()
        main_layout = QHBoxLayout(container)
        main_layout.addWidget(sidebar_widget, stretch=1)
        main_layout.addWidget(right_widget, stretch=5)
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
        self._create_top_toolbar()
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

        export_action = QAction("Export Report (PDF)", self)
        export_action.triggered.connect(self.export_report)
        file_menu.addAction(export_action)

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
        self.btn_edit_nodes = QPushButton("Edit Wall Nodes")
        self.btn_draw_zone = QPushButton("Draw Ceiling Zone")
        self.btn_add_ap = QPushButton("Add AP")
        self.btn_move_floor = QPushButton("Move Floor Plan")

        self.btn_select.clicked.connect(lambda: self.set_mode("SELECT"))
        self.btn_select.setToolTip("Select items or pan the view")

        self.btn_calibrate.clicked.connect(lambda: self.set_mode("CALIBRATE"))
        self.btn_calibrate.setToolTip("Calibrate the floor plan scale by drawing a line of known length")

        self.btn_draw_wall.clicked.connect(lambda: self.set_mode("DRAW_WALL"))
        self.btn_draw_wall.setToolTip("Draw walls by clicking endpoints. Right-click to stop.")

        self.btn_edit_nodes.clicked.connect(lambda: self.set_mode("EDIT_NODES"))
        self.btn_edit_nodes.setToolTip("Drag wall endpoints to adjust connections")

        self.btn_draw_zone.clicked.connect(lambda: self.set_mode("DRAW_ZONE"))
        self.btn_draw_zone.setToolTip("Define an area with a specific ceiling height")

        self.btn_add_ap.clicked.connect(lambda: self.set_mode("ADD_AP"))
        self.btn_add_ap.setToolTip("Place a new Access Point on the map")

        self.btn_move_floor.clicked.connect(lambda: self.set_mode("MOVE_FLOOR"))
        self.btn_move_floor.setToolTip("Drag the floor plan image to align it")

        self.sidebar_layout.addWidget(self.btn_select)
        self.sidebar_layout.addWidget(self.btn_calibrate)
        self.sidebar_layout.addWidget(self.btn_draw_wall)
        self.sidebar_layout.addWidget(self.btn_edit_nodes)
        self.sidebar_layout.addWidget(self.btn_draw_zone)
        self.sidebar_layout.addWidget(self.btn_add_ap)
        self.sidebar_layout.addWidget(self.btn_move_floor)

        self.lbl_ppm = QLabel("Scale: Not Calibrated")
        self.sidebar_layout.addWidget(self.lbl_ppm)

        # Alignment Tools
        self.sidebar_layout.addSpacing(10)
        self.sidebar_layout.addWidget(QLabel("<b>Floor Alignment</b>"))

        align_layout = QVBoxLayout()
        self.spin_x = QDoubleSpinBox()
        self.spin_x.setRange(-100000, 100000)
        self.spin_x.setPrefix("X: ")
        self.spin_x.valueChanged.connect(self.update_floor_transform)
        align_layout.addWidget(self.spin_x)

        self.spin_y = QDoubleSpinBox()
        self.spin_y.setRange(-100000, 100000)
        self.spin_y.setPrefix("Y: ")
        self.spin_y.valueChanged.connect(self.update_floor_transform)
        align_layout.addWidget(self.spin_y)

        # Rotation Controls with 90 deg buttons
        rot_layout = QHBoxLayout()
        self.btn_rot_left = QPushButton("-90°")
        self.btn_rot_left.clicked.connect(self.rotate_left)
        self.btn_rot_left.setToolTip("Rotate floor 90° Counter-Clockwise")

        self.spin_rot = QDoubleSpinBox()
        self.spin_rot.setRange(-360, 360)
        self.spin_rot.setPrefix("Rot: ")
        self.spin_rot.valueChanged.connect(self.update_floor_transform)
        self.spin_rot.setToolTip("Fine-tune rotation angle")

        self.btn_rot_right = QPushButton("+90°")
        self.btn_rot_right.clicked.connect(self.rotate_right)
        self.btn_rot_right.setToolTip("Rotate floor 90° Clockwise")

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
        self.spin_scale.setToolTip("Adjust the display scale of the floor plan image")
        align_layout.addWidget(self.spin_scale)

        self.chk_ghost = QPushButton("Toggle Ghost Floor")
        self.chk_ghost.setCheckable(True)
        self.chk_ghost.clicked.connect(self.toggle_ghost_floor)
        self.chk_ghost.setToolTip("Overlay the floor below to help with alignment")
        align_layout.addWidget(self.chk_ghost)

        self.sidebar_layout.addLayout(align_layout)

        self.sidebar_layout.addStretch()

        # Settings
        self.btn_settings = QPushButton("Settings")
        self.btn_settings.clicked.connect(self.open_settings)
        self.sidebar_layout.addSpacing(10)
        self.sidebar_layout.addWidget(QLabel("<b>Properties</b>"))

        self.zone_props_widget = QWidget()
        zp_layout = QFormLayout(self.zone_props_widget)
        self.spin_zone_height = QDoubleSpinBox()
        self.spin_zone_height.setRange(0, 50)
        self.spin_zone_height.setSuffix(" m")
        self.spin_zone_height.valueChanged.connect(self.update_selected_zone_height)
        zp_layout.addRow("Zone Height:", self.spin_zone_height)
        self.sidebar_layout.addWidget(self.zone_props_widget)
        self.zone_props_widget.hide()

        # AP Properties Widget
        self.ap_props_widget = QWidget()
        ap_layout = QFormLayout(self.ap_props_widget)

        self.combo_ap_mounting = QComboBox()
        self.combo_ap_mounting.addItems(["Ceiling", "Wall"])
        self.combo_ap_mounting.currentTextChanged.connect(self.update_selected_ap_mounting)
        ap_layout.addRow("Mounting:", self.combo_ap_mounting)

        self.spin_ap_rotation = QDoubleSpinBox()
        self.spin_ap_rotation.setRange(0, 360)
        self.spin_ap_rotation.setSuffix("°")
        self.spin_ap_rotation.valueChanged.connect(self.update_selected_ap_rotation)
        ap_layout.addRow("Direction:", self.spin_ap_rotation)

        # Radio Props (Band Specific)
        ap_layout.addRow(QLabel("<b>Radio Config</b>"))
        self.combo_channel = QComboBox()
        self.combo_channel.currentTextChanged.connect(self.update_selected_ap_channel)
        ap_layout.addRow("Channel:", self.combo_channel)

        self.combo_width = QComboBox()
        self.combo_width.currentTextChanged.connect(self.update_selected_ap_width)
        ap_layout.addRow("Width (MHz):", self.combo_width)

        self.combo_power = QComboBox()
        self.combo_power.addItems(["Auto", "Low", "Medium", "High"])
        self.combo_power.currentTextChanged.connect(self.update_selected_ap_power)
        ap_layout.addRow("Tx Power:", self.combo_power)

        self.chk_manual_radio = QCheckBox("Lock Settings (Manual)")
        self.chk_manual_radio.toggled.connect(self.update_selected_ap_manual_lock)
        ap_layout.addRow("", self.chk_manual_radio)

        self.sidebar_layout.addWidget(self.ap_props_widget)
        self.ap_props_widget.hide()

        self.sidebar_layout.addWidget(self.btn_settings)

    def _create_top_toolbar(self):
        # Wall Material
        self.top_toolbar_layout.addWidget(QLabel("<b>Wall Material:</b>"))
        self.combo_materials = QComboBox()
        # Parse material names from complex structure
        wall_mats = self.materials_data.get('materials', [])
        self.combo_materials.addItems([m['name'] for m in wall_mats])
        self.top_toolbar_layout.addWidget(self.combo_materials)

        self.top_toolbar_layout.addSpacing(20)

        # AP Selection
        self.top_toolbar_layout.addWidget(QLabel("<b>AP Model:</b>"))
        self.combo_aps = QComboBox()
        if self.hardware_data:
            self.combo_aps.addItems(list(self.hardware_data.keys()))
        self.top_toolbar_layout.addWidget(self.combo_aps)

        self.top_toolbar_layout.addSpacing(20)

        # Band Selection
        self.top_toolbar_layout.addWidget(QLabel("<b>Freq Band (GHz):</b>"))
        self.combo_band = QComboBox()
        self.combo_band.addItems(["2.4", "5", "6"])
        self.combo_band.setCurrentText("5")
        self.combo_band.currentIndexChanged.connect(self.trigger_heatmap)
        self.combo_band.currentIndexChanged.connect(self.update_material_combo_labels)
        self.combo_band.currentIndexChanged.connect(self.update_wall_tooltips)
        # Also need to update radio props widget if an AP is selected
        self.combo_band.currentIndexChanged.connect(self.on_selection_changed)
        self.top_toolbar_layout.addWidget(self.combo_band)

        self.top_toolbar_layout.addStretch()

        # Initial update of labels
        self.update_material_combo_labels()

    def _create_statusbar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.lbl_signal_strength = QLabel("Signal: N/A")
        self.lbl_signal_strength.setMinimumWidth(150)
        self.lbl_signal_strength.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.status_bar.addPermanentWidget(self.lbl_signal_strength)

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
        wall_mats = self.materials_data.get('materials', [])
        wall_mat_names = [m['name'] for m in wall_mats]
        dialog = AddFloorDialog(self.floor_material_names, wall_mat_names, self, initial_data=initial_data)

        if dialog.exec():
            data = dialog.get_data()

            # Update Object
            floor.name = data['name']
            floor.floor_number = data['number']
            floor.material_name = data['material']
            floor.ceiling_height = data['ceiling_height']

            # Check for changes that require scene refresh
            image_changed = (data['image_path'] and data['image_path'] != floor.image_path)
            detected_walls = data.get('detected_walls')

            if image_changed or detected_walls:
                canvas = self.tabs.widget(index)
                if canvas:
                    # Sync scene -> floor object (preserve other items if only walls updated?)

                    # 1. Capture current APs/Zones from Scene
                    current_aps = []
                    current_zones = []
                    for item in canvas.scene.items():
                         if isinstance(item, AccessPointItem):
                            # Use pos() if parented, scenePos() if not?
                            # When we populate, we parent to pixmap.
                            # So pos() is local.
                            # But AccessPointItem might store local?
                            # We want to store LOCAL coords in the floor object so they stick to image.
                            # If pixmap exists, pos() is relative to pixmap.
                            # If no pixmap, pos() is scene pos.
                            # This unifies it.

                            # However, currently the code uses scenePos().
                            # We will change this in _sync_canvas_to_floor.
                            pass

                    # 2. Update Floor Object
                    # (Logic inside _sync_canvas_to_floor handles this)
                    self._sync_canvas_to_floor(canvas, floor)

                    if image_changed:
                        floor.image_path = data['image_path']

                    if detected_walls:
                        floor.walls = detected_walls
                        self.status_bar.showMessage(f"Updated walls: {len(detected_walls)} segments.")
                    elif image_changed:
                         # Walls are already synced via _sync_canvas_to_floor above
                         pass

                    # 3. Refresh Scene
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
                # Line is always local coords. If parented to pixmap, it's relative to pixmap. Correct.
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
                # Use pos() which is local to parent (pixmap if exists)
                aps.append({
                    'x': item.pos().x(),
                    'y': item.pos().y(),
                    'model': item.model_name,
                    'name': item.name,
                    'mounting': item.mounting,
                    'rotation': item.rotation,
                    'radios': item.radios # Save Radios
                })
        floor.access_points = aps

        # Zones
        zones = []
        for item in canvas.scene.items():
            if isinstance(item, ZoneItem):
                 # rect() is local geometry (0,0,w,h usually)
                 # pos() is position
                 # We need the rect relative to parent.
                 # ZoneItem is a QGraphicsRectItem.
                 # rect() returns the rect in item coords.
                 # mapRectToParent(rect()) gives rect in parent coords.
                 r = item.mapRectToParent(item.rect())
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
        wall_mats = self.materials_data.get('materials', [])
        wall_mat_names = [m['name'] for m in wall_mats]
        dialog = AddFloorDialog(self.floor_material_names, wall_mat_names, self)
        if dialog.exec():
            data = dialog.get_data()
            new_floor = Floor(
                name=data['name'],
                number=data['number'],
                material_name=data['material'],
                image_path=data['image_path']
            )
            new_floor.ceiling_height = data['ceiling_height']

            # Auto-Detect Walls
            detected_walls = data.get('detected_walls')
            if detected_walls:
                new_floor.walls = detected_walls
                self.status_bar.showMessage(f"Added floor with {len(detected_walls)} detected walls.")

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
        # Determine parent (Pixmap or Scene)
        parent = canvas.pixmap_item if canvas.pixmap_item else None

        # Walls
        wall_mats = {m['name']: m for m in self.materials_data.get('materials', [])}
        current_band = self.combo_band.currentText()

        for w in floor.walls:
            # Helper to normalize access
            def get_val(item, key, default):
                return item.get(key, default) if isinstance(item, dict) else getattr(item, key, default)

            p1 = get_val(w, 'p1', (0,0))
            p2 = get_val(w, 'p2', (0,0))
            mat = get_val(w, 'material', 'Concrete')

            mat_data = wall_mats.get(mat, {})
            color_hex = mat_data.get('color', '#000000')
            wall_item = WallItem((p1[0], p1[1]), (p2[0], p2[1]), mat, color_hex)

            if parent:
                wall_item.setParentItem(parent)
            else:
                canvas.scene.addItem(wall_item)

            # Set Tooltip
            loss = mat_data.get('loss', {}).get(current_band, 0.0)
            wall_item.setToolTip(f"Material: {mat}\nLoss: {loss} dB @ {current_band} GHz")


        # APs
        for ap in floor.access_points:
            x = ap['x'] if isinstance(ap, dict) else ap.x
            y = ap['y'] if isinstance(ap, dict) else ap.y
            model = ap['model'] if isinstance(ap, dict) else ap.model
            name = ap['name'] if isinstance(ap, dict) else ap.name
            mounting = ap.get('mounting', 'Ceiling') if isinstance(ap, dict) else getattr(ap, 'mounting', 'Ceiling')
            rotation = ap.get('rotation', 0.0) if isinstance(ap, dict) else getattr(ap, 'rotation', 0.0)
            radios = ap.get('radios') if isinstance(ap, dict) else getattr(ap, 'radios', None)

            ap_item = AccessPointItem(x, y, model, name, mounting, rotation, radios=radios)
            if parent:
                ap_item.setParentItem(parent)
            else:
                canvas.scene.addItem(ap_item)


        # Zones
        for z in floor.regions:
            # z is dict from JSON
            x, y, w, h = z.get('rect', [0,0,10,10])
            height = z.get('height', 3.0)

            zone_item = ZoneItem(QRectF(x, y, w, h), height)
            if parent:
                zone_item.setParentItem(parent)
            else:
                canvas.scene.addItem(zone_item)

    def on_tab_changed(self, index):
        floor = self.project.get_floor(index)
        if floor:
            # Sync mode
            if self.current_canvas:
                self.current_canvas.mode = self.current_mode

            # Update UI controls for this floor
            # Block signals on individual controls to prevent update_floor_transform from firing
            # and overwriting the new floor with old values or vice versa during the switch.
            self.spin_x.blockSignals(True)
            self.spin_y.blockSignals(True)
            self.spin_rot.blockSignals(True)
            self.spin_scale.blockSignals(True)

            self.spin_x.setValue(floor.x_offset)
            self.spin_y.setValue(floor.y_offset)
            self.spin_rot.setValue(floor.rotation)
            self.spin_scale.setValue(floor.scale_factor)

            self.spin_x.blockSignals(False)
            self.spin_y.blockSignals(False)
            self.spin_rot.blockSignals(False)
            self.spin_scale.blockSignals(False)

            if floor.pixels_per_meter:
                self.lbl_ppm.setText(f"Scale: {floor.pixels_per_meter:.2f} px/m")
            else:
                self.lbl_ppm.setText("Scale: Not Calibrated")

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
                self.current_canvas.set_active_layer_opacity(1.0)

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
                self.current_canvas.set_active_layer_opacity(0.6)
        else:
            self.status_bar.showMessage("No floor below to display.")
            self.current_canvas.set_ghost_image(None)
            self.current_canvas.set_active_layer_opacity(1.0)

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

        # Parent for nodes: should be same as walls (pixmap)
        parent = self.current_canvas.pixmap_item if self.current_canvas.pixmap_item else None

        walls = []
        for item in self.current_canvas.scene.items():
            if isinstance(item, WallItem):
                walls.append(item)
                # If walls are parented, we need to iterate child items of pixmap?
                # scene.items() returns ALL items recursively. Good.

        threshold = 5.0 # pixels to merge

        for w in walls:
            line = w.line()
            p1 = line.p1()
            p2 = line.p2()

            # These are local coords (relative to pixmap if parented)
            # WallNodeItem should also be parented to pixmap and use local coords.

            # Check p1
            node1 = None
            for loc, node in loc_map.items():
                if math.sqrt((loc.x()-p1.x())**2 + (loc.y()-p1.y())**2) < threshold:
                    node1 = node
                    break
            if not node1:
                node1 = WallNodeItem(p1)
                if parent:
                    node1.setParentItem(parent)
                else:
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
                if parent:
                    node2.setParentItem(parent)
                else:
                    self.current_canvas.scene.addItem(node2)
                loc_map[p2] = node2
                self.active_wall_nodes.append(node2)

            # Link wall to nodes
            w.start_node = node1
            w.end_node = node2

            if w not in node1.walls:
                node1.walls.append(w)
            if w not in node2.walls:
                node2.walls.append(w)

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
        # point is in Scene Coordinates.

        # If we have a pixmap, map to Local Coordinates
        if self.current_canvas and self.current_canvas.pixmap_item:
             local_point = self.current_canvas.pixmap_item.mapFromScene(point)
             # Use local point for creating items
             processing_point = local_point
        else:
             processing_point = point

        # Delegate to existing logic but using current_canvas
        if self.current_mode == "DRAW_WALL":
            # Snapping needs to check existing walls.
            # existing walls are in local coords if parented.
            # find_snap_point expects pos in SAME system as walls.
            processing_point = self.find_snap_point(processing_point)

        if self.current_mode == "CALIBRATE":
            self._handle_calibrate_click(processing_point)
        elif self.current_mode == "DRAW_WALL":
            self._handle_wall_click(processing_point)
        elif self.current_mode == "ADD_AP":
            self._handle_ap_click(processing_point)
        elif self.current_mode == "DRAW_ZONE":
            self._handle_zone_click(processing_point)

    def _handle_calibrate_click(self, point):
        # Calibrate works on visual distance.
        # If point is local to pixmap, distance is in "unscaled" image pixels?
        # pixmap.scale() is applied to visualization.
        # If we draw on pixmap, we are in image pixels.
        # "Pixels per Meter" should be relative to the image pixels.

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

            idx = self.combo_materials.currentIndex()
            all_mats = self.materials_data.get('materials', [])
            if 0 <= idx < len(all_mats):
                mat_data = all_mats[idx]
                mat_name = mat_data['name']
                color = mat_data.get('color', '#000000')
            else:
                mat_name = "Concrete"
                color = "#000000"
                # Define default mat_data to avoid UnboundLocalError
                mat_data = {'name': mat_name, 'loss': {}}

            wall_item = WallItem(
                (self.drawing_start_point.x(), self.drawing_start_point.y()),
                (end_point.x(), end_point.y()),
                mat_name,
                color
            )

            # Parent to pixmap
            if self.current_canvas.pixmap_item:
                wall_item.setParentItem(self.current_canvas.pixmap_item)
            else:
                self.current_canvas.scene.addItem(wall_item)

            # Set Initial Tooltip
            band = self.combo_band.currentText()
            loss = mat_data.get('loss', {}).get(band, 0.0)
            wall_item.setToolTip(f"Material: {mat_name}\nLoss: {loss} dB @ {band} GHz")

            cmd = AddWallCommand(self.current_canvas.scene, wall_item)
            self.undo_stack.push(cmd)

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

        # Parent
        if self.current_canvas.pixmap_item:
             ap_item.setParentItem(self.current_canvas.pixmap_item)
        else:
             self.current_canvas.scene.addItem(ap_item)

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

                if self.current_canvas.pixmap_item:
                    zone_item.setParentItem(self.current_canvas.pixmap_item)
                else:
                    self.current_canvas.scene.addItem(zone_item)

                self.status_bar.showMessage("Zone Added.")

    def handle_canvas_move(self, point):
        # point is Scene Pos

        # For temp drawing, we need to map to parent coords if we parent temp item.
        # OR we just draw temp item in scene coords.
        # Temp lines are typically transient. Drawing them on scene is easier visually?
        # But if we are snapping to local points, we must be consistent.
        # Let's map point to local if applicable.

        scene_point = point
        if self.current_canvas and self.current_canvas.pixmap_item:
             point = self.current_canvas.pixmap_item.mapFromScene(point)

        # Heatmap Signal Status (uses Scene Pos usually?)
        # heatmap_data['origin'] is Scene Offset.
        # So for signal check, we use scene_point.
        if self.current_canvas and hasattr(self.current_canvas, 'heatmap_data'):
            hd = self.current_canvas.heatmap_data
            if hd:
                # Calculate Grid Index
                ox, oy = hd['origin']
                res = hd['resolution']
                w_px = hd['width']
                h_px = hd['height']

                # Local coords relative to heatmap origin
                lx = scene_point.x() - ox
                ly = scene_point.y() - oy

                if 0 <= lx < w_px and 0 <= ly < h_px:
                    # Map to grid index
                    gx = int(lx / res)
                    gy = int(ly / res)

                    # Max Grid
                    grid = hd['grid']
                    # Individual Grids (ap_grids is a dict)
                    ap_grids = hd.get('ap_grids', {})

                    val = -100.0
                    if 0 <= gy < grid.shape[0] and 0 <= gx < grid.shape[1]:
                        val = grid[gy, gx]

                    if val > -90.0:
                        # Find contributing APs
                        contributing = []
                        for ap_name, ap_grid in ap_grids.items():
                            if 0 <= gy < ap_grid.shape[0] and 0 <= gx < ap_grid.shape[1]:
                                ap_val = ap_grid[gy, gx]
                                if ap_val > -90.0:
                                    contributing.append(f"{ap_name}: {ap_val:.1f}")

                        contributing.sort(key=lambda s: float(s.split(': ')[1]), reverse=True)

                        tooltip_text = f"Max: {val:.1f} dBm"
                        if contributing:
                            tooltip_text += " | " + " ".join(contributing)

                        self.lbl_signal_strength.setText(tooltip_text)
                    else:
                        self.lbl_signal_strength.setText("Signal: N/A")
                else:
                     self.lbl_signal_strength.setText("Signal: N/A")

        # Update Wall Nodes logic
        if self.current_mode == "EDIT_NODES":
            if self.current_canvas:
                for item in self.current_canvas.scene.items():
                    if isinstance(item, WallItem):
                        item.update_positions()

        if self.current_mode in ["CALIBRATE", "DRAW_WALL"] and self.drawing_start_point:
            if self.current_mode == "DRAW_WALL":
                point = self.find_snap_point(point) # Local point

            if not self.temp_line_item:
                self.temp_line_item = QGraphicsLineItem()
                pen = QPen()
                if self.current_mode == "CALIBRATE":
                    pen.setColor(Qt.red)
                else:
                    pen.setColor(Qt.blue)
                pen.setWidth(2)
                self.temp_line_item.setPen(pen)

                # Parent temp line to pixmap so it moves/rotates/scales correctly while drawing?
                # Yes, if we are drawing in local space.
                if self.current_canvas.pixmap_item:
                     self.temp_line_item.setParentItem(self.current_canvas.pixmap_item)
                else:
                     self.current_canvas.scene.addItem(self.temp_line_item)


            line = self.temp_line_item.line()
            line.setP1(self.drawing_start_point)
            line.setP2(point)
            self.temp_line_item.setLine(line)

        elif self.current_mode == "DRAW_ZONE" and self.drawing_start_point:
            if not self.temp_rect_item:
                self.temp_rect_item = QGraphicsRectItem()
                self.temp_rect_item.setPen(QPen(Qt.blue, 1, Qt.DashLine))
                if self.current_canvas.pixmap_item:
                     self.temp_rect_item.setParentItem(self.current_canvas.pixmap_item)
                else:
                     self.current_canvas.scene.addItem(self.temp_rect_item)

            rect = QRectF(self.drawing_start_point, point).normalized()
            self.temp_rect_item.setRect(rect)

    def handle_canvas_release(self, point):
        # Handle Move Floor Plan
        if self.current_mode == "MOVE_FLOOR" and self.current_canvas and self.current_canvas.pixmap_item:
            # Sync position back to UI and Object
            pos = self.current_canvas.pixmap_item.pos()
            # Avoid triggering updates while setting values
            self.blockSignals(True)
            self.spin_x.setValue(pos.x())
            self.spin_y.setValue(pos.y())
            self.blockSignals(False)

            # Update Object (since we blocked signals)
            self.current_floor.x_offset = pos.x()
            self.current_floor.y_offset = pos.y()

            self.trigger_heatmap()
            return

        # Handle Move AP
        scene = self.current_canvas.scene
        selected = scene.selectedItems()
        if len(selected) == 1 and isinstance(selected[0], AccessPointItem):
            item = selected[0]

            # Snap to Wall if Wall Mounted
            if item.mounting == "Wall":
                self._snap_ap_to_wall(item)

            if self.selected_item_start_pos is not None:
                new_pos = item.pos()
                if new_pos != self.selected_item_start_pos:
                    cmd = MoveCommand(item, self.selected_item_start_pos, new_pos)
                    self.undo_stack.push(cmd)
                    self.selected_item_start_pos = new_pos
                    self.trigger_heatmap()

                    # Update rotation spinner if snap changed it
                    if self.ap_props_widget.isVisible():
                        self.spin_ap_rotation.blockSignals(True)
                        self.spin_ap_rotation.setValue(item.rotation)
                        self.spin_ap_rotation.blockSignals(False)

    def _snap_ap_to_wall(self, ap_item):
        """Snaps an AP to the closest wall and orients it."""
        scene = self.current_canvas.scene
        closest_dist = 50.0 # Pixel threshold
        best_point = None
        best_angle = None

        ap_pos = ap_item.pos() # Local

        # WallItems
        # If walls are children, we can find them.
        # Iterate all scene items is robust, but checks everything.

        for item in scene.items():
            if isinstance(item, WallItem):
                line = item.line()
                p1 = line.p1()
                p2 = line.p2()

                # Project point to segment
                v_wall = p2 - p1
                wall_len_sq = v_wall.x()**2 + v_wall.y()**2
                if wall_len_sq == 0: continue

                v_ap = ap_pos - p1
                t = (v_ap.x()*v_wall.x() + v_ap.y()*v_wall.y()) / wall_len_sq
                t = max(0, min(1, t))

                proj = p1 + v_wall * t
                dist = math.sqrt((ap_pos.x() - proj.x())**2 + (ap_pos.y() - proj.y())**2)

                if dist < closest_dist:
                    closest_dist = dist
                    best_point = proj

                    # Determine Normal Angle
                    # Wall vector: (dx, dy)
                    # Normal: (-dy, dx) or (dy, -dx).
                    # We want the normal pointing towards the AP's original position (away from wall).
                    dx = v_wall.x()
                    dy = v_wall.y()

                    normal1 = QPointF(-dy, dx)
                    normal2 = QPointF(dy, -dx)

                    # Vector from Wall to AP
                    v_out = ap_pos - proj

                    # Dot product to check direction
                    dot1 = normal1.x()*v_out.x() + normal1.y()*v_out.y()

                    final_normal = normal1 if dot1 >= 0 else normal2

                    # Angle of normal
                    angle_rad = math.atan2(final_normal.y(), final_normal.x())
                    angle_deg = math.degrees(angle_rad)
                    best_angle = (angle_deg + 360) % 360

        if best_point:
            ap_item.setPos(best_point)
            if best_angle is not None:
                ap_item.set_rotation(best_angle)

    def on_selection_changed(self):
        if not self.current_canvas: return
        selected = self.current_canvas.scene.selectedItems()

        self.zone_props_widget.hide()
        self.ap_props_widget.hide()

        if len(selected) == 1:
            item = selected[0]
            if isinstance(item, AccessPointItem):
                self.selected_item_start_pos = item.pos()
                self.ap_props_widget.show()
                self.combo_ap_mounting.blockSignals(True)
                self.combo_ap_mounting.setCurrentText(item.mounting)
                self.combo_ap_mounting.blockSignals(False)

                self.spin_ap_rotation.blockSignals(True)
                self.spin_ap_rotation.setValue(item.rotation)
                self.spin_ap_rotation.blockSignals(False)

                # Load Radio Config for current band
                self._load_ap_radio_props(item)

            elif isinstance(item, ZoneItem):
                self.selected_item_start_pos = None
                self.zone_props_widget.show()
                self.spin_zone_height.blockSignals(True)
                self.spin_zone_height.setValue(item.ceiling_height)
                self.spin_zone_height.blockSignals(False)
            elif isinstance(item, WallItem):
                self.selected_item_start_pos = None
                # Sync Dropdown to Wall Material
                # We need to find the index that corresponds to item.material_name
                # The dropdown now contains "Material (dB)" strings.
                # We can fuzzy match or rely on order if preserved?
                # The order is preserved from self.materials_data['materials'].

                mat_list = self.materials_data.get('materials', [])
                for i, m in enumerate(mat_list):
                    if m['name'] == item.material_name:
                        self.combo_materials.setCurrentIndex(i)
                        break
            else:
                 self.selected_item_start_pos = None
        else:
            self.selected_item_start_pos = None

    def update_selected_zone_height(self, val):
        if not self.current_canvas: return
        selected = self.current_canvas.scene.selectedItems()
        if len(selected) == 1 and isinstance(selected[0], ZoneItem):
            selected[0].set_height(val)
            self.trigger_heatmap()

    def update_selected_ap_mounting(self, text):
        if not self.current_canvas: return
        selected = self.current_canvas.scene.selectedItems()
        if len(selected) == 1 and isinstance(selected[0], AccessPointItem):
            selected[0].mounting = text
            self.trigger_heatmap()

    def update_selected_ap_rotation(self, val):
        if not self.current_canvas: return
        selected = self.current_canvas.scene.selectedItems()
        if len(selected) == 1 and isinstance(selected[0], AccessPointItem):
            selected[0].set_rotation(val)
            self.trigger_heatmap()

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
        # Trigger Auto Planner before heatmap
        # This updates APs in place
        run_auto_planner(self)

        # If selection matches, reload UI
        if self.current_canvas:
            selected = self.current_canvas.scene.selectedItems()
            if len(selected) == 1 and isinstance(selected[0], AccessPointItem):
                 self._load_ap_radio_props(selected[0])

        # Multi-floor Heatmap Logic
        if not self.current_canvas or not self.current_floor: return
        if self.current_floor.pixels_per_meter <= 0: return # No scale

        current_walls = []
        for item in self.current_canvas.scene.items():
            if isinstance(item, WallItem):
                l = item.line()
                # Need Global Coords for heatmap!
                p1 = item.mapToScene(l.p1())
                p2 = item.mapToScene(l.p2())

                current_walls.append({
                    'p1': (p1.x(), p1.y()),
                    'p2': (p2.x(), p2.y()),
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
                        pos = item.scenePos() # GLOBAL POS

                        # Calculate effective Z (Ceiling Height override)
                        ap_z_offset = floor.ceiling_height # Default

                        # Check Zones
                        for z_item in zones:
                            poly = z_item.mapToScene(z_item.boundingRect())
                            if poly.containsPoint(pos, Qt.OddEvenFill):
                                ap_z_offset = z_item.ceiling_height
                                break

                        # Adjust Z for Ceiling mount to ensure correct floor penetration logic
                        # If Ceiling, AP is slightly below the slab above.
                        effective_z = floor_slab_z + ap_z_offset
                        if item.mounting == "Ceiling":
                            effective_z -= 0.01

                        floor_aps.append({
                            'x': pos.x(),
                            'y': pos.y(),
                            'z': effective_z, # Absolute Z
                            'model': item.model_name,
                            'name': item.name,
                            'mounting': item.mounting,
                            'rotation': item.rotation
                        })
            else:
                # Fallback to stored data if tab not active?
                # For robust multi-floor, we should read stored APs if canvas closed,
                # but currently we keep all tabs open.

                # IMPORTANT: 'floor.access_points' stores LOCAL coords now if we saved properly!
                # If we rely on 'floor.access_points' when canvas is closed, we need to know the transform to get Global.
                # Since we keep tabs open, this path is less critical, but for correctness:
                # We need to apply floor.x_offset, y_offset, rotation, scale to these points.

                # For this task, we can assume tabs are open or logic is sufficient for active floor.
                # To be safe, let's just use what we have.

                for ap in floor.access_points:
                    # ap is dict
                    ap_z_offset = floor.ceiling_height

                    effective_z = floor_slab_z + ap_z_offset
                    if ap.get('mounting', 'Ceiling') == "Ceiling":
                        effective_z -= 0.01

                    # TODO: Transform local ap['x'], ap['y'] to Global if canvas not available.
                    # Ignoring for now as tabs are persistent in this app.

                    floor_aps.append({
                        'x': ap['x'],
                        'y': ap['y'],
                        'z': effective_z,
                        'model': ap['model'],
                        'name': ap['name'],
                        'mounting': ap.get('mounting', 'Ceiling'),
                        'rotation': ap.get('rotation', 0.0)
                    })

            all_aps.extend(floor_aps)

        if not all_aps:
            return

        self.status_bar.showMessage("Generating Heatmap...")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()

        try:
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

            # Add Padding/Bleed (e.g., 200 pixels margin)
            margin = 200
            rect.adjust(-margin, -margin, margin, margin)

            width = int(rect.width())
            height = int(rect.height())

            # Also need top-left offset to place the pixmap correctly
            offset_x = rect.x()
            offset_y = rect.y()

            if width <= 0 or height <= 0: return

            rssi_grid, ap_grids = generate_heatmap(
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

            # Store Heatmap Data for Tooltips
            self.current_canvas.heatmap_data = {
                'grid': rssi_grid,
                'ap_grids': ap_grids,
                'origin': (offset_x, offset_y),
                'resolution': 20,
                'width': width,
                'height': height
            }

            pixmap = heatmap_to_pixmap(rssi_grid, width, height,
                                       self.project.heatmap_min_dbm,
                                       self.project.heatmap_max_dbm)

            self.current_canvas.heatmap_item = QGraphicsPixmapItem(pixmap)

            # Position heatmap correctly at the top-left of the bounding rect
            self.current_canvas.heatmap_item.setPos(offset_x, offset_y)

            self.current_canvas.heatmap_item.setZValue(10)
            self.current_canvas.scene.addItem(self.current_canvas.heatmap_item)
            self.status_bar.showMessage("Heatmap generated.")
        finally:
            QApplication.restoreOverrideCursor()

    def save_project(self):
        # Sync Scene items back to Floor objects before saving
        for idx, floor in enumerate(self.project.floors):
            canvas = self.tabs.widget(idx)
            if canvas:
                self._sync_canvas_to_floor(canvas, floor)

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
        dialog = SettingsDialog(self.project.name,
                                self.project.heatmap_min_dbm,
                                self.project.heatmap_max_dbm,
                                self.project.snap_threshold, self)
        if dialog.exec():
            v = dialog.get_values()
            self.project.name = v[0]
            self.project.heatmap_min_dbm = v[1]
            self.project.heatmap_max_dbm = v[2]
            self.project.snap_threshold = v[3]

    def export_report(self):
        # Check Project Name
        if self.project.name == "New Project" or not self.project.name:
            reply = QMessageBox.question(self, "Project Name",
                                         "The project name is currently default ('New Project').\nDo you want to rename it before exporting?",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if reply == QMessageBox.Yes:
                new_name, ok = QInputDialog.getText(self, "Rename Project", "Project Name:", text=self.project.name)
                if ok and new_name:
                    self.project.name = new_name

        file_path, _ = QFileDialog.getSaveFileName(self, "Export PDF Report", "report.pdf", "PDF Files (*.pdf)")
        if not file_path:
            return

        self.status_bar.showMessage("Generating Report... Please wait.")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()

        original_tab_idx = self.tabs.currentIndex()
        original_band_idx = self.combo_band.currentIndex()

        # Temporarily disable Ghost Floor to ensure clean capture
        was_ghost_checked = self.chk_ghost.isChecked()
        if was_ghost_checked:
            self.chk_ghost.setChecked(False)
            # Ensure current ghost is removed immediately
            for idx in range(self.tabs.count()):
                w = self.tabs.widget(idx)
                if isinstance(w, PlanCanvas):
                    w.set_ghost_image(None)

        floors_data = []
        bom_aps = []

        try:
            # Collect Data
            for i, floor in enumerate(self.project.floors):
                # Sync current state to floor object (if currently active tab)
                if i == original_tab_idx:
                     self._sync_canvas_to_floor(self.current_canvas, floor)

                # Switch tab to ensure canvas exists and is sized correctly?
                # Ideally we render off-screen, but using the visible canvas is easier for maintaining state/transforms.
                self.tabs.setCurrentIndex(i)
                canvas = self.current_canvas
                QApplication.processEvents()

                floor_entry = {
                    'name': floor.name,
                    'bands': []
                }

                # BOM Collection
                # We need to make sure floor.access_points is up to date.
                # If we just switched tabs, _populate_canvas_items put items in scene.
                # But _sync_canvas_to_floor puts them back in floor object.
                # Let's read from the Scene items for BOM to be sure.
                for item in canvas.scene.items():
                    if isinstance(item, AccessPointItem):
                        bom_aps.append({
                            'name': item.name,
                            'model': item.model_name,
                            'floor_name': floor.name,
                            'radios': item.radios
                        })

                # Generate Bands
                for band in ["2.4", "5", "6"]:
                    self.combo_band.blockSignals(True)
                    self.combo_band.setCurrentText(band)
                    self.combo_band.blockSignals(False)

                    self.trigger_heatmap()
                    QApplication.processEvents() # Process events to ensure update

                    # Capture Image
                    # Render the whole scene (or itemsBoundingRect?)
                    # itemsBoundingRect might include ghost or negative space.
                    # We should align with what the user sees or the image rect.
                    # Ideally, use the Heatmap Rect or Image Rect.
                    # Since we added Bleed, itemsBoundingRect is large.
                    # Let's use itemsBoundingRect.

                    rect = canvas.scene.itemsBoundingRect()
                    if rect.width() > 0 and rect.height() > 0:
                        image = QImage(int(rect.width()), int(rect.height()), QImage.Format_ARGB32)
                        image.fill(Qt.white) # Background

                        painter = QPainter(image)
                        painter.setRenderHint(QPainter.Antialiasing)
                        # Direct render without manual translation (source rect handles it)
                        canvas.scene.render(painter, target=QRectF(0, 0, rect.width(), rect.height()), source=rect)
                        painter.end()

                        img_path = f"temp_f{i}_{band}.png"
                        image.save(img_path)
                        floor_entry['bands'].append({'band': band, 'image_path': img_path})

                floors_data.append(floor_entry)

            # Generate PDF
            report_gen = PDFReport(file_path)
            report_gen.generate_report(
                project_name=self.project.name,
                floors_data=floors_data,
                access_points=bom_aps,
                min_dbm=self.project.heatmap_min_dbm,
                max_dbm=self.project.heatmap_max_dbm
            )

            # Cleanup
            for floor in floors_data:
                for band_data in floor['bands']:
                    if os.path.exists(band_data['image_path']):
                        os.remove(band_data['image_path'])

            self.status_bar.showMessage(f"Report saved to {file_path}")

        except Exception as e:
            self.status_bar.showMessage(f"Error exporting report: {e}")
            print(f"Export Error: {e}")
        finally:
            QApplication.restoreOverrideCursor()
            # Restore state
            self.tabs.setCurrentIndex(original_tab_idx)
            self.combo_band.setCurrentIndex(original_band_idx)
            if was_ghost_checked:
                self.chk_ghost.setChecked(True)
                # self.update_ghost_view() will be called by on_tab_changed logic if we switch tabs?
                # We switched back to original_tab_idx.
                # on_tab_changed -> update_ghost_view if checked.
                # So ghost should reappear.

    def _load_ap_radio_props(self, ap_item):
        band = self.combo_band.currentText()
        config = ap_item.radios.get(band, {})

        # Populate Channels based on band
        self.combo_channel.blockSignals(True)
        self.combo_channel.clear()
        self.combo_channel.addItem("Auto")
        if band == "2.4":
            self.combo_channel.addItems([str(c) for c in [1, 6, 11]])
        elif band == "5":
            self.combo_channel.addItems([str(c) for c in [36, 40, 44, 48, 149, 153, 157, 161]])
        elif band == "6":
            self.combo_channel.addItems([str(c) for c in [1, 5, 9, 13, 17, 21]]) # Simplified

        curr_ch = str(config.get('channel', 'Auto'))
        idx = self.combo_channel.findText(curr_ch)
        if idx >= 0:
            self.combo_channel.setCurrentIndex(idx)
        else:
            self.combo_channel.setCurrentIndex(0) # Auto
        self.combo_channel.blockSignals(False)

        # Populate Widths
        self.combo_width.blockSignals(True)
        self.combo_width.clear()
        if band == "2.4":
            self.combo_width.addItems(["20", "40"])
        else:
            self.combo_width.addItems(["20", "40", "80", "160"])

        curr_bw = str(config.get('width', 20))
        idx = self.combo_width.findText(curr_bw)
        if idx >= 0:
            self.combo_width.setCurrentIndex(idx)
        else:
            self.combo_width.setCurrentIndex(0)
        self.combo_width.blockSignals(False)

        # Power
        self.combo_power.blockSignals(True)
        curr_pwr = str(config.get('power', 'Auto'))
        self.combo_power.setCurrentText(curr_pwr)
        self.combo_power.blockSignals(False)

        # Manual Lock
        self.chk_manual_radio.blockSignals(True)
        self.chk_manual_radio.setChecked(config.get('manual', False))
        self.chk_manual_radio.blockSignals(False)

    def update_selected_ap_channel(self, val):
        if not self.current_canvas: return
        selected = self.current_canvas.scene.selectedItems()
        if len(selected) == 1 and isinstance(selected[0], AccessPointItem):
            band = self.combo_band.currentText()
            item = selected[0]
            # If value is numeric, convert, else keep string "Auto"
            if val != "Auto":
                try:
                    val = int(val)
                except:
                    pass

            item.radios[band]['channel'] = val
            # Auto-lock if user changes it
            item.radios[band]['manual'] = True
            self.chk_manual_radio.setChecked(True)
            self.trigger_heatmap()

    def update_selected_ap_width(self, val):
        if not self.current_canvas: return
        selected = self.current_canvas.scene.selectedItems()
        if len(selected) == 1 and isinstance(selected[0], AccessPointItem):
            band = self.combo_band.currentText()
            item = selected[0]
            try:
                val = int(val)
            except:
                val = 20
            item.radios[band]['width'] = val
            item.radios[band]['manual'] = True
            self.chk_manual_radio.setChecked(True)
            self.trigger_heatmap()

    def update_selected_ap_power(self, val):
        if not self.current_canvas: return
        selected = self.current_canvas.scene.selectedItems()
        if len(selected) == 1 and isinstance(selected[0], AccessPointItem):
            band = self.combo_band.currentText()
            item = selected[0]
            item.radios[band]['power'] = val
            item.radios[band]['manual'] = True
            self.chk_manual_radio.setChecked(True)
            self.trigger_heatmap()

    def update_selected_ap_manual_lock(self, checked):
        if not self.current_canvas: return
        selected = self.current_canvas.scene.selectedItems()
        if len(selected) == 1 and isinstance(selected[0], AccessPointItem):
            band = self.combo_band.currentText()
            item = selected[0]
            item.radios[band]['manual'] = checked
            # If unlocking, trigger auto-calc?
            # Ideally yes, but auto-calc happens on move/add.
            # We can trigger generic update.
            self.trigger_heatmap()

    def update_material_combo_labels(self):
        """Updates the dropdown labels to include attenuation for the current band."""
        band = self.combo_band.currentText()
        current_idx = self.combo_materials.currentIndex()

        self.combo_materials.blockSignals(True)
        self.combo_materials.clear()

        wall_mats = self.materials_data.get('materials', [])

        items = []
        for m in wall_mats:
            name = m['name']
            loss = m.get('loss', {}).get(band, 0.0)
            items.append(f"{name} ({loss} dB)")

        self.combo_materials.addItems(items)

        if 0 <= current_idx < len(items):
            self.combo_materials.setCurrentIndex(current_idx)
        else:
             self.combo_materials.setCurrentIndex(0)

        self.combo_materials.blockSignals(False)

    def update_wall_tooltips(self):
        """Updates tooltips for all walls in all open tabs when the band changes."""
        band = self.combo_band.currentText()
        wall_mats = {m['name']: m for m in self.materials_data.get('materials', [])}

        # Iterate all tabs
        for i in range(self.tabs.count()):
            canvas = self.tabs.widget(i)
            if isinstance(canvas, PlanCanvas):
                for item in canvas.scene.items():
                    if isinstance(item, WallItem):
                        loss = wall_mats.get(item.material_name, {}).get(band, 0.0)
                        item.setToolTip(f"Material: {item.material_name}\nLoss: {loss} dB @ {band} GHz")

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
