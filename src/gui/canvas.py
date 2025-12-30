from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem
from PySide6.QtGui import QPixmap, QPainter, QPen, QColor, QWheelEvent
from PySide6.QtCore import Qt, Signal, QPointF

class PlanCanvas(QGraphicsView):
    """
    The main canvas for displaying the floor plan, walls, and heatmap.
    Supports Zooming and Panning.
    """

    # Signals for interactions
    point_clicked = Signal(QPointF)
    mouse_moved = Signal(QPointF)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        # Rendering hints for better quality
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)

        # Navigation flags
        self.setDragMode(QGraphicsView.NoDrag) # We will implement custom drag if needed, or use ScrollHandDrag
        self._is_panning = False
        self._pan_start = QPointF(0, 0)

        self.pixmap_item = None

        # Calibration state
        self.temp_line = None
        self.start_point = None
        self.is_drawing_line = False

    def load_image(self, image_path):
        """Loads a floor plan image onto the scene."""
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            return False

        self.scene.clear()
        self.pixmap_item = QGraphicsPixmapItem(pixmap)
        self.scene.addItem(self.pixmap_item)
        self.setSceneRect(self.pixmap_item.boundingRect())
        self.fitInView(self.pixmap_item, Qt.KeepAspectRatio)
        return True

    def wheelEvent(self, event: QWheelEvent):
        """Handles Zooming with the mouse wheel."""
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
            scene_pos = self.mapToScene(event.position().toPoint())
            self.point_clicked.emit(scene_pos)

            # Handle Drawing logic (if controlled by parent)
            # But here we might want to just emit the click and let parent decide,
            # OR handle temp line drawing here if we set a mode.
            # For now, let's keep it simple: Parent handles logic via signals or we expose a method.

            super().mousePressEvent(event)
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        scene_pos = self.mapToScene(event.position().toPoint())
        self.mouse_moved.emit(scene_pos)

        if self._is_panning:
            delta = event.position() - self._pan_start
            self._pan_start = event.position()

            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._is_panning = False
            self.setCursor(Qt.ArrowCursor)
            event.accept()
        else:
            super().mouseReleaseEvent(event)
