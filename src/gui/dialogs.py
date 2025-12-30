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
