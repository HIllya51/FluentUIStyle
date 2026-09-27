"""主窗口控制器（对应 C++ MainWindow 的菜单/工具栏/导航/主题等逻辑）。

C++ 侧对应：
- buildMainMenus / rebuildMenuAndToolBar / setupToolBarControls
- initializeNavigationView（导航树 + footer）
- applyThemeIndex / applyAccentColor / applyWidgetBgMode / refreshFluentStyle
- updateActionIcons（搜索框、Tab、按钮、菜单、导航图标）
- setupAccentColorWidget / setupTitleBarChrome / setTopMost
- on_checkBox_4/5、on_radioButton_4..7 等槽
- QLineEdit/QTextEdit/QComboBox/QAbstractSpinBox 的标准右键菜单图标
  （C++ 通过重写 contextMenuEvent，Python 用应用级事件过滤器实现）
"""

import ctypes
import ctypes.wintypes as wt
import os

from PyQt5.QtCore import QEvent, QObject, QPoint, Qt
from PyQt5.QtGui import QContextMenuEvent, QKeySequence
from PyQt5.QtWidgets import (
    QAbstractSpinBox,
    QAction,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMenu,
    QMenuBar,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QStyleFactory,
    QTabBar,
    QTextEdit,
    QTreeWidgetItem,
    QWidget,
)

from exwidgets import ExWinUINavigationView
from settings_page import build_settings_page
from utils import apply_dwm_dark_titlebar, create_fluent_icon

# 右键菜单标准图标（applyStandardMenuIcons 的码点表）
_CTX_GLYPHS = [
    ("undo", "\ue7a7"),
    ("redo", "\ue7a6"),
    ("cut", "\ue8c6"),
    ("copy", "\ue8c8"),
    ("paste", "\ue77f"),
    ("select all", "\ue8b3"),
    ("selectall", "\ue8b3"),
    ("delete", "\ue74d"),
    ("clear", "\ue74d"),
    ("step up", "\ue70e"),
    ("step down", "\ue70d"),
]


def refresh_fluent_style():
    if "FluentUI3" in QStyleFactory.keys():
        QApplication.instance().setStyle("FluentUI3")


def apply_accent_color(color):
    app = QApplication.instance()
    app.setProperty("_q_accent_color", color if color.isValid() else None)
    refresh_fluent_style()


def set_top_most(window, top_most):
    try:
        ctypes.windll.user32.SetWindowPos(
            wt.HWND(int(window.windowHandle().winId())),
            wt.HWND(-1 if top_most else -2),  # HWND_TOPMOST / HWND_NOTOPMOST
            0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)  # SWP_NOMOVE|SWP_NOSIZE|SWP_NOACTIVATE
    except Exception as e:  # noqa: BLE001
        print("置顶设置失败:", e)


