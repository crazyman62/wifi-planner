import sys
import os

# Add the src directory to sys.path so that imports work correctly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from src.gui.main_window import main

if __name__ == "__main__":
    main()
