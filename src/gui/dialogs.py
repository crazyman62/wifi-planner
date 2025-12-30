from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QDialogButtonBox, QMessageBox

class CalibrationDialog(QDialog):
    def __init__(self, pixel_distance, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Calibrate Scale")
        self.pixel_distance = pixel_distance

        layout = QVBoxLayout(self)

        info_label = QLabel(f"Selected Distance: {pixel_distance:.2f} pixels")
        layout.addWidget(info_label)

        layout.addWidget(QLabel("Enter Real-World Distance (meters):"))
        self.input_meters = QLineEdit()
        layout.addWidget(self.input_meters)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def validate_and_accept(self):
        try:
            val = float(self.input_meters.text())
            if val <= 0:
                raise ValueError
            self.real_distance = val
            self.accept()
        except ValueError:
            QMessageBox.warning(self, "Invalid Input", "Please enter a valid positive number.")
