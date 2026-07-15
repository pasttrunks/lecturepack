import sys
from PySide6.QtWidgets import QApplication
from lecturepack.infrastructure.config_manager import ConfigManager
from lecturepack.ui.main_window import MainWindow

def main():
    app = QApplication(sys.argv)
    
    # Initialize config
    config_manager = ConfigManager()
    
    # Run window
    window = MainWindow(config_manager)
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
