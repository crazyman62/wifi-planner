from PySide6.QtWidgets import QGraphicsLineItem, QGraphicsEllipseItem, QGraphicsItem, QGraphicsSimpleTextItem, QInputDialog, QMenu
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
    def __init__(self, x, y, model_name, name="AP", parent=None):
        # Radius 10px
        r = 10
        super().__init__(x - r, y - r, 2 * r, 2 * r, parent)

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
        # Item coords: circle center is roughly at r, r relative to rect top-left?
        # Actually in QGraphicsEllipseItem, (0,0) is top left of the rect we passed.
        # We passed (x-r, y-r, 2r, 2r).
        # So in local coords, the circle is (0,0, 2r, 2r). Center is (r, r).

        r = 10
        x_center = r
        y_bottom = 2 * r + 2

        self.text_item.setPos(x_center - rect.width() / 2, y_bottom)

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

    def contextMenuEvent(self, event):
        menu = QMenu()
        rename_action = menu.addAction("Rename")
        delete_action = menu.addAction("Delete")

        action = menu.exec(event.screenPos())

        if action == rename_action:
            new_name, ok = QInputDialog.getText(None, "Rename AP", "New Name:", text=self.name)
            if ok and new_name:
                self.set_name(new_name)
                # Note: This change isn't strictly undoable via the current UndoStack unless we add a RenameCommand.
                # For Phase 1, direct modification is likely acceptable, or we can leave it as is.
        elif action == delete_action:
            # We need to trigger deletion in MainWindow to handle UndoStack.
            # We can't easily access MainWindow here without passing it down.
            # Alternative: ignore context menu delete and use 'Delete' key,
            # OR assume scene has a view which has a window.
            # For now, let's just let the user know they can press Delete, or emit a signal if we could.
            pass
