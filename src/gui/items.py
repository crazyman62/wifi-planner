from PySide6.QtWidgets import QGraphicsLineItem, QGraphicsEllipseItem, QGraphicsItem, QGraphicsSimpleTextItem, QInputDialog, QMenu, QGraphicsRectItem
from PySide6.QtGui import QPen, QColor, QBrush
from PySide6.QtCore import Qt, QPointF

class WallNodeItem(QGraphicsEllipseItem):
    """
    A handle for a wall endpoint.
    """
    def __init__(self, point, parent=None):
        r = 6
        super().__init__(point.x() - r, point.y() - r, 2*r, 2*r, parent)
        self.setBrush(QBrush(QColor("blue")))
        self.setPen(QPen(Qt.white))
        self.setFlags(QGraphicsItem.ItemIsSelectable | QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemSendsGeometryChanges)
        self.setZValue(5) # Above walls

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            # We need to update connected walls
            # But we don't know them directly unless we store references or parent observes.
            # Best practice: Signal or callback? QGraphicsItems don't have signals.
            # We can rely on Scene to handle this, or store list of connected walls.
            pass
        return super().itemChange(change, value)


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

        # References to nodes (managed by Canvas/Tool)
        self.start_node = None
        self.end_node = None

    def paint(self, painter, option, widget=None):
        if self.isSelected():
            pen = QPen(QColor(Qt.yellow)) # Highlight color
            pen.setWidth(6)
            painter.setPen(pen)
        else:
            painter.setPen(self.default_pen)

        painter.drawLine(self.line())

    def update_positions(self):
        if self.start_node and self.end_node:
            line = self.line()
            # Node pos is top-left of rect? No, if we center it...
            # We need center of node.
            p1 = self.start_node.scenePos() + QPointF(6, 6) # Radius offset correction if needed?
            # Actually WallNodeItem is placed at (x-r, y-r). scenePos gives (x-r, y-r).
            # Center is scenePos + (r, r).

            # Wait, itemChange ItemPositionChange returns the new position of the item's origin (top-left of rect).
            # Let's verify `AccessPointItem` logic.
            # If we just use center() of rect in local coords mapped to scene?

            r = 6
            c1 = self.start_node.sceneBoundingRect().center()
            c2 = self.end_node.sceneBoundingRect().center()

            line.setP1(c1)
            line.setP2(c2)
            self.setLine(line)

class AccessPointItem(QGraphicsEllipseItem):
    def __init__(self, x, y, model_name, name="AP", parent=None):
        # Radius 10px
        r = 10
        # Initialize centered at local (0,0)
        super().__init__(-r, -r, 2 * r, 2 * r, parent)

        # Set scene position
        self.setPos(x, y)

        self.model_name = model_name
        self.name = name

        # Appearance
        self.setBrush(QBrush(QColor("green")))
        self.setPen(QPen(Qt.black))

        # Flags
        self.setFlags(QGraphicsItem.ItemIsSelectable |
                      QGraphicsItem.ItemIsMovable |
                      QGraphicsItem.ItemSendsGeometryChanges)

        # Text Label
        self.text_item = QGraphicsSimpleTextItem(self.name, self)
        self.text_item.setBrush(QBrush(Qt.black))
        self._update_text_pos()

    def set_name(self, name):
        self.name = name
        self.text_item.setText(name)
        self._update_text_pos()

    def _update_text_pos(self):
        # Center text below the circle
        rect = self.text_item.boundingRect()
        r = 10
        x_center = 0 # Center of circle (0,0)
        y_bottom = r + 2
        self.text_item.setPos(x_center - rect.width() / 2, y_bottom)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.scene():
            pass
        return super().itemChange(change, value)

    def paint(self, painter, option, widget=None):
        if self.isSelected():
            self.setPen(QPen(QColor(Qt.yellow), 2))
        else:
            self.setPen(QPen(Qt.black, 1))
        super().paint(painter, option, widget)

    def contextMenuEvent(self, event):
        menu = QMenu()
        rename_action = menu.addAction("Rename")
        delete_action = menu.addAction("Delete")
        action = menu.exec(event.screenPos())
        if action == rename_action:
            new_name, ok = QInputDialog.getText(None, "Rename AP", "New Name:", text=self.name)
            if ok and new_name:
                self.set_name(new_name)
        elif action == delete_action:
            pass

class ZoneItem(QGraphicsRectItem):
    """
    Rectangular zone for ceiling height overrides.
    """
    def __init__(self, rect, ceiling_height, parent=None):
        super().__init__(rect, parent)
        self.ceiling_height = ceiling_height

        # Appearance
        self.setBrush(QBrush(QColor(100, 100, 255, 50))) # Semi-transparent blue
        self.setPen(QPen(Qt.blue, 1, Qt.DashLine))

        self.setFlags(QGraphicsItem.ItemIsSelectable | QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemSendsGeometryChanges)

        # Label
        self.text_item = QGraphicsSimpleTextItem(f"H: {ceiling_height}m", self)
        self.text_item.setBrush(QBrush(Qt.blue))
        self.text_item.setPos(rect.x() + 5, rect.y() + 5)

    def set_height(self, h):
        self.ceiling_height = h
        self.text_item.setText(f"H: {h}m")
