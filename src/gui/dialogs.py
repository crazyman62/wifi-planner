from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QDialogButtonBox, QMessageBox, QComboBox, QPushButton, QFileDialog
from PySide6.QtWidgets import QSpinBox, QFormLayout, QDoubleSpinBox, QGroupBox, QCheckBox
import os

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

        # Auto-detect Walls
        self.grp_autodetect = QGroupBox("Auto-Detect Walls")
        self.grp_autodetect.setCheckable(True)
        self.grp_autodetect.setChecked(False)
        auto_layout = QFormLayout(self.grp_autodetect)

        self.combo_inner_mat = QComboBox()
        self.combo_inner_mat.addItems(wall_materials)
        if wall_materials:
             # Default to something reasonable if available, or just first
             pass
        auto_layout.addRow("Inner Wall Material:", self.combo_inner_mat)

        layout.addWidget(self.grp_autodetect)

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

            # Disable autodetect by default on edit
            self.grp_autodetect.setChecked(False)

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

    def get_data(self):
        return {
            'name': self.edit_name.text(),
            'number': self.spin_number.value(),
            'material': self.combo_material.currentText(),
            'ceiling_height': self.spin_ceiling.value(),
            'image_path': self.image_path,
            'auto_detect': self.grp_autodetect.isChecked(),
            'inner_material': self.combo_inner_mat.currentText()
        }
