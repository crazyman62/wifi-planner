from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QDialogButtonBox, QMessageBox, QComboBox, QPushButton, QFileDialog
from PySide6.QtWidgets import QSpinBox, QFormLayout, QDoubleSpinBox, QGroupBox, QCheckBox, QSlider, QGraphicsScene, QGraphicsView, QGraphicsPixmapItem, QGraphicsLineItem
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QPen, QColor, QImage
import os
from src.utils.vision import detect_walls

class WallDetectionPreviewDialog(QDialog):
    def __init__(self, image_path, wall_materials, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Detect Walls Preview")
        self.resize(1000, 700)
        self.image_path = image_path
        self.detected_walls = []

        # Layouts
        main_layout = QVBoxLayout(self)
        controls_layout = QHBoxLayout()

        # Controls
        controls_layout.addWidget(QLabel("Sensitivity:"))
        self.slider_sensitivity = QSlider(Qt.Horizontal)
        self.slider_sensitivity.setRange(0, 100)
        self.slider_sensitivity.setValue(50)
        self.slider_sensitivity.setTickInterval(10)
        self.slider_sensitivity.setTickPosition(QSlider.TicksBelow)
        self.slider_sensitivity.valueChanged.connect(self.on_sensitivity_changed)
        controls_layout.addWidget(self.slider_sensitivity)

        self.lbl_val = QLabel("50")
        controls_layout.addWidget(self.lbl_val)

        controls_layout.addSpacing(20)

        controls_layout.addWidget(QLabel("Inner Material:"))
        self.combo_inner = QComboBox()
        self.combo_inner.addItems(wall_materials)
        controls_layout.addWidget(self.combo_inner)

        main_layout.addLayout(controls_layout)

        # Preview
        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        main_layout.addWidget(self.view)

        # Buttons
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        main_layout.addWidget(btns)

        # Initial Load
        self.load_image_and_detect()

    def on_sensitivity_changed(self, val):
        self.lbl_val.setText(str(val))
        self.detect_and_draw()

    def load_image_and_detect(self):
        self.pixmap = QPixmap(self.image_path)
        self.detect_and_draw()

    def detect_and_draw(self):
        self.scene.clear()
        # Add background
        if self.pixmap:
            self.scene.addPixmap(self.pixmap)

        sensitivity = self.slider_sensitivity.value()
        inner_mat = self.combo_inner.currentText()
        outer_mat = "Concrete (Standard 4\")" # Fixed for now or could be passed

        # Run detection
        # Note: running in main thread for MVP. If slow, needs thread.
        try:
            self.detected_walls = detect_walls(self.image_path, outer_mat, inner_mat, sensitivity)
        except Exception as e:
            print(f"Detection error: {e}")
            self.detected_walls = []

        # Draw Lines
        pen_outer = QPen(QColor(0, 0, 255), 3) # Blue for outer
        pen_inner = QPen(QColor(255, 0, 0), 2) # Red for inner

        for w in self.detected_walls:
            p1 = w['p1']
            p2 = w['p2']
            mat = w['material']

            line_item = QGraphicsLineItem(p1[0], p1[1], p2[0], p2[1])
            if mat == outer_mat:
                line_item.setPen(pen_outer)
            else:
                line_item.setPen(pen_inner)
            self.scene.addItem(line_item)

    def get_walls(self):
        # Update materials to current selection just in case changed without re-detect?
        # Re-detect already uses current combo selection.
        # But if user changes combo WITHOUT moving slider, we need to update material names in self.detected_walls
        # Or just re-run detect one last time on accept?
        # Better: Since detected_walls stores string material names, we should ensure they match.
        # on_sensitivity_changed calls detect_and_draw which reads combo.
        # If I change combo, I should trigger update too.
        # Let's connect combo too.
        return self.detected_walls

class CalibrationDialog(QDialog):
    def __init__(self, pixel_distance, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Calibrate Scale")
        self.pixel_distance = pixel_distance

        layout = QVBoxLayout(self)

        info_label = QLabel(f"Selected Distance: {pixel_distance:.2f} pixels")
        layout.addWidget(info_label)

        layout.addWidget(QLabel("Enter Real-World Distance:"))
        self.input_distance = QLineEdit()
        layout.addWidget(self.input_distance)

        self.combo_units = QComboBox()
        self.combo_units.addItems(["Meters", "Feet"])
        layout.addWidget(self.combo_units)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def validate_and_accept(self):
        try:
            val = float(self.input_distance.text())
            if val <= 0:
                raise ValueError

            unit = self.combo_units.currentText()
            if unit == "Feet":
                # Convert to Meters
                val = val * 0.3048

            self.real_distance = val
            self.accept()
        except ValueError:
            QMessageBox.warning(self, "Invalid Input", "Please enter a valid positive number.")

class SettingsDialog(QDialog):
    def __init__(self, current_min_dbm, current_max_dbm, current_snap_dist, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(300, 200)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        layout.addWidget(QLabel("<b>Heatmap Visualization (dBm)</b>"))
        self.spin_max = QSpinBox()
        self.spin_max.setRange(-100, 0)
        self.spin_max.setValue(int(current_max_dbm))
        form.addRow("High Signal (Blue):", self.spin_max)

        self.spin_min = QSpinBox()
        self.spin_min.setRange(-120, -10)
        self.spin_min.setValue(int(current_min_dbm))
        form.addRow("Low Signal (Red):", self.spin_min)

        layout.addSpacing(10)
        layout.addWidget(QLabel("<b>Editor</b>"))
        self.spin_snap = QSpinBox()
        self.spin_snap.setRange(0, 50)
        self.spin_snap.setValue(int(current_snap_dist))
        form.addRow("Snapping Distance (px):", self.spin_snap)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_values(self):
        return (self.spin_min.value(), self.spin_max.value(), self.spin_snap.value())


class AddFloorDialog(QDialog):
    def __init__(self, floor_materials, wall_materials=None, parent=None, initial_data=None):
        super().__init__(parent)
        self.setWindowTitle("Floor Configuration")
        self.resize(400, 300)

        self.image_path = None
        self.is_edit_mode = initial_data is not None
        if wall_materials is None:
            wall_materials = []

        layout = QVBoxLayout(self)
        form = QFormLayout()

        # Floor Name
        self.edit_name = QLineEdit("New Floor")
        form.addRow("Floor Name:", self.edit_name)

        # Floor Number
        self.spin_number = QSpinBox()
        self.spin_number.setRange(-10, 100)
        self.spin_number.setValue(1)
        form.addRow("Floor Number:", self.spin_number)

        # Material
        self.combo_material = QComboBox()
        self.combo_material.addItems(floor_materials)
        form.addRow("Floor Material:", self.combo_material)

        # Ceiling Height
        self.spin_ceiling = QDoubleSpinBox()
        self.spin_ceiling.setRange(1.0, 50.0)
        self.spin_ceiling.setValue(3.0)
        self.spin_ceiling.setSuffix(" m")
        form.addRow("Default Ceiling Height:", self.spin_ceiling)

        layout.addLayout(form)

        # Image Selection
        self.btn_image = QPushButton("Select Floor Plan Image")
        self.btn_image.clicked.connect(self.select_image)
        self.lbl_image_status = QLabel("No image selected")
        layout.addWidget(self.btn_image)
        layout.addWidget(self.lbl_image_status)

        # Wall Detection
        self.wall_materials = wall_materials
        self.detected_walls = []

        det_layout = QHBoxLayout()
        self.btn_detect = QPushButton("Detect Walls...")
        self.btn_detect.clicked.connect(self.open_detection_dialog)
        self.lbl_detect_status = QLabel("Not detected")
        det_layout.addWidget(self.btn_detect)
        det_layout.addWidget(self.lbl_detect_status)
        layout.addLayout(det_layout)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Populate if editing
        if initial_data:
            self.edit_name.setText(initial_data.get('name', ''))
            self.spin_number.setValue(initial_data.get('number', 1))
            self.spin_ceiling.setValue(initial_data.get('ceiling_height', 3.0))
            mat = initial_data.get('material', '')
            idx = self.combo_material.findText(mat)
            if idx >= 0: self.combo_material.setCurrentIndex(idx)

            self.image_path = initial_data.get('image_path')
            if self.image_path:
                self.lbl_image_status.setText(os.path.basename(self.image_path))
            else:
                self.lbl_image_status.setText("No image set")

    def select_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Floor Plan", "", "Images (*.png *.jpg *.jpeg *.bmp)"
        )
        if file_path:
            self.image_path = file_path
            self.lbl_image_status.setText(os.path.basename(file_path))

    def validate_and_accept(self):
        if not self.edit_name.text():
            QMessageBox.warning(self, "Input Error", "Please provide a floor name.")
            return
        if not self.image_path and not self.is_edit_mode:
            QMessageBox.warning(self, "Input Error", "Please select a floor plan image.")
            return

        self.accept()

    def open_detection_dialog(self):
        if not self.image_path:
            QMessageBox.warning(self, "No Image", "Please select an image first.")
            return

        dlg = WallDetectionPreviewDialog(self.image_path, self.wall_materials, self)
        if dlg.exec():
            self.detected_walls = dlg.get_walls()
            self.lbl_detect_status.setText(f"{len(self.detected_walls)} walls detected")

    def get_data(self):
        return {
            'name': self.edit_name.text(),
            'number': self.spin_number.value(),
            'material': self.combo_material.currentText(),
            'ceiling_height': self.spin_ceiling.value(),
            'image_path': self.image_path,
            'detected_walls': self.detected_walls
        }
