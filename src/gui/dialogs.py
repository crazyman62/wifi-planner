from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QDialogButtonBox, QMessageBox, QComboBox

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

from PySide6.QtWidgets import QSpinBox, QFormLayout

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
