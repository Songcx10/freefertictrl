import time
from PyQt5.QtWidgets import QApplication, QMainWindow, QProgressBar, QPushButton
from PyQt5.QtCore import QThread, pyqtSignal

def run(self):
    total_items = 100
    for i in range(total_items):
        time.sleep(0.1)  # Simulate some work being done
        # self.progress_signal.emit(i + 1)
        self.dockwidget.Probar.setValue(i + 1)