class StandardContextMenuFilter(QObject):
    """给标准右键菜单补上 Segoe 图标（对应 C++ 重写的各 contextMenuEvent）。"""

    def __init__(self, parent=None):
        super().__init__(parent)

    def _apply_standard_menu_icons(self, menu):
        for action in menu.actions():
            if action.isSeparator():
                continue
            sub_menu = action.menu()
            if sub_menu is not None:
                self._apply_standard_menu_icons(sub_menu)
                continue
            if not action.icon().isNull():
                continue
            text = action.text().replace("&", "").lower()
            for key, glyph in _CTX_GLYPHS:
                if key in text:
                    action.setIcon(create_fluent_icon(glyph))
                    break

    def eventFilter(self, watched, event):
        if event.type() != QEvent.ContextMenu:
            return False

        if isinstance(watched, QLineEdit) and watched.contextMenuPolicy() == Qt.DefaultContextMenu:
            menu = watched.createStandardContextMenu()
            if menu is not None:
                self._apply_standard_menu_icons(menu)
                menu.setAttribute(Qt.WA_DeleteOnClose)
                menu.exec_(event.globalPos())
                return True

        elif isinstance(watched, QTextEdit) and watched.contextMenuPolicy() == Qt.DefaultContextMenu:
            menu = watched.createStandardContextMenu()
            if menu is not None:
                self._apply_standard_menu_icons(menu)
                menu.setAttribute(Qt.WA_DeleteOnClose)
                menu.exec_(event.globalPos())
                return True

        elif isinstance(watched, QComboBox) and watched.lineEdit() is not None:
            menu = watched.lineEdit().createStandardContextMenu()
            if menu is not None:
                self._apply_standard_menu_icons(menu)
                menu.setAttribute(Qt.WA_DeleteOnClose)
                menu.exec_(event.globalPos())
                return True

        elif isinstance(watched, QAbstractSpinBox) and watched.contextMenuPolicy() == Qt.DefaultContextMenu:
            edit = watched.findChild(QLineEdit)
            if edit is None:
                return False
            menu = edit.createStandardContextMenu()
            if menu is None:
                return False
            menu.addSeparator()
            step_enabled = watched.stepEnabled()
            step_up = menu.addAction("&Step up")
            step_up.setEnabled(bool(step_enabled & QAbstractSpinBox.StepUpEnabled))
            step_down = menu.addAction("Step &down")
            step_down.setEnabled(bool(step_enabled & QAbstractSpinBox.StepDownEnabled))
            self._apply_standard_menu_icons(menu)

            if event.reason() == QContextMenuEvent.Mouse:
                pos = event.globalPos()
            else:
                pos = watched.mapToGlobal(QPoint(event.pos().x(), 0)) + QPoint(
                    watched.width() // 2, watched.height() // 2)
            action = menu.exec_(pos)
            menu.deleteLater()
            if action is not None:
                if action == step_up:
                    watched.stepBy(1)
                elif action == step_down:
                    watched.stepBy(-1)
            return True

        return False


class MainWindowController:
    def __init__(self, window):
        self.window = window
        self.app = QApplication.instance()

        # 1:1 C++ 里的 g_actionIconMap / g_menuIconMap
        self.action_icon_map = {}
        self.menu_icon_map = {}
        self.tabbar_icon_map = {}
        self._search_action = None
        self._update_tab_icons_cb = None
        self.theme_combo = None
        self.scheme_combo = None
        self.style_combo = None
        self.bg_tab = None
        self.nav_toggle_action = None
        self.nav_view = None
        self.menu_bar = None
        self.tool_bar = None
        self.settings_widgets = None

        self.initialize_fluent_border_widgets()
        self.build_menu_and_toolbar()
        self.setup_combobox()
        self.setup_basic_slots()
        self.setup_accent_color_widget()
        self.install_context_menu_filter()

    # =========================================================================
    # 基础页卡片化（对应 initializeFluentBorderWidgets）
    # =========================================================================
    def initialize_fluent_border_widgets(self):
        fluent_widgets = [
            self.window.widget, self.window.widget_2, self.window.widget_3, self.window.widget_4,
            self.window.widget_5, self.window.widget_6, self.window.widget_7, self.window.widget_8,
            self.window.widget_9, self.window.widget_10, self.window.widget_12, self.window.widget_13,
            self.window.widget_14,
        ]
        for w in fluent_widgets:
            w.setAttribute(Qt.WA_StyledBackground)
            w.setProperty("isCard", True)

    # =========================================================================
    # 菜单与工具栏
    # =========================================================================
    def add_action(self, parent, icon_code, text):
        action = parent.addAction(create_fluent_icon(icon_code), text)
        self.action_icon_map[action] = icon_code
        return action

    def add_menu(self, parent, icon_code, text):
        menu = parent.addMenu(create_fluent_icon(icon_code), text)
        self.menu_icon_map[menu] = icon_code
        return menu

    def build_menu_and_toolbar(self):
        # C++ 新建 menubar（objectName win-menu-bar）并替换 .ui 默认的
        self.menu_bar = QMenuBar(self.window)
        self.menu_bar.setObjectName("win-menu-bar")
        self.build_main_menus()

        self.tool_bar = self.window.addToolBar("工具栏")
        self.nav_toggle_action = self.add_action(self.tool_bar, "\ue700", "")
        self.nav_toggle_action.triggered.connect(self._on_nav_toggle_triggered)
        self.tool_bar.addSeparator()

        # 文件操作
        a_new = self.add_action(self.tool_bar, "\ue8a5", "新建")
        a_new.setShortcut(QKeySequence("Ctrl+N"))
        a_open = self.add_action(self.tool_bar, "\ue8a5", "打开")
        a_open.setShortcut(QKeySequence("Ctrl+O"))
        a_save = self.add_action(self.tool_bar, "\ue74e", "保存")
        a_save.setShortcut(QKeySequence("Ctrl+S"))
        self.tool_bar.addSeparator()

        # 编辑操作
        a_undo = self.add_action(self.tool_bar, "\ue7a7", "撤销")
        a_undo.setShortcut(QKeySequence("Ctrl+Z"))
        a_redo = self.add_action(self.tool_bar, "\ue7a6", "重做")
        a_redo.setShortcut(QKeySequence("Ctrl+Y"))
        self.tool_bar.addSeparator()

        a_cut = self.add_action(self.tool_bar, "\ue8c6", "剪切")
        a_cut.setShortcut(QKeySequence("Ctrl+X"))
        a_copy = self.add_action(self.tool_bar, "\ue8c8", "复制")
        a_copy.setShortcut(QKeySequence("Ctrl+C"))
        a_paste = self.add_action(self.tool_bar, "\ue8c7", "粘贴")
        a_paste.setShortcut(QKeySequence("Ctrl+V"))
        self.tool_bar.addSeparator()

        # 构建操作
        a_build = self.add_action(self.tool_bar, "\ue7b8", "构建")
        a_build.setShortcut(QKeySequence("Ctrl+B"))
        self.add_action(self.tool_bar, "\ue7b8", "重新构建")
        self.add_action(self.tool_bar, "\ue768", "运行")
        self.tool_bar.addSeparator()

        self.setup_toolbar_controls()

        self.tool_bar.setAttribute(Qt.WA_TranslucentBackground, True)
        self.tool_bar.setAttribute(Qt.WA_StyledBackground, False)
        self.tool_bar.setAutoFillBackground(False)

        # 无边框：菜单栏进 chrome header；否则替换 QMainWindow 的菜单栏
        if os.environ.get("GALLERY_FRAMELESS", "1") != "0":
            self.window.installChromeHeader(self.menu_bar)
        else:
            self.window.setMenuBar(self.menu_bar)

    def build_main_menus(self):
        menu_bar = self.menu_bar

        # --- 文件 ---
        file_menu = menu_bar.addMenu("文件")
        a_new_file = self.add_action(file_menu, "\ue8a5", "新建文件")
        a_new_file.setShortcut(QKeySequence("Ctrl+N"))
        self.add_action(file_menu, "\ue8b5", "新建项目")

        recent_menu = self.add_menu(file_menu, "\ue8c3", "最近打开")
        recent_menu.addAction("project1")
        recent_menu.addAction("project2")
        recent_menu.addAction("example.cpp")

        a_open = self.add_action(file_menu, "\ue8a5", "打开文件")
        a_open.setShortcut(QKeySequence("Ctrl+O"))
        self.add_action(file_menu, "\ue8b5", "打开项目")
        file_menu.addSeparator()
        a_save = self.add_action(file_menu, "\ue74e", "保存")
        a_save.setShortcut(QKeySequence("Ctrl+S"))
        a_save_as = self.add_action(file_menu, "\ue74e", "另存为")
        a_save_as.setShortcut(QKeySequence("Ctrl+Shift+S"))
        file_menu.addSeparator()
        self.add_action(file_menu, "\ue8bb", "关闭文件")
        a_exit = self.add_action(file_menu, "\ue8bb", "退出")
        a_exit.setShortcut(QKeySequence("Ctrl+Q"))
        a_exit.triggered.connect(self.window.close)

        # --- 编辑 ---
        edit_menu = menu_bar.addMenu("编辑")
        a_undo = self.add_action(edit_menu, "\ue7a7", "撤销")
        a_undo.setShortcut(QKeySequence("Ctrl+Z"))
        a_redo = self.add_action(edit_menu, "\ue7a6", "重做")
        a_redo.setShortcut(QKeySequence("Ctrl+Y"))
        edit_menu.addSeparator()
        a_cut = self.add_action(edit_menu, "\ue8c6", "剪切")
        a_cut.setShortcut(QKeySequence("Ctrl+X"))
        a_copy = self.add_action(edit_menu, "\ue8c8", "复制")
        a_copy.setShortcut(QKeySequence("Ctrl+C"))
        a_paste = self.add_action(edit_menu, "\ue8c7", "粘贴")
        a_paste.setShortcut(QKeySequence("Ctrl+V"))
        edit_menu.addSeparator()
        a_find = self.add_action(edit_menu, "\ue721", "查找")
        a_find.setShortcut(QKeySequence("Ctrl+F"))
        a_replace = self.add_action(edit_menu, "\ue8ac", "替换")
        a_replace.setShortcut(QKeySequence("Ctrl+H"))

        advanced_menu = self.add_menu(edit_menu, "\ue713", "高级")
        a_format = self.add_action(advanced_menu, "\ue930", "自动格式化")
        a_format.setCheckable(True)
        self.add_action(advanced_menu, "\ue930", "排序行")
        self.add_action(advanced_menu, "\ue8bb", "删除空行")

        # --- 视图 ---
        view_menu = menu_bar.addMenu("视图")
        a_show_tb = self.add_action(view_menu, "\ue728", "显示工具栏")
        a_show_tb.setCheckable(True)
        a_show_tb.setChecked(True)
        a_show_tb.triggered.connect(lambda checked: self.tool_bar.setVisible(checked))
        a_show_sb = self.add_action(view_menu, "\ue9d9", "显示状态栏")
        a_show_sb.setCheckable(True)
        a_show_sb.setChecked(True)
        a_show_sb.triggered.connect(lambda checked: self.window.statusBar().setVisible(checked))
        view_menu.addSeparator()
        a_show_sidebar = self.add_action(view_menu, "\ue728", "显示侧边栏")
        a_show_sidebar.setCheckable(True)
        a_show_sidebar.setChecked(True)
        a_show_out = self.add_action(view_menu, "\ue7e8", "显示输出窗口")
        a_show_out.setCheckable(True)

        zoom_menu = self.add_menu(view_menu, "\ue71e", "缩放")
        zoom_menu.addAction("放大")
        zoom_menu.addAction("缩小")
        zoom_menu.addAction("恢复默认")

        # --- 构建 ---
        build_menu = menu_bar.addMenu("构建")
        a_build = self.add_action(build_menu, "\ue7b8", "构建项目")
        a_build.setShortcut(QKeySequence("Ctrl+B"))
        self.add_action(build_menu, "\ue7b8", "重新构建")
        build_menu.addSeparator()
        self.add_action(build_menu, "\ue768", "运行")
        self.add_action(build_menu, "\ue7a6", "调试")
        build_target = self.add_menu(build_menu, "\ue8b5", "构建目标")
        build_target.addAction("Debug")
        build_target.addAction("Release")

        # --- 帮助（无 ExTour，跳过“功能导览”） ---
        help_menu = menu_bar.addMenu("帮助")
        self.add_action(help_menu, "\ue8a5", "文档")
        self.add_action(help_menu, "\ue8a5", "API参考")
        help_menu.addSeparator()
        self.add_action(help_menu, "\ue7b8", "检查更新")
        help_menu.addSeparator()
        self.add_action(help_menu, "\ue946", "关于")

    def setup_toolbar_controls(self, tool_bar=None):
        tool_bar = tool_bar or self.tool_bar

        # 禁用开关
        disable_cb = QCheckBox("禁用", tool_bar)
        disable_cb.setProperty("isSwitchButton", True)
        disable_cb.clicked.connect(
            lambda checked: self.window.centralWidget().setEnabled(not checked))
        tool_bar.addWidget(disable_cb)
        tool_bar.addSeparator()

        self.setup_theme_selector(tool_bar)
        tool_bar.addSeparator()
        self.setup_color_scheme_selector(tool_bar)
        tool_bar.addSeparator()
        self.setup_style_selector(tool_bar)
        tool_bar.addSeparator()
        self.setup_widget_background_selector(tool_bar)

    def setup_theme_selector(self, tool_bar):
        tool_bar.addWidget(QLabel("主题：", tool_bar))
        self.theme_combo = QComboBox(tool_bar)
        self.theme_combo.blockSignals(True)
        self.theme_combo.addItem("浅色")
        self.theme_combo.addItem("暗色")
        self.theme_combo.blockSignals(False)
        self.theme_combo.setView(QListView(self.theme_combo))
        self.theme_combo.setCurrentIndex(1 if self.app.property("_q_colorscheme") == 1 else 0)
        self.theme_combo.currentIndexChanged.connect(self.apply_theme_index)
        if self.theme_combo.currentIndex() == 1:
            self.window.rBDarkTheme.setChecked(True)
        else:
            self.window.rBLightTheme.setChecked(True)
        tool_bar.addWidget(self.theme_combo)

    def setup_color_scheme_selector(self, tool_bar):
        tool_bar.addWidget(QLabel("配色：", tool_bar))
        self.scheme_combo = QComboBox(tool_bar)
        self.scheme_combo.blockSignals(True)
        self.scheme_combo.addItem("Fluent")
        self.scheme_combo.addItem("Teams")
        self.scheme_combo.blockSignals(False)
        self.scheme_combo.setView(QListView(self.scheme_combo))

        def on_scheme_changed(index):
            self.app.setProperty("_q_themestyle", index)
            refresh_fluent_style()
            self.update_action_icons()

        self.scheme_combo.currentIndexChanged.connect(on_scheme_changed)
        tool_bar.addWidget(self.scheme_combo)

    def setup_style_selector(self, tool_bar):
        tool_bar.addWidget(QLabel("样式：", tool_bar))
        self.style_combo = QComboBox(tool_bar)
        self.style_combo.addItems(QStyleFactory.keys())
        self.style_combo.setView(QListView(self.style_combo))

        def on_style_changed(_index):
            self.app.setStyle(self.style_combo.currentText())
            self.update_action_icons()

        self.style_combo.currentIndexChanged.connect(on_style_changed)
        tool_bar.addWidget(self.style_combo)

    def setup_widget_background_selector(self, tool_bar):
        tool_bar.addWidget(QLabel("窗口背景：", tool_bar))
        self.bg_tab = QTabBar(tool_bar)
        self.bg_tab.setProperty("tabBarStyle", 9)  # Segmented_WinUI3
        self.bg_tab.addTab("无")
        self.bg_tab.addTab("图片")
        self.bg_tab.addTab("DWM blur")
        tool_bar.addWidget(self.bg_tab)

        def on_bg_changed(index):
            self.apply_widget_bg_mode(index)
            radios = [self.window.rBWidgtModeNormal, self.window.rBWidgetModePixmap,
                      self.window.rBWidgetModeDwmBlur]
            if 0 <= index < len(radios):
                radios[index].setChecked(True)

        self.bg_tab.currentChanged.connect(on_bg_changed)

    # =========================================================================
    # 主题 / 配色 / 背景 / 强调色
    # =========================================================================
    def apply_theme_index(self, index):
        if self.theme_combo is not None:
            self.theme_combo.blockSignals(True)
            self.theme_combo.setCurrentIndex(index)
            self.theme_combo.blockSignals(False)

        self.app.setProperty("_q_colorscheme", index)
        refresh_fluent_style()
        self.update_action_icons()

        if index == 0:
            self.window.rBLightTheme.setChecked(True)
        else:
            self.window.rBDarkTheme.setChecked(True)

        title_bar = self.window.titleBar()
        if title_bar is not None:
            title_bar.setThemeDark(index == 1)
        apply_dwm_dark_titlebar(self.window, index == 1)

    def apply_widget_bg_mode(self, mode):
        self.app.setProperty("_q_widget_mode", mode)
        refresh_fluent_style()
        self.window.setWidgetBgMode(mode)

    # =========================================================================
    # 导航
    # =========================================================================
    def _on_nav_toggle_triggered(self, _checked=False):
        if self.nav_view is None:
            return
        expand = self.nav_view.navigationExpanded()
        self.nav_view.setNavigationExpanded(not expand)
        self.window.rBOnlyIcon.setChecked(expand)
        self.window.rBIconAndText.setChecked(not expand)

    def setup_navigation(self):
        self.nav_view = ExWinUINavigationView(self.window)
        self.nav_view.setObjectName("winUINavigationView")
        self.nav_view.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Expanding)
        self.window.navigationPaneLayout.addWidget(self.nav_view, 0, 0)

        nav = self.nav_view
        nav.addNavigationItem("基础控件", 0, "\ue80f")
        nav.addNavigationItem("表格控件", 1, "\ue99a")
        nav.addNavigationItem("列表控件", 2, "\ue71d")
        nav.addNavigationItem("树形控件", 3, "\ued28")
        nav.addNavigationItem("导航控件", 4, "\ue8b0")
        # ExWidgets 子树：C++ 仅在 pageExRangeSlider 存在时创建（纯 PyQt5 无该页，跳过）
        nav.addNavigationItem("Mdi", 5, "\ue9d9")

        # 运行时页面按 objectName 解析索引
        def page_index_by_name(name):
            page = self.window.stackedWidget.findChild(QWidget, name)
            return self.window.stackedWidget.indexOf(page) if page is not None else -1

        icons_page = page_index_by_name("pageIcons")
        if icons_page >= 0:
            nav.addNavigationItem("图标库", icons_page, "\ue8fd")
        dialogs_page = page_index_by_name("pageDialogs")
        if dialogs_page >= 0:
            nav.addNavigationItem("对话框", dialogs_page, "\ue8f2")

        # 测试节点（演示导航控件的多级树形展开）
        nav_view = nav.mainNavView()

        def add_nav_child(parent, text, page_index):
            item = QTreeWidgetItem(parent)
            nav_view.configureNavigationItem(item, text, page_index, "")
            return item

        test_root = add_nav_child(nav_view, "测试节点", 6)
        for i in range(5):
            child = add_nav_child(test_root, f"子节点{i+1}", 6)
            for j in range(3):
                add_nav_child(child, f"子节点{i+1}-{j+1}", 6)

        # footer
        changelog_page = page_index_by_name("pageChangelog")
        if changelog_page >= 0:
            nav.addFooterNavigationItem("更新日志", changelog_page, "\ue823")
        nav.addFooterNavigationItem("关于", 8, "\ue77b")
        nav.addFooterNavigationItem("设置", 6, "\ue713")

        nav.setStackedWidget(self.window.stackedWidget)
        nav.setNavigationExpanded(True, False)
        nav.clearFooterSelection()

    # =========================================================================
    # 基础页杂项槽（对应 C++ on_* 槽）
    # =========================================================================
    def setup_combobox(self):
        self.window.comboBox.setView(QListView(self.window.comboBox))

    def setup_basic_slots(self):
        w = self.window
        w.checkBox_4.clicked.connect(lambda checked: w.checkBox_5.setChecked(checked))
        w.checkBox_5.stateChanged.connect(
            lambda state: w.checkBox_5.setText("On" if state == Qt.Checked else "Off"))

        # SpinBox 按钮布局：radioButton_5/4/7/6 -> 0/2/1/3
        def set_spin_layout(layout):
            w.spinBox.setProperty("spinBoxButtonLayout", layout)
            w.spinBox.setFrame(w.spinBox.hasFrame())

        w.radioButton_5.clicked.connect(lambda: set_spin_layout(0))  # ArrowsHorizontalRight
        w.radioButton_4.clicked.connect(lambda: set_spin_layout(2))  # ArrowsHorizontalSides
        w.radioButton_7.clicked.connect(lambda: set_spin_layout(1))  # ArrowsVertical
        w.radioButton_6.clicked.connect(lambda: set_spin_layout(3))  # PlusMinusHorizontalSides

        # 主题 radio -> 工具栏组合框
        w.rBLightTheme.clicked.connect(lambda: self.theme_combo.setCurrentIndex(0))
        w.rBDarkTheme.clicked.connect(lambda: self.theme_combo.setCurrentIndex(1))

        # 背景 radio -> 工具栏背景 TabBar
        w.rBWidgtModeNormal.clicked.connect(lambda: self.bg_tab.setCurrentIndex(0))
        w.rBWidgetModePixmap.clicked.connect(lambda: self.bg_tab.setCurrentIndex(1))
        w.rBWidgetModeDwmBlur.clicked.connect(lambda: self.bg_tab.setCurrentIndex(2))

        # 导航 radio -> 展开状态
        w.rBOnlyIcon.clicked.connect(lambda: self.nav_view.setNavigationExpanded(False))
        w.rBIconAndText.clicked.connect(lambda: self.nav_view.setNavigationExpanded(True))

    # =========================================================================
    # 标题栏接线（对应 setupTitleBarChrome）
    # =========================================================================
    def setup_title_bar_chrome(self):
        title_bar = self.window.titleBar()
        if title_bar is None:
            return

        is_dark = self.app.property("_q_colorscheme") == 1
        title_bar.setThemeDark(is_dark)

        title_bar.themeButton().clicked.connect(
            lambda: self.apply_theme_index(0 if self.app.property("_q_colorscheme") == 1 else 1))

        def on_pin_toggled(checked):
            set_top_most(self.window, checked)
            title_bar.setPinned(checked)

        title_bar.pinButton().toggled.connect(on_pin_toggled)
        title_bar.accentColorChanged.connect(apply_accent_color)

    # =========================================================================
    # 强调色（对应 setupAccentColorWidget）
    # =========================================================================
    def setup_accent_color_widget(self):
        from PyQt5.QtGui import QColor, QFont

        container = self.window.widgetAccentColor
        if container.layout() is not None:
            QWidget().setLayout(container.layout())

        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        colors = [
            None,              # Default（无效色表示恢复默认）
            QColor("#FFB900"),
            QColor("#FF8C00"),
            QColor("#E81123"),
            QColor("#E3008C"),
            QColor("#881798"),
            QColor("#0078D4"),
            QColor("#00B7C3"),
            QColor("#107C10"),
        ]

        icon_font = QFont("Segoe Fluent Icons")
        icon_font.setPixelSize(20)

        btn_group = QButtonGroup(self.window)
        btn_group.setExclusive(True)

        for i, color in enumerate(colors):
            btn = QPushButton(container)
            btn.setFixedSize(40, 40)
            btn.setCheckable(True)
            btn.setFont(icon_font)
            btn_group.addButton(btn, i)

            bg_color = color if color else QColor("#0078D4")
            # 不带 :hover/:pressed 规则——悬停时保持调色板原色不变（Qt5 构建
            # 下 QSS 悬停色与 FluentUI3Style 的悬停层叠加后观感发白，与
            # C++ Qt6 构建的实际显示不一致）
            style = f"""
                QPushButton {{
                    background-color: {bg_color.name()};
                    border: 1px solid rgba(0, 0, 0, 0.1);
                    border-radius: 4px;
                }}
            """
            btn.setStyleSheet(style)
            btn.setToolTip("恢复默认" if not color else color.name())
            layout.addWidget(btn)

        layout.addSpacerItem(QSpacerItem(1, 1, QSizePolicy.Expanding, QSizePolicy.Preferred))

        def on_color_clicked(btn_id):
            for b in btn_group.buttons():
                b.setText("")

            clicked_btn = btn_group.button(btn_id)
            if clicked_btn is not None:
                clicked_btn.setText("\ue73e")

            color = colors[btn_id]
            if color is not None:
                self.app.setProperty("_q_accent_color", color)
            else:
                self.app.setProperty("_q_accent_color", None)
            refresh_fluent_style()

        btn_group.idClicked.connect(on_color_clicked)

        default_btn = btn_group.button(0)
        if default_btn is not None:
            default_btn.setChecked(True)
            default_btn.setText("\ue73e")

    # =========================================================================
    # 设置页
    # =========================================================================
    def setup_settings_page(self):
        def on_about_clicked():
            if self.nav_view is not None:
                self.nav_view.setSelectedPageIndex(8)
            else:
                self.window.stackedWidget.setCurrentIndex(8)

        self.settings_widgets = build_settings_page(self.window, on_about_clicked)

    # =========================================================================
    # 图标刷新（对应 updateActionIcons）
    # =========================================================================
    def register_tab_icons_updater(self, callback):
        self._update_tab_icons_cb = callback

    def update_action_icons(self):
        w = self.window

        # 搜索框尾部图标（先移除旧的再补新的）
        if self._search_action is not None:
            w.lineEditSerach.removeAction(self._search_action)
        self._search_action = w.lineEditSerach.addAction(
            create_fluent_icon("\ue721"), QLineEdit.TrailingPosition)
        self.action_icon_map[self._search_action] = "\ue721"

        # Tab 展示页图标
        if self._update_tab_icons_cb is not None:
            self._update_tab_icons_cb()

        # 按钮图标
        w.toolButton.setIcon(create_fluent_icon("\ue8c3"))
        w.pushButton_10.setIcon(create_fluent_icon("\ue713"))
        w.toolButton_4.setIcon(create_fluent_icon("\ue804"))
        w.tBtnAutoRaise.setIcon(create_fluent_icon("\ue804"))
        w.circleBtn.setIcon(create_fluent_icon("\ue713"))
        w.circleBtn2.setIcon(create_fluent_icon("\ue8c3"))

        # 菜单 action / 菜单图标
        for action, code in self.action_icon_map.items():
            action.setIcon(create_fluent_icon(code))
        for menu, code in self.menu_icon_map.items():
            menu.setIcon(create_fluent_icon(code))

        # 导航树图标由 ExNavTreeWidget.changeEvent(StyleChange) 自动刷新

    # =========================================================================
    # 右键菜单图标
    # =========================================================================
    def install_context_menu_filter(self):
        self._context_menu_filter = StandardContextMenuFilter(self.window)
        self.app.installEventFilter(self._context_menu_filter)
