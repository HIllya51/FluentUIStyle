"""基础控件页配置（对应 C++ MainWindow::initializeComponents 中基础页部分
与 setupButtonsAndIcons / changeAccentPalette）。

图标刷新由控制器 updateActionIcons 统一处理（含 circleBtn 等）。
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QMenu, QToolButton


def change_accent_palette(widget, color_hex):
    """C++ 版本仅在 Qt 6.6+（QPalette::Accent）下生效，Qt5 构建为 no-op。"""
    from PyQt5.QtGui import QPalette, QColor
    if hasattr(QPalette, "Accent"):
        palette = widget.palette()
        palette.setColor(QPalette.Accent, QColor(color_hex))
        widget.setPalette(palette)


def setup_basic_showcase(window, controller):
    w = window

    # 其他属性设置（特殊绘制开关）
    w.dial_3.setProperty("dialDrawValue", False)
    w.scrollArea_2.viewport().setAutoFillBackground(False)
    w.scrollAreaWidgetContents.setAutoFillBackground(False)
    w.scrollAreaWidgetContents_4.setAutoFillBackground(False)

    # 搜索框占位符（尾部图标由 updateActionIcons 添加/刷新）
    w.lineEditSerach.setPlaceholderText("搜索...")
    w.lineEditSerach.setClearButtonEnabled(True)

    # 进度条样式: ProgressBarThick = 1
    w.progressBar.setProperty("progressBarStyle", 1)

    # SpinBox 按钮布局: ArrowsHorizontalRight = 0
    w.spinBox.setProperty("spinBoxButtonLayout", 0)

    w.checkBox_5.setText("Off")

    # 树形控件项高度调整
    w.treeWidget.setProperty("ItemHeight", 32)
    w.treeWidget.setIndentation(20)

    # 修改部分控件的 Accent 色（Qt6.6+ 生效，Qt5 由 PaletteManager 全局管理）
    change_accent_palette(w.checkBox_2, "#4CAF50")
    change_accent_palette(w.checkBox_3, "#FFC107")
    change_accent_palette(w.checkBox_4, "#FF8F00")

    change_accent_palette(w.radioButton, "#FFC107")
    change_accent_palette(w.radioButton_2, "#FF8F00")

    # 带菜单的工具按钮
    w.toolButton_3.setAutoRaise(False)
    w.toolButton_3.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
    w.toolButton_3.setPopupMode(QToolButton.InstantPopup)
    w.toolButton_3.setText("菜单按钮")

    menu = QMenu(w.toolButton_3)
    controller.add_action(menu, "\ue8a5", "新建文件")
    controller.add_action(menu, "\ue8b5", "新建项目")
    controller.add_action(menu, "\ue8c3", "最近打开")
    controller.add_action(menu, "\ue8a5", "打开文件")

    w.toolButton_3.setMenu(menu)
    w.toolButton_4.setMenu(menu)

    # 包含文本和图标的工具按钮
    w.toolButton_4.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
    w.toolButton_4.setText("上下按钮")

    # 初始图标（刷新逻辑在控制器 updateActionIcons：含 toolButton /
    # pushButton_10 / toolButton_4 / tBtnAutoRaise / circleBtn / circleBtn2）
    controller.update_action_icons()
