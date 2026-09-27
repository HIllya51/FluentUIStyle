import os
import sys

# PyQt5 的 uic 解析 mainwindow.ui 里的 <customwidget> 时会按
# <header>exstackedwidget.h</header> 导入模块 exstackedwidget，
# 必须保证本目录在 sys.path 中（uic 自身只追加 CWD）。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtCore import QCoreApplication, QEasingCurve, Qt, QTimer
from PyQt5.QtGui import QFont, QIcon
from PyQt5.QtWidgets import QApplication, QStyleFactory

import exstackedwidget  # noqa: F401  供 uic 按模块名解析 ExStackedWidget

from basic_showcase import setup_basic_showcase
from extra_pages import (
    setup_about_page,
    setup_changelog_page,
    setup_dialogs_page,
    setup_icons_page,
    setup_mdi_page,
)
from gallerywindow import GALLERY_DIR, GalleryWindow
from mainwindow import MainWindowController
from tab_showcase import setup_tab_showcase
from table_showcase import setup_table_widget
from utils import apply_dwm_dark_titlebar, is_system_dark_theme

WINDOW_TITLE = "FluentUI Gallery - QStyle [PyQt5 | x64 | Qt {}]"


def create_window(app):
    """构建主窗口（不进入事件循环），便于自动化测试复用。"""
    from PyQt5.QtCore import QT_VERSION_STR

    # FluentUI3 样式相关的全局开关（与 C++ Gallery 保持一致）
    app.setProperty("_q_scrollHint_center", False)   # True 时使用 Qt 原生居中弹出
    app.setProperty("_q_themestyle", 0)              # 0=Fluent 配色, 1=Teams 配色
    app.setProperty("_q_colorscheme", 1 if is_system_dark_theme() else 0)  # 0=浅色, 1=暗色

    window = GalleryWindow(os.path.join(GALLERY_DIR, "mainwindow.ui"))
    window.setWindowIcon(QIcon(os.path.join(GALLERY_DIR, "resources", "appicon.ico")))
    window.setWindowTitle(WINDOW_TITLE.format(QT_VERSION_STR))

    # 集中处理主窗口绑定（菜单、工具栏、标题栏接线、全局设置）
    controller = MainWindowController(window)

    # C++ Gallery 在代码里补充设置的窗口级属性（.ui 中没有）
    window.centralWidget().setAttribute(Qt.WA_TranslucentBackground, True)
    window.centralWidget().setAttribute(Qt.WA_StyledBackground, True)

    # 设置页（须在导航构建前，radio 桥接层就位）
    controller.setup_settings_page()

    # 纯 PyQt5 构建的运行时页面（对应 C++ 里 addWidget 的页面）
    # 注意添加顺序：C++ 依赖索引 7=图标库、8=关于，这里保持一致
    setup_icons_page(window)      # -> 索引 7 (pageIcons)
    setup_about_page(window)      # -> 索引 8 (pageAbout)
    setup_dialogs_page(window)    # -> 索引 9 (pageDialogs)
    setup_changelog_page(window)  # -> 索引 10 (pageChangelog)
    setup_mdi_page(window)        # 填充 .ui 中预留的空 page_5

    # 导航（须在运行时页面创建后，按 objectName 解析索引）
    controller.setup_navigation()

    # 子模块 UI 逻辑
    setup_basic_showcase(window, controller)
    setup_tab_showcase(window, controller)

    # 标题栏接线（主题切换/置顶/强调色）
    controller.setup_title_bar_chrome()

    # 堆叠窗口：纵向滑动切页动画（对应 C++ setVerticalMode/InOutSine/300ms）
    window.stackedWidget.setVerticalMode(True)
    window.stackedWidget.setAnimation(QEasingCurve.InOutSine)
    window.stackedWidget.setSpeed(300)

    # 表格页懒加载：首次切到表格页或启动 1.2s 后预热再枚举已安装软件，
    # 避免注册表查询阻塞冷启动（同 C++ Gallery 的 ensureInitialized 策略）
    table_ready = {"done": False}

    def init_table():
        if not table_ready["done"]:
            table_ready["done"] = True
            setup_table_widget(window)

    window.stackedWidget.currentChanged.connect(
        lambda index: init_table() if index == 1 else None)
    QTimer.singleShot(1200, init_table)

    # 停靠窗口日志（changelog）
    window.loadChangelog()

    # 初始页面与图标刷新
    window.stackedWidget.setCurrentIndex(0)
    controller.update_action_icons()

    return window, controller


def main():
    # Qt5 下需要显式开启高 DPI（Qt6 默认开启）
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)

    # 兜底：也可把 FluentUI3StylePlugin.dll 放到本目录 plugins/styles 下，
    # 已放入 PyQt5 的 plugins/styles（site-packages）时无需此步。
    plugin_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plugins")
    if os.path.isdir(plugin_path):
        QCoreApplication.addLibraryPath(plugin_path)

    if "FluentUI3" not in QStyleFactory.keys():
        print("未找到 FluentUI3 样式插件。请确认 FluentUI3StylePlugin.dll（Qt5 构建、"
              "与 Python 位数一致）已放入 PyQt5 的 plugins/styles 或本目录的 plugins/styles 下。")
        sys.exit(-1)

    app.setStyle("FluentUI3")

    font = app.font()
    font.setPixelSize(13)
    font.setFamily("微软雅黑")
    font.setHintingPreference(QFont.PreferNoHinting)
    app.setFont(font)

    window, _controller = create_window(app)
    window.show()
    apply_dwm_dark_titlebar(window, app.property("_q_colorscheme") == 1)

    rc = app.exec_()

    # ---- 退出 ----
    # uic 加载的大控件树 + Python 重写的虚拟函数（nativeEvent/paintEvent 等）
    # 在解释器关闭阶段的析构顺序存在竞态：无论 deleteLater 还是显式析构
    # QApplication，都可能段错误——表现为退出时鼠标忙圈转个不停。
    # 界面数据无需落盘，事件循环已结束，直接结束进程最稳妥。
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(rc)


if __name__ == "__main__":
    main()
