from .list_item_ui import Ui_Form
from PyQt5.QtWidgets import QWidget,QListWidgetItem

# 自定义的item 继承自QListWidgetItem
class MyQListWidgetItem(QWidget):
    def __init__(self, shape, txt):
        super().__init__()
        self._ui = Ui_Form()  # 创建ui对象
        self._ui.setupUi(self)  # 构造ui

        self.shape = shape
        self.content = txt

        if self.shape:
            self._ui.labelRegion.setText(self.shape.label)
        self._ui.textEditContent.setText(self.content)


