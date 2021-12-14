from PyQt5 import QtGui
from PyQt5 import QtCore
from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QMainWindow,QListWidget,QListWidgetItem,QAbstractItemView,QWidget,QApplication,QButtonGroup,QPushButton,QTextEdit,QRadioButton,QCheckBox,QLabel,QSpacerItem,QMessageBox,QGroupBox,QVBoxLayout,QHBoxLayout
from PyQt5.QtCore import QObject,QThread,QSettings,pyqtSignal,pyqtSlot,Qt
from .logger import logger
from .shape import Shape
import PIL.Image
import math
import os
import io
import json
import functools
import imgviz
from guiocr import __appname__
from guiocr import PY2
from guiocr import QT5
from guiocr import utils
from guiocr.config import get_config
from guiocr.widgets.main_window_ui import Ui_MainWindow
from guiocr.widgets import *
from guiocr.utils import *


LABEL_COLORMAP = imgviz.label_colormap(value=200)
here = os.path.dirname(os.path.abspath(__file__))


class MainWindow(QMainWindow):
    FIT_WINDOW, FIT_WIDTH, MANUAL_ZOOM = 0, 1, 2

    def __init__(self):
        super().__init__()  # 调用父类构造函数，创建QWidget窗体
        self._ui = Ui_MainWindow()  # 创建ui对象
        self._ui.setupUi(self)  # 构造ui
        self.setWindowTitle(__appname__)

        # 加载默认配置
        config = get_config()
        self._config = config

        # 程序数据
        self.image = QtGui.QImage()
        self.dataDict = {}#用于保持标注数据
        self.imagePath = None
        self.recentFiles = []
        self.maxRecent = 7
        self.otherData = None
        self.zoom_level = 100
        self.fit_window = False
        self.zoom_values = {}  # key=filename, value=(zoom_mode, zoom_value)
        self.brightnessContrast_values = {}
        self.filename = ""
        self.output_dir = "./output"
        self.lastOpenDir = here
        self.imageList = []
        self.result = []
        self.suffix = ".json"
        self.scroll_values = {
            Qt.Horizontal: {},
            Qt.Vertical: {},
        }  # key=filename, value=scroll_value

        # 线程
        self.workThread = QThread()
        self.processor = OCR_qt()
        self.processor.moveToThread(self.workThread)
        self.processor.sendResult.connect(self.onReceiveResults)
        self.workThread.started.connect(self.processor.start)

        # 单选按钮组
        self.checkBtnGroup = QButtonGroup(self)
        self.checkBtnGroup.addButton(self._ui.checkBox_ocr)
        self.checkBtnGroup.addButton(self._ui.checkBox_det)
        self.checkBtnGroup.addButton(self._ui.checkBox_recog)
        self.checkBtnGroup.addButton(self._ui.checkBox_layoutparser)
        self.checkBtnGroup.setExclusive(True)

        # 添加按钮icon
        self._ui.btnOpenImg.setIcon(self.getIcon("open_img_grey"))
        self._ui.btnOpenDir.setIcon(self.getIcon("folder_open_grey"))
        self._ui.btnNext.setIcon(self.getIcon("next_grey"))
        self._ui.btnPrev.setIcon(self.getIcon("before_grey"))
        self._ui.btnAddShape.setIcon(self.getIcon("add_grey"))
        self._ui.btnEditShape.setIcon(self.getIcon("edit_grey"))
        self._ui.btnSaveAll.setIcon(self.getIcon("done_grey"))
        self._ui.btnBrightness.setIcon(self.getIcon("brightness_grey"))
        # self._ui.btnStartProcess.setIcon(self.getIcon("play_white"))

        # 按钮响应函数
        self._ui.btnOpenImg.clicked.connect(self.openFile)
        self._ui.btnOpenDir.clicked.connect(self.openDirDialog)
        self._ui.btnNext.clicked.connect(self.openNextImg)
        self._ui.btnPrev.clicked.connect(self.openPrevImg)
        self._ui.btnStartProcess.clicked.connect(self.startProcess)
        self._ui.btnCopyAll.clicked.connect(self.copyToClipboard)
        self._ui.btnSaveAll.clicked.connect(self.saveToFile)
        # self._ui.btnAddShape.clicked.connect(self.newShape)
        # self._ui.btnEditShape.clicked.connect(self.setEditMode)
        self._ui.listWidgetResults.itemClicked.connect(self.onItemResultClicked)
        # self._ui.listWidgetResults.itemSelectionChanged.connect(self.onItemResultClicked)
        self._ui.listWidgetResults.clear()
        # self.addResultItem(shape=None,txt="test3")


        # 控件布局
        """左侧：区域标签列表"""
        self.labelList = LabelListWidget()
        self._ui.scrollAreaLabellist.setWidget(self.labelList)
        self._ui.scrollAreaLabellist.setWidgetResizable(True)
        self.labelList.itemSelectionChanged.connect(self.labelSelectionChanged)
        # self.labelList.itemDoubleClicked.connect(self.editLabel)
        self.labelList.itemChanged.connect(self.labelItemChanged)
        self.labelList.itemDropped.connect(self.labelOrderChanged)
        self.labelList.setSelectionMode(QAbstractItemView.MultiSelection)  # 设置单选or多选

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
            Qt.Vertical: self._ui.scrollAreaCanvas.verticalScrollBar(),
            Qt.Horizontal: self._ui.scrollAreaCanvas.horizontalScrollBar(),
        }
        self.canvas.scrollRequest.connect(self.scrollRequest)
        # self.setCentralWidget(self._ui.scrollAreaCanvas)


        # 设置默认形状颜色
        Shape.line_color = QtGui.QColor(*self._config["shape"]["line_color"])
        Shape.fill_color = QtGui.QColor(*self._config["shape"]["fill_color"])
        Shape.select_line_color = QtGui.QColor(
            *self._config["shape"]["select_line_color"]
        )
        Shape.select_fill_color = QtGui.QColor(
            *self._config["shape"]["select_fill_color"]
        )
        Shape.vertex_fill_color = QtGui.QColor(
            *self._config["shape"]["vertex_fill_color"]
        )
        Shape.hvertex_fill_color = QtGui.QColor(
            *self._config["shape"]["hvertex_fill_color"]
        )

        # Restore application settings.
        self.settings = QSettings("app", __appname__)

        # actions
        self._initActions()

        # status bar
        self.statusBar().showMessage(str(self.tr("%s started.")) % __appname__)
        self.statusBar().show()


        # TODO 快捷键设置

    def _initActions(self):
        # Actions
        action = functools.partial(utils.newAction, self)
        shortcuts = self._config["shortcuts"]
        quit = action(
            self.tr("&Quit"),
            self.close,
            shortcuts["quit"],
            "quit",
            self.tr("Quit application"),
        )
        open_ = action(
            self.tr("&Open"),
            self.openFile,
            shortcuts["open"],
            "open",
            self.tr("Open image or label file"),
        )
        opendir = action(
            self.tr("&Open Dir"),
            self.openDirDialog,
            shortcuts["open_dir"],
            "open",
            self.tr(u"Open Dir"),
        )
        openNextImg = action(
            self.tr("&Next Image"),
            self.openNextImg,
            shortcuts["open_next"],
            "next",
            self.tr(u"Open next (hold Ctl+Shift to copy labels)"),
            enabled=False,
        )
        openPrevImg = action(
            self.tr("&Prev Image"),
            self.openPrevImg,
            shortcuts["open_prev"],
            "prev",
            self.tr(u"Open prev (hold Ctl+Shift to copy labels)"),
            enabled=False,
        )
        save = action(
            self.tr("&Save"),
            self.saveFile,
            shortcuts["save"],
            "save",
            self.tr("Save labels to file"),
            enabled=False,
        )
        saveAs = action(
            self.tr("&Save As"),
            self.saveFileAs,
            shortcuts["save_as"],
            "save-as",
            self.tr("Save labels to a different file"),
            enabled=False,
        )

        deleteFile = action(
            self.tr("&Delete File"),
            self.deleteFile,
            shortcuts["delete_file"],
            "delete",
            self.tr("Delete current label file"),
            enabled=False,
        )

        changeOutputDir = action(
            self.tr("&Change Output Dir"),
            slot=self.changeOutputDirDialog,
            shortcut=shortcuts["save_to"],
            icon="open",
            tip=self.tr(u"Change where annotations are loaded/saved"),
        )

        saveWithImageData = action(
            text="Save With Image Data",
            slot=self.enableSaveImageWithData,
            tip="Save image data in label file",
            checkable=True,
            checked=self._config["store_data"],
        )

        close = action(
            "&Close",
            self.closeFile,
            shortcuts["close"],
            "close",
            "Close current file",
        )

        createMode = action(
            self.tr("Create Polygons"),
            lambda: self.toggleDrawMode(False, createMode="polygon"),
            shortcuts["create_polygon"],
            "objects",
            self.tr("Start drawing polygons"),
            enabled=False,
        )
        createRectangleMode = action(
            self.tr("Create Rectangle"),
            lambda: self.toggleDrawMode(False, createMode="rectangle"),
            shortcuts["create_rectangle"],
            "objects",
            self.tr("Start drawing rectangles"),
            enabled=False,
        )
        createCircleMode = action(
            self.tr("Create Circle"),
            lambda: self.toggleDrawMode(False, createMode="circle"),
            shortcuts["create_circle"],
            "objects",
            self.tr("Start drawing circles"),
            enabled=False,
        )
        createLineMode = action(
            self.tr("Create Line"),
            lambda: self.toggleDrawMode(False, createMode="line"),
            shortcuts["create_line"],
            "objects",
            self.tr("Start drawing lines"),
            enabled=False,
        )
        createPointMode = action(
            self.tr("Create Point"),
            lambda: self.toggleDrawMode(False, createMode="point"),
            shortcuts["create_point"],
            "objects",
            self.tr("Start drawing points"),
            enabled=False,
        )
        createLineStripMode = action(
            self.tr("Create LineStrip"),
            lambda: self.toggleDrawMode(False, createMode="linestrip"),
            shortcuts["create_linestrip"],
            "objects",
            self.tr("Start drawing linestrip. Ctrl+LeftClick ends creation."),
            enabled=False,
        )
        editMode = action(
            self.tr("Edit Polygons"),
            self.setEditMode,
            shortcuts["edit_polygon"],
            "edit",
            self.tr("Move and edit the selected polygons"),
            enabled=False,
        )

        delete = action(
            self.tr("Delete Polygons"),
            self.deleteSelectedShape,
            shortcuts["delete_polygon"],
            "cancel",
            self.tr("Delete the selected polygons"),
            enabled=False,
        )

        hideAll = action(
            self.tr("&Hide\nPolygons"),
            functools.partial(self.togglePolygons, False),
            icon="eye",
            tip=self.tr("Hide all polygons"),
            enabled=False,
        )
        showAll = action(
            self.tr("&Show\nPolygons"),
            functools.partial(self.togglePolygons, True),
            icon="eye",
            tip=self.tr("Show all polygons"),
            enabled=False,
        )

        help = action(
            self.tr("&Tutorial"),
            self.tutorial,
            icon="help",
            tip=self.tr("Show tutorial page"),
        )

        zoom = QtWidgets.QWidgetAction(self)
        zoom.setDefaultWidget(self.zoomWidget)
        self.zoomWidget.setWhatsThis(
            str(
                self.tr(
                    "Zoom in or out of the image. Also accessible with "
                    "{} and {} from the canvas."
                )
            ).format(
                utils.fmtShortcut(
                    "{},{}".format(shortcuts["zoom_in"], shortcuts["zoom_out"])
                ),
                utils.fmtShortcut(self.tr("Ctrl+Wheel")),
            )
        )
        self.zoomWidget.setEnabled(False)

        zoomIn = action(
            self.tr("Zoom &In"),
            functools.partial(self.addZoom, 1.1),
            shortcuts["zoom_in"],
            "zoom-in",
            self.tr("Increase zoom level"),
            enabled=False,
        )
        zoomOut = action(
            self.tr("&Zoom Out"),
            functools.partial(self.addZoom, 0.9),
            shortcuts["zoom_out"],
            "zoom-out",
            self.tr("Decrease zoom level"),
            enabled=False,
        )
        zoomOrg = action(
            self.tr("&Original size"),
            functools.partial(self.setZoom, 100),
            shortcuts["zoom_to_original"],
            "zoom",
            self.tr("Zoom to original size"),
            enabled=False,
        )
        fitWindow = action(
            self.tr("&Fit Window"),
            self.setFitWindow,
            shortcuts["fit_window"],
            "fit-window",
            self.tr("Zoom follows window size"),
            checkable=True,
            enabled=False,
        )
        fitWidth = action(
            self.tr("Fit &Width"),
            self.setFitWidth,
            shortcuts["fit_width"],
            "fit-width",
            self.tr("Zoom follows window width"),
            checkable=True,
            enabled=False,
        )
        brightnessContrast = action(
            "&Brightness Contrast",
            self.brightnessContrast,
            None,
            "color",
            "Adjust brightness and contrast",
            enabled=False,
        )
        # Group zoom controls into a list for easier toggling.
        zoomActions = (
            self.zoomWidget,
            zoomIn,
            zoomOut,
            zoomOrg,
            fitWindow,
            fitWidth,
        )
        self.zoomMode = self.FIT_WINDOW
        fitWindow.setChecked(Qt.Checked)
        self.scalers = {
            self.FIT_WINDOW: self.scaleFitWindow,
            self.FIT_WIDTH: self.scaleFitWidth,
            # Set to one to scale to 100% when loading files.
            self.MANUAL_ZOOM: lambda: 1,
        }

        fill_drawing = action(
            self.tr("Fill Drawing Polygon"),
            self.canvas.setFillDrawing,
            None,
            "color",
            self.tr("Fill polygon while drawing"),
            checkable=True,
            enabled=True,
        )
        fill_drawing.trigger()
        # Lavel list context menu.
        # labelMenu = QtWidgets.QMenu()
        # utils.addActions(labelMenu, (edit, delete))
        # self.labelList.setContextMenuPolicy(Qt.CustomContextMenu)
        # self.labelList.customContextMenuRequested.connect(
        #     self.popLabelListMenu
        # )

        # Store actions for further handling.
        self.actions = utils.struct(
            # saveAuto=saveAuto,
            saveWithImageData=saveWithImageData,
            changeOutputDir=changeOutputDir,
            save=save,
            saveAs=saveAs,
            open=open_,
            close=close,
            deleteFile=deleteFile,
            # toggleKeepPrevMode=toggle_keep_prev_mode,
            delete=delete,
            # edit=edit,
            # duplicate=duplicate,
            # copy=copy,
            # paste=paste,
            # undoLastPoint=undoLastPoint,
            # undo=undo,
            # removePoint=removePoint,
            createMode=createMode,
            editMode=editMode,
            createRectangleMode=createRectangleMode,
            createCircleMode=createCircleMode,
            createLineMode=createLineMode,
            createPointMode=createPointMode,
            createLineStripMode=createLineStripMode,
            zoom=zoom,
            zoomIn=zoomIn,
            zoomOut=zoomOut,
            zoomOrg=zoomOrg,
            # keepPrevScale=keepPrevScale,
            fitWindow=fitWindow,
            fitWidth=fitWidth,
            brightnessContrast=brightnessContrast,
            zoomActions=zoomActions,
            openNextImg=openNextImg,
            openPrevImg=openPrevImg,
            fileMenuActions=(open_, opendir, save, saveAs, close, quit),
            tool=(),
            # XXX: need to add some actions here to activate the shortcut
            editMenu=(
                # edit,
                # duplicate,
                delete,
                None,
                # undo,
                # undoLastPoint,
                None,
                # removePoint,
                None,
                # toggle_keep_prev_mode,
            ),
            # menu shown at right click
            menu=(
                createMode,
                createRectangleMode,
                createCircleMode,
                createLineMode,
                createPointMode,
                createLineStripMode,
                editMode,
                # edit,
                # duplicate,
                # copy,
                # paste,
                delete,
                # undo,
                # undoLastPoint,
                # removePoint,
            ),
            onLoadActive=(
                close,
                createMode,
                createRectangleMode,
                createCircleMode,
                createLineMode,
                createPointMode,
                createLineStripMode,
                editMode,
                brightnessContrast,
            ),
            onShapesPresent=(saveAs, hideAll, showAll),
        )

        # self.canvas.vertexSelected.connect(self.actions.removePoint.setEnabled)


    def getIcon(self,iconName:str):
        self.icons_dir = os.path.join(here, "./icons")
        path = os.path.join(":/", self.icons_dir, f"{iconName}.png")
        return QtGui.QIcon(path)

    def errorMessage(self, title, message):
        return QtWidgets.QMessageBox.critical(
            self, title, "<p><b>%s</b></p>%s" % (title, message)
        )

    def currentPath(self):
        return os.path.dirname(str(self.filename)) if self.filename else "."

    def currentItem(self):
        items = self.labelList.selectedItems()
        if items:
            return items[0]
        return None

    def addRecentFile(self, filename):
        if filename in self.recentFiles:
            self.recentFiles.remove(filename)
        elif len(self.recentFiles) >= self.maxRecent:
            self.recentFiles.pop()
        self.recentFiles.insert(0, filename)

    def addResultItem(self,shape=None,txt=""):
        """
        为labellist、listWidgetResults添加一条记录
        Args:
            shape:
            txt:

        Returns:

        """

        newItem = QListWidgetItem(txt,self._ui.listWidgetResults)
        newItem.setCheckState(Qt.Checked)
        newItem.setFlags(Qt.ItemIsEditable | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        self._ui.listWidgetResults.addItem(newItem)

    def onItemResultClicked(self):
        """
        listWidgetResults选中一条记录时，激活对应的区域

        Returns:

        """
        for id in self._ui.listWidgetResults.selectedIndexes():
            # 选取labelList中对应idx的item
            idx = int(id.row())
            item = self.labelList[idx]
            self.labelList.selectItem(item)
            self.labelList.scrollToItem(item)
            # self.labelSelectionChanged()
            # for shape in self.canvas.shapes:
            #     if item.shape.label == shape.label:
            #         self.canvas.selectShapes([shape])

    # React to labelList select signals.
    def labelSelectionChanged(self):
        if self._noSelectionSlot:
            return
        if self.canvas.editing():
            selected_shapes = []
            for item in self.labelList.selectedItems():
                selected_shapes.append(item.shape())
                # 选中listWidgetResults对应的item
                index = self.labelList.model().indexFromItem(item)
                self._ui.listWidgetResults.selectionModel().select(index,QtCore.QItemSelectionModel.Select)
                self._ui.listWidgetResults.scrollTo(index)
            if selected_shapes:
                self.canvas.selectShapes(selected_shapes)
            else:
                self.canvas.deSelectShape()

    # React to canvas shape select signals.
    def shapeSelectionChanged(self, selected_shapes):
        self._noSelectionSlot = True
        for shape in self.canvas.selectedShapes:
            shape.selected = False
        self.labelList.clearSelection()
        self.canvas.selectedShapes = selected_shapes
        for shape in self.canvas.selectedShapes:
            shape.selected = True
            item = self.labelList.findItemByShape(shape)
            self.labelList.selectItem(item)
            self.labelList.scrollToItem(item)

        # 选中listWidgetResults对应的文本列表项
        for id in self.labelList.selectedIndexes():
            idx = int(id.row())
            item = self._ui.listWidgetResults.item(idx)
            # item.setSelected(True)
            self._ui.listWidgetResults.selectionModel().select(id,QtCore.QItemSelectionModel.Select)
            self._ui.listWidgetResults.scrollToItem(item)

        self._noSelectionSlot = False
        n_selected = len(selected_shapes)
        self.actions.delete.setEnabled(n_selected)
        # self.actions.duplicate.setEnabled(n_selected)
        # self.actions.copy.setEnabled(n_selected)
        # self.actions.edit.setEnabled(n_selected == 1)

    def openPrevImg(self, _value=False):
        keep_prev = self._config["keep_prev"]
        if QtWidgets.QApplication.keyboardModifiers() == (
            Qt.ControlModifier | Qt.ShiftModifier
        ):
            self._config["keep_prev"] = True

        # if not self.mayContinue():
        #     return

        if len(self.imageList) <= 0:
            return

        if self.filename is None:
            return

        currIndex = self.imageList.index(self.filename)
        if currIndex - 1 >= 0:
            filename = self.imageList[currIndex - 1]
            if filename:
                self.loadFile(filename)

        self._config["keep_prev"] = keep_prev

    def openNextImg(self, _value=False, load=True):
        keep_prev = self._config["keep_prev"]
        if QtWidgets.QApplication.keyboardModifiers() == (
            Qt.ControlModifier | Qt.ShiftModifier
        ):
            self._config["keep_prev"] = True

        # if not self.mayContinue():
        #     return

        if len(self.imageList) <= 0:
            return

        filename = None
        if self.filename is None:
            filename = self.imageList[0]
        else:
            currIndex = self.imageList.index(self.filename)
            if currIndex + 1 < len(self.imageList):
                filename = self.imageList[currIndex + 1]
            else:
                filename = self.imageList[-1]
        self.filename = filename

        if self.filename and load:
            self.loadFile(self.filename)

        self._config["keep_prev"] = keep_prev

    def openFile(self, _value=False):
        path = os.path.dirname(str(self.filename)) if self.filename else "."
        formats = [
            "*.{}".format(fmt.data().decode())
            for fmt in QtGui.QImageReader.supportedImageFormats()
        ]
        filters = self.tr("图像文件 (%s)") % " ".join(
            formats #+ ["*%s" % LabelFile.suffix]
        )
        fileDialog = FileDialogPreview(self)
        fileDialog.setFileMode(FileDialogPreview.ExistingFile)
        fileDialog.setNameFilter(filters)
        fileDialog.setWindowTitle(
            self.tr("%s - 选择图像文件") % __appname__,
        )
        fileDialog.setWindowFilePath(path)
        fileDialog.setViewMode(FileDialogPreview.Detail)
        if fileDialog.exec_():
            fileName = fileDialog.selectedFiles()[0]
            if fileName:
                self.loadFile(fileName)

    def loadFile(self, filename=None):
        self.resetState()
        self.canvas.setEnabled(False)
        if filename is None:
            filename = self.settings.value("filename", "")
        filename = str(filename)
        if not QtCore.QFile.exists(filename):
            self.errorMessage(
                self.tr("Error opening file"),
                self.tr("No such file: <b>%s</b>") % filename,
            )
            return False
        # assumes same name, but json extension
        self.status(
            str(self.tr("Loading %s...")) % os.path.basename(str(filename))
        )
        self.imageData = self.load_image_file(filename)
        image = QtGui.QImage.fromData(self.imageData)
        self._ui.btnStartProcess.setText("开始")
        self._ui.listWidgetResults.clear()
        self.labelList.clear()

        if image.isNull():
            formats = [
                "*.{}".format(fmt.data().decode())
                for fmt in QtGui.QImageReader.supportedImageFormats()
            ]
            self.errorMessage(
                self.tr("Error opening file"),
                self.tr(
                    "<p>Make sure <i>{0}</i> is a valid image file.<br/>"
                    "Supported image formats: {1}</p>"
                ).format(filename, ",".join(formats)),
            )
            self.status(self.tr("Error reading %s") % filename)
            return False
        self.image = image
        self.filename = filename
        if self._config["keep_prev"]:
            prev_shapes = self.canvas.shapes
        self.canvas.loadPixmap(QtGui.QPixmap.fromImage(image))
        flags = {k: False for k in self._config["flags"] or []}

        self.canvas.setEnabled(True)
        # set zoom values
        is_initial_load = not self.zoom_values
        if self.filename in self.zoom_values:
            self.zoomMode = self.zoom_values[self.filename][0]
            self.setZoom(self.zoom_values[self.filename][1])
        elif is_initial_load or not self._config["keep_prev_scale"]:
            self.adjustScale(initial=True)
        # set scroll values
        for orientation in self.scroll_values:
            if self.filename in self.scroll_values[orientation]:
                self.setScroll(
                    orientation, self.scroll_values[orientation][self.filename]
                )
        # set brightness contrast values
        dialog = BrightnessContrastDialog(
            utils.img_data_to_pil(self.imageData),
            self.onNewBrightnessContrast,
            parent=self,
        )
        brightness, contrast = self.brightnessContrast_values.get(
            self.filename, (None, None)
        )
        if self._config["keep_prev_brightness"] and self.recentFiles:
            brightness, _ = self.brightnessContrast_values.get(
                self.recentFiles[0], (None, None)
            )
        if self._config["keep_prev_contrast"] and self.recentFiles:
            _, contrast = self.brightnessContrast_values.get(
                self.recentFiles[0], (None, None)
            )
        if brightness is not None:
            dialog.slider_brightness.setValue(brightness)
        if contrast is not None:
            dialog.slider_contrast.setValue(contrast)
        self.brightnessContrast_values[self.filename] = (brightness, contrast)
        if brightness is not None or contrast is not None:
            dialog.onNewValue(None)
        self.paintCanvas()
        self.addRecentFile(self.filename)
        self.toggleActions(True)
        self.canvas.setFocus()
        self.status(str(self.tr("Loaded %s")) % os.path.basename(str(filename)))
        return True

    def startProcess(self):
        if not self.checkBtnGroup.checkedButton():
            self.errorMessage("提示","请先选择任务配置")
            return

        # TODO:多线程处理+进度条
        selectBtnName = self.checkBtnGroup.checkedButton().objectName()
        if selectBtnName == "checkBox_ocr":
            # 文本检测+识别
            self.processor.set_task(self.filename,cls=True,lan=self._ui.comboBoxLanguage.currentText())
            self._ui.btnStartProcess.setText("解析中...")
            # self.result = ocr(self.filename, cls=True, lan=self._ui.comboBoxLanguage.currentText())
            # self.add_ocr_results(self.result)
        elif selectBtnName == "checkBox_det":
            # TODO:文本检测
            self.processor.set_task(self.filename, cls=False, lan=self._ui.comboBoxLanguage.currentText())
            # self.result = ocr(self.filename, cls=False, lan=self._ui.comboBoxLanguage.currentText())
            # self.add_ocr_results(self.result)
        elif selectBtnName == "checkBox_recog":
            # TODO:文本识别
            self.errorMessage("提示","当前版本暂不支持")
            # self.result = ocr(self.filename, cls=True, lan=self._ui.comboBoxLanguage.currentText())
            # self.add_ocr_results(self.result)
        elif selectBtnName == "checkBox_layoutparser":
            self.errorMessage("提示","当前版本暂不支持")
            # self.result = structure_analysis(self.filename,self.output_dir)
            # self.add_structure_results(self.result)

        self.workThread.start()

        # 显示结果页
        self._ui.tabWidgetResult.setCurrentIndex(1)

    def onReceiveResults(self,result):
        self.workThread.quit()

        # 检测+识别结果
        self.add_ocr_results(result)

        self._ui.btnStartProcess.setText("解析完成")
        # TODO：其他分析结果

    def add_ocr_results(self,result):
        boxes = [line[0] for line in result]
        txts = [line[1][0] for line in result]
        shapes = []
        for i in range(len(boxes)):
            x1 = boxes[i][0][0]#min(boxes[i][0][0],boxes[i][1][0])
            y1 = boxes[i][0][1]#min(boxes[i][0][1],boxes[i][1][1])
            x2 = boxes[i][2][0]#max(boxes[i][0][0], boxes[i][1][0])
            y2 = boxes[i][2][1]#max(boxes[i][0][1], boxes[i][1][1])
            label = f"({x1},{y1}),({x2},{y2})"
            shape = Shape(
                label=label,
                shape_type="rectangle",
                group_id=i,
            )
            shape.addPoint(QtCore.QPointF(x1, y1))
            shape.addPoint(QtCore.QPointF(x2, y2))
            shapes.append(shape)
            # shape.close()
            txt = txts[i]
            self.addLabel(shape)
            self.addResultItem(shape,txt)
        self.loadShapes(shapes)

    def add_structure_results(self,result):
        # TODO: 版面分析
        for line in result:
            line.pop('img')
            print(line)

    def copyToClipboard(self):
        contents = []
        for id in self._ui.listWidgetResults.selectionModel().selectedRows():#selectedIndexes():#for item in self._ui.listWidgetResults.selectedItems():
            # 选取labelList中对应idx的item
            idx = int(id.row())
            content = self._ui.listWidgetResults.item(idx).text()# item = self.labelList[idx]
            contents.append(content)
        txt = "\n".join(contents)
        self._ui.statusbar.setStatusTip(f"Copy {len(contents)} results to clipboard!")
        clipboard = QApplication.clipboard()
        clipboard.setText(txt)

    def saveToFile(self):
        # TODO:保存至json、txt等
        pass


    def load_image_file(self,filename):
        try:
            image_pil = PIL.Image.open(filename)
        except IOError:
            logger.error("Failed opening image file: {}".format(filename))
            return

        # apply orientation to image according to exif
        # image_pil = utils.apply_exif_orientation(image_pil)

        with io.BytesIO() as f:
            ext = os.path.splitext(filename)[1].lower()
            if ext in [".jpg", ".jpeg"]:
                format = "JPEG"
            else:
                format = "PNG"
            image_pil.save(f, format=format)
            f.seek(0)
            return f.read()

    def saveFile(self, _value=False):
        assert not self.image.isNull(), "cannot save empty image"
        if self.labelFile:
            # DL20180323 - overwrite when in directory
            self._saveFile(self.labelFile.filename)
        elif self.output_file:
            self._saveFile(self.output_file)
            self.close()
        else:
            self._saveFile(self.saveFileDialog())

    def saveFileAs(self, _value=False):
        assert not self.image.isNull(), "cannot save empty image"
        self._saveFile(self.saveFileDialog())

    def saveFileDialog(self):
        caption = self.tr("%s - Choose File") % __appname__
        filters = self.tr("Label files (*%s)") % self.suffix
        if self.output_dir:
            dlg = QtWidgets.QFileDialog(
                self, caption, self.output_dir, filters
            )
        else:
            dlg = QtWidgets.QFileDialog(
                self, caption, self.currentPath(), filters
            )
        dlg.setDefaultSuffix(self.suffix[1:])
        dlg.setAcceptMode(QtWidgets.QFileDialog.AcceptSave)
        dlg.setOption(QtWidgets.QFileDialog.DontConfirmOverwrite, False)
        dlg.setOption(QtWidgets.QFileDialog.DontUseNativeDialog, False)
        basename = os.path.basename(os.path.splitext(self.filename)[0])
        if self.output_dir:
            default_labelfile_name = os.path.join(
                self.output_dir, basename + self.suffix
            )
        else:
            default_labelfile_name = os.path.join(
                self.currentPath(), basename + self.suffix
            )
        filename = dlg.getSaveFileName(
            self,
            self.tr("Choose File"),
            default_labelfile_name,
            self.tr("Label files (*%s)") % self.suffix,
        )
        if isinstance(filename, tuple):
            filename, _ = filename
        return filename

    def _saveFile(self, filename):
        if filename and self.saveLabels(filename):
            self.addRecentFile(filename)
            self.setClean()

    def enableSaveImageWithData(self, enabled):
        self._config["store_data"] = enabled
        self.actions.saveWithImageData.setChecked(enabled)

    def changeOutputDirDialog(self, _value=False):
        default_output_dir = self.output_dir
        if default_output_dir is None and self.filename:
            default_output_dir = os.path.dirname(self.filename)
        if default_output_dir is None:
            default_output_dir = self.currentPath()

        output_dir = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            self.tr("%s - Save/Load Annotations in Directory") % __appname__,
            default_output_dir,
            QtWidgets.QFileDialog.ShowDirsOnly
            | QtWidgets.QFileDialog.DontResolveSymlinks,
        )
        output_dir = str(output_dir)

        if not output_dir:
            return

        self.output_dir = output_dir

        self.statusBar().showMessage(
            self.tr("%s . Annotations will be saved/loaded in %s")
            % ("Change Annotations Dir", self.output_dir)
        )
        self.statusBar().show()

        current_filename = self.filename
        self.importDirImages(self.lastOpenDir, load=False)


    def deleteFile(self):
        #TODO delete result file
        mb = QtWidgets.QMessageBox
        msg = self.tr(
            "You are about to permanently delete this label file, "
            "proceed anyway?"
        )
        answer = mb.warning(self, self.tr("Attention"), msg, mb.Yes | mb.No)
        if answer != mb.Yes:
            return

        # label_file = self.getLabelFile()
        # if osp.exists(label_file):
        #     os.remove(label_file)
        #     logger.info("Label file is removed: {}".format(label_file))
        #
        #     item = self.fileListWidget.currentItem()
        #     item.setCheckState(Qt.Unchecked)
        #
        #     self.resetState()

    def closeFile(self, _value=False):
        if not self.mayContinue():
            return
        self.resetState()
        self.setClean()
        self.toggleActions(False)
        self.canvas.setEnabled(False)
        self.actions.saveAs.setEnabled(False)

    def saveLabels(self, filename):
        try:
            with open(filename, "w") as f:
                json.dump(self.dataDict, f, ensure_ascii=False, indent=2)
            self.filename = filename
        except Exception as e:
            raise e


    def queueEvent(self, function):
        QtCore.QTimer.singleShot(0, function)

    def status(self, message, delay=5000):
        self.statusBar().showMessage(message, delay)

    def resetState(self):
        self.labelList.clear()
        self.filename = None
        self.imagePath = None
        self.imageData = None
        self.labelFile = None
        self.otherData = None
        self.canvas.resetState()

    def _update_shape_color(self, shape):
        r, g, b = self._get_rgb_by_label(shape.label,shape.group_id)
        shape.line_color = QtGui.QColor(r, g, b)
        shape.vertex_fill_color = QtGui.QColor(r, g, b)
        shape.hvertex_fill_color = QtGui.QColor(255, 255, 255)
        shape.fill_color = QtGui.QColor(r, g, b, 128)
        shape.select_line_color = QtGui.QColor(255, 255, 255)
        shape.select_fill_color = QtGui.QColor(r, g, b, 155)

    def _get_rgb_by_label(self, label,group_id):
        if self._config["shape_color"] == "auto":
            label_id = group_id
            # item = self.uniqLabelList.findItemsByLabel(label)[0]
            # label_id = self.uniqLabelList.indexFromItem(item).row() + 1
            label_id += self._config["shift_auto_shape_color"]
            return LABEL_COLORMAP[label_id % len(LABEL_COLORMAP)]
        elif (
            self._config["shape_color"] == "manual"
            and self._config["label_colors"]
            and label in self._config["label_colors"]
        ):
            return self._config["label_colors"][label]
        elif self._config["default_shape_color"]:
            return self._config["default_shape_color"]
        return (0, 255, 0)

    def remLabels(self, shapes):
        for shape in shapes:
            item = self.labelList.findItemByShape(shape)
            self.labelList.removeItem(item)



    def addLabel(self, shape):
        if shape.group_id is None:
            text = shape.label
        else:
            text = "{} ({})".format(shape.label, shape.group_id)
        label_list_item = LabelListWidgetItem(text, shape)
        self.labelList.addItem(label_list_item)
        for action in self.actions.onShapesPresent:
            action.setEnabled(True)

        self._update_shape_color(shape)
        label_list_item.setText(
            '{} <font color="#{:02x}{:02x}{:02x}">●</font>'.format(
                text, *shape.fill_color.getRgb()[:3]
            )
        )

    def loadShapes(self, shapes, replace=True):
        self._noSelectionSlot = True
        # for shape in shapes:
        #     self.addLabel(shape)
        self.labelList.clearSelection()
        self._noSelectionSlot = False
        self.canvas.loadShapes(shapes, replace=replace)

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

    def adjustScale(self, initial=False):
        value = self.scalers[self.FIT_WINDOW if initial else self.zoomMode]()
        value = int(100 * value)
        self.zoomWidget.setValue(value)
        self.zoom_values[self.filename] = (self.zoomMode, value)

    def scaleFitWindow(self):
        """Figure out the size of the pixmap to fit the main widget."""
        e = 2.0  # So that no scrollbars are generated.
        w1 = self.centralWidget().width() - e
        h1 = self.centralWidget().height() - e
        a1 = w1 / h1
        # Calculate a new scale value based on the pixmap's aspect ratio.
        w2 = self.canvas.pixmap.width() - 0.0
        h2 = self.canvas.pixmap.height() - 0.0
        a2 = w2 / h2
        return w1 / w2 if a2 >= a1 else h1 / h2

    def scaleFitWidth(self):
        # The epsilon does not seem to work too well here.
        w = self.centralWidget().width() - 2.0
        return w / self.canvas.pixmap.width()

    def onNewBrightnessContrast(self, qimage):
        self.canvas.loadPixmap(
            QtGui.QPixmap.fromImage(qimage), clear_shapes=False
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



    def labelItemChanged(self, item):
        shape = item.shape()
        self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)

    def labelOrderChanged(self):
        self.setDirty()
        self.canvas.loadShapes([item.shape() for item in self.labelList])

    def newShape(self):
        flags = {}
        group_id = None
        flags = {}
        group_id = -1
        self.labelList.clearSelection()

        # 在沙盘对象中添加区域对象
        shape = self.canvas.getLastShape()
        x1 = int(shape.points[0].x())
        y1 = int(shape.points[0].y())
        x2 = int(shape.points[1].x())
        y2 = int(shape.points[1].y())
        text = f"({x1},{y1}),({x2},{y2})"
        shape = self.canvas.setLastLabel(text, flags)

        # 添加到listwidget
        self.addLabel(shape)

        self.actions.editMode.setEnabled(True)
        self.actions.undoLastPoint.setEnabled(False)
        self.actions.undo.setEnabled(True)
        if text:
            self.labelList.clearSelection()
            shape = self.canvas.setLastLabel(text, flags)
            shape.group_id = group_id

            # self.actions.undoLastPoint.setEnabled(False)
            # self.actions.undo.setEnabled(True)
            self.setDirty()
        else:
            # self.canvas.undoLastLine()
            self.canvas.shapesBackups.pop()

    def addLabel(self, shape):
        if shape.group_id is None:
            text = shape.label
        else:
            text = "{} ({})".format(shape.label, shape.group_id)
        label_list_item = LabelListWidgetItem(text, shape)
        self.labelList.addItem(label_list_item)
        for action in self.actions.onShapesPresent:
            action.setEnabled(True)

        self._update_shape_color(shape)
        label_list_item.setText(
            '{} <font color="#{:02x}{:02x}{:02x}">●</font>'.format(
                text, *shape.fill_color.getRgb()[:3]
            )
        )

    def copyShape(self):
        self.canvas.endMove(copy=True)
        for shape in self.canvas.selectedShapes:
            self.addLabel(shape)
        self.labelList.clearSelection()
        self.setDirty()

    def moveShape(self):
        self.canvas.endMove(copy=False)
        self.setDirty()

    def duplicateSelectedShape(self):
        added_shapes = self.canvas.duplicateSelectedShapes()
        self.labelList.clearSelection()
        for shape in added_shapes:
            self.addLabel(shape)
        self.setDirty()

    def pasteSelectedShape(self):
        self.loadShapes(self._copied_shapes, replace=False)
        self.setDirty()

    def copySelectedShape(self):
        self._copied_shapes = [s.copy() for s in self.canvas.selectedShapes]
        self.actions.paste.setEnabled(len(self._copied_shapes) > 0)

    def removeSelectedPoint(self):
        self.canvas.removeSelectedPoint()
        self.canvas.update()
        if not self.canvas.hShape.points:
            self.canvas.deleteShape(self.canvas.hShape)
            self.remLabels([self.canvas.hShape])
            self.setDirty()
            if self.noShapes():
                for action in self.actions.onShapesPresent:
                    action.setEnabled(False)

    def deleteSelectedShape(self):
        yes, no = QtWidgets.QMessageBox.Yes, QtWidgets.QMessageBox.No
        msg = self.tr(
            "You are about to permanently delete {} polygons, "
            "proceed anyway?"
        ).format(len(self.canvas.selectedShapes))
        if yes == QtWidgets.QMessageBox.warning(
            self, self.tr("Attention"), msg, yes | no, yes
        ):
            self.remLabels(self.canvas.deleteSelected())
            self.setDirty()
            if self.noShapes():
                for action in self.actions.onShapesPresent:
                    action.setEnabled(False)

    def onMoveShape(self):
        for shape in self.canvas.selectedShapes:
            rgb = self._get_rgb_by_label(shape.label,shape.group_id)
            # self.uniqLabelList.setItemLabel(item, shape.label, rgb)
            item = self.labelList.findItemByShape(shape)
            x1 = int(shape.points[0].x())
            y1 = int(shape.points[0].y())
            x2 = int(shape.points[1].x())
            y2 = int(shape.points[1].y())
            shape.label = f"({x1},{y1}),({x2},{y2})"
            text = "{} ({})".format(shape.label, shape.group_id)  # f"({x1},{y1}),({x2},{y2})"
            r, g, b = rgb
            item.setText(
                '{} <font color="#{:02x}{:02x}{:02x}">●</font>'.format(
                    text, r, g, b
                )
            )
            self.labelList.clearSelection()
            self.labelList.selectItem(item)
            self.labelList.scrollToItem(item)
            self.selectRegionId = self.labelList.selectItemIndex(item)

        # self.setDirty()

    def togglePolygons(self, value):
        for item in self.labelList:
            item.setCheckState(Qt.Checked if value else Qt.Unchecked)

    def openDirDialog(self, _value=False, dirpath=None):
        defaultOpenDirPath = dirpath if dirpath else "."
        if self.lastOpenDir and os.path.exists(self.lastOpenDir):
            defaultOpenDirPath = self.lastOpenDir
        else:
            defaultOpenDirPath = (
                os.path.dirname(self.filename) if self.filename else "."
            )

        targetDirPath = str(
            QtWidgets.QFileDialog.getExistingDirectory(
                self,
                self.tr("%s - Open Directory") % __appname__,
                defaultOpenDirPath,
                QtWidgets.QFileDialog.ShowDirsOnly
                | QtWidgets.QFileDialog.DontResolveSymlinks,
            )
        )
        self.importDirImages(targetDirPath)

    def importDirImages(self, dirpath, pattern=None, load=True):
        self.actions.openNextImg.setEnabled(True)
        self.actions.openPrevImg.setEnabled(True)

        # if not self.mayContinue() or not dirpath:
        #     return

        self.lastOpenDir = dirpath
        self.filename = None
        self.labelList.clear()
        self._ui.listWidgetResults.clear()
        # self.fileListWidget.clear()
        for filename in self.scanAllImages(dirpath):
            if pattern and pattern not in filename:
                continue
            self.imageList.append(filename)
        self.openNextImg(load=load)

    def scanAllImages(self, folderPath):
        extensions = [
            ".%s" % fmt.data().decode().lower()
            for fmt in QtGui.QImageReader.supportedImageFormats()
        ]

        images = []
        for root, dirs, files in os.walk(folderPath):
            for file in files:
                if file.lower().endswith(tuple(extensions)):
                    relativePath = os.path.join(root, file)
                    images.append(relativePath)
        images.sort(key=lambda x: x.lower())
        return images

    def toggleDrawingSensitive(self, drawing=True):
        """Toggle drawing sensitive.

        In the middle of drawing, toggling between modes should be disabled.
        """
        self.actions.editMode.setEnabled(not drawing)
        # self.actions.undoLastPoint.setEnabled(drawing)
        # self.actions.undo.setEnabled(not drawing)
        self.actions.delete.setEnabled(not drawing)

    def toggleDrawMode(self, edit=True, createMode="polygon"):
        self.canvas.setEditing(edit)
        self.canvas.createMode = createMode
        if edit:
            self.actions.createMode.setEnabled(True)
            self.actions.createRectangleMode.setEnabled(True)
            self.actions.createCircleMode.setEnabled(True)
            self.actions.createLineMode.setEnabled(True)
            self.actions.createPointMode.setEnabled(True)
            self.actions.createLineStripMode.setEnabled(True)
        else:
            if createMode == "polygon":
                self.actions.createMode.setEnabled(False)
                self.actions.createRectangleMode.setEnabled(True)
                self.actions.createCircleMode.setEnabled(True)
                self.actions.createLineMode.setEnabled(True)
                self.actions.createPointMode.setEnabled(True)
                self.actions.createLineStripMode.setEnabled(True)
            elif createMode == "rectangle":
                self.actions.createMode.setEnabled(True)
                self.actions.createRectangleMode.setEnabled(False)
                self.actions.createCircleMode.setEnabled(True)
                self.actions.createLineMode.setEnabled(True)
                self.actions.createPointMode.setEnabled(True)
                self.actions.createLineStripMode.setEnabled(True)
            elif createMode == "line":
                self.actions.createMode.setEnabled(True)
                self.actions.createRectangleMode.setEnabled(True)
                self.actions.createCircleMode.setEnabled(True)
                self.actions.createLineMode.setEnabled(False)
                self.actions.createPointMode.setEnabled(True)
                self.actions.createLineStripMode.setEnabled(True)
            elif createMode == "point":
                self.actions.createMode.setEnabled(True)
                self.actions.createRectangleMode.setEnabled(True)
                self.actions.createCircleMode.setEnabled(True)
                self.actions.createLineMode.setEnabled(True)
                self.actions.createPointMode.setEnabled(False)
                self.actions.createLineStripMode.setEnabled(True)
            elif createMode == "circle":
                self.actions.createMode.setEnabled(True)
                self.actions.createRectangleMode.setEnabled(True)
                self.actions.createCircleMode.setEnabled(False)
                self.actions.createLineMode.setEnabled(True)
                self.actions.createPointMode.setEnabled(True)
                self.actions.createLineStripMode.setEnabled(True)
            elif createMode == "linestrip":
                self.actions.createMode.setEnabled(True)
                self.actions.createRectangleMode.setEnabled(True)
                self.actions.createCircleMode.setEnabled(True)
                self.actions.createLineMode.setEnabled(True)
                self.actions.createPointMode.setEnabled(True)
                self.actions.createLineStripMode.setEnabled(False)
            else:
                raise ValueError("Unsupported createMode: %s" % createMode)
        self.actions.editMode.setEnabled(not edit)

    def setEditMode(self):
        self.toggleDrawMode(True)

    def setClean(self):
        self.dirty = False
        self.actions.save.setEnabled(False)
        self.actions.createMode.setEnabled(True)
        self.actions.createRectangleMode.setEnabled(True)
        self.actions.createCircleMode.setEnabled(True)
        self.actions.createLineMode.setEnabled(True)
        self.actions.createPointMode.setEnabled(True)
        self.actions.createLineStripMode.setEnabled(True)
        title = __appname__
        if self.filename is not None:
            title = "{} - {}".format(title, self.filename)
        self.setWindowTitle(title)

        if self.hasLabelFile():
            self.actions.deleteFile.setEnabled(True)
        else:
            self.actions.deleteFile.setEnabled(False)

    def toggleActions(self, value=True):
        """Enable/Disable widgets which depend on an opened image."""
        for z in self.actions.zoomActions:
            z.setEnabled(value)
        for action in self.actions.onLoadActive:
            action.setEnabled(value)

    def tutorial(self):
        # TODO: add readme
        pass

