from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsItem
from PySide6.QtGui import QPixmap, QPainter, QPen, QColor, QWheelEvent
from PySide6.QtCore import Qt, Signal, QPointF
from src.gui.items import WallItem, AccessPointItem

class PlanCanvas(QGraphicsView):
    """
    The main canvas for displaying the floor plan, walls, and heatmap.
    Supports Zooming and Panning.
    """

    # Signals for interactions
    point_clicked = Signal(QPointF)
    right_clicked = Signal(QPointF) # New signal for right click
    mouse_moved = Signal(QPointF)
    mouse_released = Signal(QPointF) # New signal for drag end

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        # Rendering hints for better quality
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)

        # Navigation flags
        self.setDragMode(QGraphicsView.NoDrag) # We will implement custom drag if needed, or use ScrollHandDrag
        self.setMouseTracking(True) # Enable hover events for signal inspection
        self._is_panning = False
        self._pan_start = QPointF(0, 0)
        self._mode = "SELECT"

        self.pixmap_item = None
        self.ghost_pixmap_item = None
        self.heatmap_item = None # Explicitly init attribute

        # Calibration state
        self.temp_line = None
        self.start_point = None
        self.is_drawing_line = False

    def load_image(self, image_path, x_offset=0, y_offset=0, rotation=0, scale_factor=1.0):
        """
        Loads a floor plan image onto the scene.
        """
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            return False

        if self.pixmap_item in self.scene.items():
            self.scene.removeItem(self.pixmap_item)

        self.pixmap_item = QGraphicsPixmapItem(pixmap)

        # Set Transform Origin to Center for better rotation
        cx = pixmap.width() / 2
        cy = pixmap.height() / 2
        self.pixmap_item.setTransformOriginPoint(cx, cy)

        # Apply Transforms
        # Scale (Image resolution scaling, distinct from View Zoom or Physics Scale)
        self.pixmap_item.setScale(scale_factor)

        # Rotation
        self.pixmap_item.setRotation(rotation)

        # Position (Offset)
        # Note: Position applies to the item's top-left in Scene coords.
        # Rotation applies around the center.
        self.pixmap_item.setPos(x_offset, y_offset)

        # Ensure Background is at bottom
        self.pixmap_item.setZValue(-100)

        self.scene.addItem(self.pixmap_item)

        # Set scene rect to include the image
        self.setSceneRect(self.pixmap_item.sceneBoundingRect())

        # Apply current mode flags
        self.mode = self._mode

        return True

    @property
    def mode(self):
        return self._mode

    @mode.setter
    def mode(self, value):
        self._mode = value
        if self.pixmap_item:
            if value == "MOVE_FLOOR":
                self.pixmap_item.setFlag(QGraphicsItem.ItemIsMovable, True)
                self.pixmap_item.setFlag(QGraphicsItem.ItemIsSelectable, True)
            else:
                self.pixmap_item.setFlag(QGraphicsItem.ItemIsMovable, False)
                self.pixmap_item.setFlag(QGraphicsItem.ItemIsSelectable, False)

    def set_ghost_image(self, image_path, x_offset=0, y_offset=0, rotation=0, scale_factor=1.0):
        """
        Sets a 'ghost' image of another floor (e.g. floor below).
        """
        if self.ghost_pixmap_item:
            self.scene.removeItem(self.ghost_pixmap_item)
            self.ghost_pixmap_item = None

        if not image_path:
            return

        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            return

        self.ghost_pixmap_item = QGraphicsPixmapItem(pixmap)

        # Center Origin for Ghost too
        cx = pixmap.width() / 2
        cy = pixmap.height() / 2
        self.ghost_pixmap_item.setTransformOriginPoint(cx, cy)

        self.ghost_pixmap_item.setOpacity(1.0) # Solid as requested
        self.ghost_pixmap_item.setScale(scale_factor)
        self.ghost_pixmap_item.setRotation(rotation)
        self.ghost_pixmap_item.setPos(x_offset, y_offset)
        self.ghost_pixmap_item.setZValue(-101) # Below the current floor map

        self.scene.addItem(self.ghost_pixmap_item)

    def set_active_layer_opacity(self, opacity):
        """
        Sets the opacity of the active floor elements (Image, Walls, APs).
        """
        if self.pixmap_item:
            self.pixmap_item.setOpacity(opacity)

        for item in self.scene.items():
            if isinstance(item, (WallItem, AccessPointItem)):
                item.setOpacity(opacity)

    def update_image_transform(self, x, y, rotation, scale):
        if self.pixmap_item:
            # Origin point persists, just update properties
            self.pixmap_item.setPos(x, y)
            self.pixmap_item.setRotation(rotation)
            self.pixmap_item.setScale(scale)
            # Update Scene Rect if needed, or let it grow
            # self.setSceneRect(self.pixmap_item.sceneBoundingRect())

    def wheelEvent(self, event: QWheelEvent):
        """
        Handles Scrolling logic.
        No Modifier: Zoom
        Ctrl: Vertical Pan
        Shift: Horizontal Pan
        """
        modifiers = event.modifiers()

        if modifiers & Qt.ControlModifier:
            # Vertical Pan
            delta = event.angleDelta().y()
            self.verticalScrollBar().setValue(int(self.verticalScrollBar().value() - delta))
            event.accept()
        elif modifiers & Qt.ShiftModifier:
            # Horizontal Pan (Use Y delta as most mice have one wheel)
            delta = event.angleDelta().y()
            self.horizontalScrollBar().setValue(int(self.horizontalScrollBar().value() - delta))
            event.accept()
        else:
            # Zoom (Default)
            zoom_in_factor = 1.15
            zoom_out_factor = 1 / zoom_in_factor

            # Save the scene pos
            old_pos = self.mapToScene(event.position().toPoint())

            # Zoom
            if event.angleDelta().y() > 0:
                zoom_factor = zoom_in_factor
            else:
                zoom_factor = zoom_out_factor

            self.scale(zoom_factor, zoom_factor)

            # Get the new position
            new_pos = self.mapToScene(event.position().toPoint())

            # Move scene to old position
            delta = new_pos - old_pos
            self.translate(delta.x(), delta.y())

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._is_panning = True
            self._pan_start = event.position()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
        elif event.button() == Qt.LeftButton:
            if self.mode == "SELECT":
                # Check if clicking on background -> Pan
                item = self.itemAt(event.position().toPoint())
                if item is None or item == self.pixmap_item or item == self.ghost_pixmap_item:
                    self._is_panning = True
                    self._pan_start = event.position()
                    self.setCursor(Qt.ClosedHandCursor)
                    event.accept()
                    return # Don't propagate or emit click if panning

                # Else clicking on an item -> Select/Move logic (default or custom)
                # But we also might want to emit point_clicked?
                # Usually if we click an item, we select it.
                # super().mousePressEvent handles selection.
                # MainWindow handles selectionChanged signal.

                # But if I select an item, I might still want to emit point_clicked for consistency?
                # Probably not needed for "SELECT" mode.

                pass

            # For Draw Modes, always emit click
            scene_pos = self.mapToScene(event.position().toPoint())
            self.point_clicked.emit(scene_pos)
            super().mousePressEvent(event)

        elif event.button() == Qt.RightButton:
            scene_pos = self.mapToScene(event.position().toPoint())
            self.right_clicked.emit(scene_pos)
            super().mousePressEvent(event)
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        scene_pos = self.mapToScene(event.position().toPoint())
        self.mouse_moved.emit(scene_pos)

        if self._is_panning:
            delta = event.position() - self._pan_start
            self._pan_start = event.position()

            self.horizontalScrollBar().setValue(int(self.horizontalScrollBar().value() - delta.x()))
            self.verticalScrollBar().setValue(int(self.verticalScrollBar().value() - delta.y()))
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._is_panning:
            self._is_panning = False
            self.setCursor(Qt.ArrowCursor)
            event.accept()

        if event.button() == Qt.LeftButton:
            # Emit release signal for move tracking
            scene_pos = self.mapToScene(event.position().toPoint())
            self.mouse_released.emit(scene_pos)
            super().mouseReleaseEvent(event)
        else:
            super().mouseReleaseEvent(event)
