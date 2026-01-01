from abc import ABC, abstractmethod
from PySide6.QtCore import QPointF

class Command(ABC):
    @abstractmethod
    def execute(self):
        pass

    @abstractmethod
    def undo(self):
        pass

class UndoStack:
    def __init__(self):
        self._history = []

    def push(self, command: Command):
        command.execute()
        self._history.append(command)

    def undo(self):
        if self._history:
            command = self._history.pop()
            command.undo()
            return True
        return False

class AddWallCommand(Command):
    def __init__(self, scene, wall_item):
        self.scene = scene
        self.wall_item = wall_item
        self.parent_item = wall_item.parentItem() # Capture parent

    def execute(self):
        # If item is already in scene/parented correctly (initial creation), do nothing?
        # But undo removes it. So redo needs to add it back.

        # QGraphicsScene.addItem reparents to None (Root).
        # We must respect self.parent_item.

        if self.parent_item:
            self.wall_item.setParentItem(self.parent_item)
        elif self.wall_item.scene() != self.scene:
            self.scene.addItem(self.wall_item)

    def undo(self):
        # removeItem works regardless of parent
        self.scene.removeItem(self.wall_item)

class AddAPCommand(Command):
    def __init__(self, scene, ap_item):
        self.scene = scene
        self.ap_item = ap_item
        self.parent_item = ap_item.parentItem() # Capture parent

    def execute(self):
        if self.parent_item:
            self.ap_item.setParentItem(self.parent_item)
        elif self.ap_item.scene() != self.scene:
            self.scene.addItem(self.ap_item)

    def undo(self):
        self.scene.removeItem(self.ap_item)

class DeleteCommand(Command):
    def __init__(self, scene, items):
        self.scene = scene
        self.items = items # List of items
        # Capture parents for all items to restore them correctly
        self.parents = {item: item.parentItem() for item in items}

    def execute(self):
        for item in self.items:
            self.scene.removeItem(item)

    def undo(self):
        for item in self.items:
            parent = self.parents.get(item)
            if parent:
                item.setParentItem(parent)
            else:
                self.scene.addItem(item)

class MoveCommand(Command):
    def __init__(self, item, old_pos, new_pos):
        self.item = item
        self.old_pos = old_pos
        self.new_pos = new_pos

    def execute(self):
        self.item.setPos(self.new_pos)

    def undo(self):
        self.item.setPos(self.old_pos)
