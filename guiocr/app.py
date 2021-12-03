from PyQt5.QtWidgets import QMainWindow,QListWidget,QAbstractItemView,QWidget,QApplication,QButtonGroup,QPushButton,QTextEdit,QRadioButton,QCheckBox,QLabel,QSpacerItem,QMessageBox,QGroupBox,QVBoxLayout,QHBoxLayout
from PyQt5.QtGui import *
from PyQt5.QtCore import QObject,QThread,QSettings,pyqtSignal,pyqtSlot,Qt
from guiocr import __appname__
from guiocr import PY2
from guiocr import QT5
from guiocr import utils
from logger import logger
from shape import Shape
from guiocr.config import get_config
from guiocr.widgets.main_window_ui import Ui_MainWindow
from guiocr.widgets import *
from guiocr.utils import *
import math

class MainWindow(QMainWindow):
    FIT_WINDOW, FIT_WIDTH, MANUAL_ZOOM = 0, 1, 2

    def __init__(self):
        super().__init__()  # 调用父类构造函数，创建QWidget窗体
        self._ui = Ui_MainWindow()  # 创建ui对象
        self._ui.setupUi(self)  # 构造ui
        self.setWindowTitle(__appname__)

        # 单选按钮组
        self.checkBtnGroup = QButtonGroup(self)
        self.checkBtnGroup.addButton(self._ui.checkBox_recog)

        # 控件布局
        """左侧：区域标签列表"""
        self.labelList = LabelListWidget()
        self._ui.scrollAreaLabellist.setWidget(self.labelList)
        self._ui.scrollAreaLabellist.setWidgetResizable(True)
        self.labelList.itemSelectionChanged.connect(self.labelSelectionChanged)
        # self.labelList.itemDoubleClicked.connect(self.editLabel)
        self.labelList.itemChanged.connect(self.labelItemChanged)
        self.labelList.itemDropped.connect(self.labelOrderChanged)
        self.labelList.setSelectionMode(QAbstractItemView.SingleSelection)  # 设置单选

        """缩放控件"""
        self.zoomWidget = ZoomWidget()
        self.setAcceptDrops(True)

        """中心画布"""
        self.canvas = self.labelList.canvas = Canvas(
            epsilon=self._config["epsilon"],
            double_click=self._config["canvas"]["double_click"],
            num_backups=self._config["canvas"]["num_backups"],
        )
        self.canvas.zoomRequest.connect(self.zoomRequest)
        self.canvas.newShape.connect(self.newShape)
        self.canvas.shapeMoved.connect(self.onMoveShape)  # self.setDirty)
        self.canvas.selectionChanged.connect(self.shapeSelectionChanged)
        self.canvas.drawingPolygon.connect(self.toggleDrawingSensitive)

        # Callbacks:
        self.zoomWidget.valueChanged.connect(self.paintCanvas)

        # 滚动缩放区域
        self._ui.scrollAreaCanvas.setWidget(self.canvas)
        self._ui.scrollAreaCanvas.setWidgetResizable(True)
        self.scrollBars = {
            Qt.Vertical: self.scrollArea.verticalScrollBar(),
            Qt.Horizontal: self.scrollArea.horizontalScrollBar(),
        }
        self.canvas.scrollRequest.connect(self.scrollRequest)

        # 加载默认配置
        config = get_config()
        self._config = config

        # 设置默认形状颜色
        Shape.line_color = QColor(*self._config["shape"]["line_color"])
        Shape.fill_color = QColor(*self._config["shape"]["fill_color"])
        Shape.select_line_color = QColor(
            *self._config["shape"]["select_line_color"]
        )
        Shape.select_fill_color = QColor(
            *self._config["shape"]["select_fill_color"]
        )
        Shape.vertex_fill_color = QColor(
            *self._config["shape"]["vertex_fill_color"]
        )
        Shape.hvertex_fill_color = QColor(
            *self._config["shape"]["hvertex_fill_color"]
        )

        # 程序数据
        self.image = QImage()
        self.imagePath = None
        self.recentFiles = []
        self.maxRecent = 7
        self.otherData = None
        self.zoom_level = 100
        self.fit_window = False
        self.zoom_values = {}  # key=filename, value=(zoom_mode, zoom_value)
        self.brightnessContrast_values = {}

        # Restore application settings.
        self.settings = QSettings("casia", __appname__)

        # TODO 快捷键设置


    def scrollRequest(self, delta, orientation):
        units = -delta * 0.1  # natural scroll
        bar = self.scrollBars[orientation]
        value = bar.value() + bar.singleStep() * units
        self.setScroll(orientation, value)

    def setScroll(self, orientation, value):
        self.scrollBars[orientation].setValue(value)
        self.scroll_values[orientation][self.filename] = value

    def setZoom(self, value):
        self.actions.fitWidth.setChecked(False)
        self.actions.fitWindow.setChecked(False)
        self.zoomMode = self.MANUAL_ZOOM
        self.zoomWidget.setValue(value)
        self.zoom_values[self.filename] = (self.zoomMode, value)

    def addZoom(self, increment=1.1):
        zoom_value = self.zoomWidget.value() * increment
        if increment > 1:
            zoom_value = math.ceil(zoom_value)
        else:
            zoom_value = math.floor(zoom_value)
        self.setZoom(zoom_value)

    def zoomRequest(self, delta, pos):
        canvas_width_old = self.canvas.width()
        units = 1.1
        if delta < 0:
            units = 0.9
        self.addZoom(units)

        canvas_width_new = self.canvas.width()
        if canvas_width_old != canvas_width_new:
            canvas_scale_factor = canvas_width_new / canvas_width_old

            x_shift = round(pos.x() * canvas_scale_factor) - pos.x()
            y_shift = round(pos.y() * canvas_scale_factor) - pos.y()

            self.setScroll(
                Qt.Horizontal,
                self.scrollBars[Qt.Horizontal].value() + x_shift,
                )
            self.setScroll(
                Qt.Vertical,
                self.scrollBars[Qt.Vertical].value() + y_shift,
                )


    def setFitWindow(self, value=True):
        if value:
            self.actions.fitWidth.setChecked(False)
        self.zoomMode = self.FIT_WINDOW if value else self.MANUAL_ZOOM
        self.adjustScale()

    def setFitWidth(self, value=True):
        if value:
            self.actions.fitWindow.setChecked(False)
        self.zoomMode = self.FIT_WIDTH if value else self.MANUAL_ZOOM
        self.adjustScale()

    def onNewBrightnessContrast(self, qimage):
        self.canvas.loadPixmap(
            QPixmap.fromImage(qimage), clear_shapes=False
        )

    def brightnessContrast(self, value):
        dialog = BrightnessContrastDialog(
            utils.img_data_to_pil(self.imageData),
            self.onNewBrightnessContrast,
            parent=self,
        )
        brightness, contrast = self.brightnessContrast_values.get(
            self.filename, (None, None)
        )
        if brightness is not None:
            dialog.slider_brightness.setValue(brightness)
        if contrast is not None:
            dialog.slider_contrast.setValue(contrast)
        dialog.exec_()

        brightness = dialog.slider_brightness.value()
        contrast = dialog.slider_contrast.value()
        self.brightnessContrast_values[self.filename] = (brightness, contrast)

    def paintCanvas(self):
        assert not self.image.isNull(), "cannot paint null image"
        self.canvas.scale = 0.01 * self.zoomWidget.value()
        self.canvas.adjustSize()
        self.canvas.update()