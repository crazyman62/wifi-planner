from PySide6.QtWidgets import QGraphicsLineItem, QGraphicsEllipseItem, QGraphicsItem
from PySide6.QtGui import QPen, QColor, QBrush
from PySide6.QtCore import Qt

class WallItem(QGraphicsLineItem):
    def __init__(self, p1, p2, material_name, color_hex, parent=None):
        super().__init__(p1[0], p1[1], p2[0], p2[1], parent)
        self.material_name = material_name
        self.color_hex = color_hex

        # Appearance
        self.default_pen = QPen(QColor(color_hex))
        self.default_pen.setWidth(4)
        self.setPen(self.default_pen)

        # Flags
        self.setFlags(QGraphicsItem.ItemIsSelectable)

    def paint(self, painter, option, widget=None):
        # Override paint to handle selection appearance if needed,
        # or rely on standard dashed line for selection.
        # For simple lines, standard Qt selection style is usually a dashed box around it,
        # which looks ugly for lines. Let's make the line thicker or change color when selected.

        if self.isSelected():
            pen = QPen(QColor(Qt.yellow)) # Highlight color
            pen.setWidth(6)
            painter.setPen(pen)
        else:
            painter.setPen(self.default_pen)

        painter.drawLine(self.line())

class AccessPointItem(QGraphicsEllipseItem):
    def __init__(self, x, y, model_name, parent=None):
        # Radius 10px
        r = 10
        super().__init__(x - r, y - r, 2 * r, 2 * r, parent)

        self.model_name = model_name

        # Appearance
        self.setBrush(QBrush(QColor("green")))
        self.setPen(QPen(Qt.black))

        # Flags
        self.setFlags(QGraphicsItem.ItemIsSelectable |
                      QGraphicsItem.ItemIsMovable |
                      QGraphicsItem.ItemSendsGeometryChanges)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.scene():
            # Notify scene or parent if needed for live updates,
            # but for Undo/Redo we handle it via mouse release in MainWindow or Canvas.
            pass
        return super().itemChange(change, value)

    def paint(self, painter, option, widget=None):
        if self.isSelected():
            self.setPen(QPen(QColor(Qt.yellow), 2))
        else:
            self.setPen(QPen(Qt.black, 1))

        super().paint(painter, option, widget)
