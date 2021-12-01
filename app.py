from PyQt5.QtWidgets import QMainWindow,QMessageBox,QAbstractItemView
from PyQt5.QtCore import QObject,QThread,pyqtSignal,pyqtSlot

class MainWindow(QMainWindow):
    FIT_WINDOW, FIT_WIDTH, MANUAL_ZOOM = 0, 1, 2

