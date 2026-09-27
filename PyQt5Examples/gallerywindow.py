"""GalleryWindow —— 主窗口子类（C++ MainWindow 的纯 PyQt5 等价物）。

对应 C++ 侧：
- MainWindow::paintEvent     -> 背景图 / DWM blur 模式绘制
- FluentWindowFrame          -> 纯 Python 无边框方案（保留 WS_THICKFRAME，
                                用 WM_NCCALCSIZE 去掉原生标题栏与边框占位，
                                WM_NCHITTEST 提供拖动 / 8 向缩放 / Snap Layouts）
- installChromeHeader        -> setMenuWidget(标题栏 + 菜单栏)
- loadChangelog              -> 填充右侧停靠窗口的日志
"""

import ctypes
import ctypes.wintypes as wt
import os

from PyQt5.QtCore import QEvent, QPoint, QRect, Qt, QTimer
from PyQt5.QtGui import QPainter, QPixmap, QTextCursor
from PyQt5.QtWidgets import QMainWindow, QWidget
from PyQt5.uic import loadUi

from exwidgets import FluentTitleBar

GALLERY_DIR = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Examples", "Gallery")
)

# Win32 常量
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_NCCALCSIZE = 0x0083
WM_NCHITTEST = 0x0084
WM_NCRBUTTONUP = 0x00A5
WM_NCDESTROY = 0x0082
WM_UAHDESTROYWINDOW = 0x0090        # 未公开消息
WM_UNREGISTER_WINDOW_SERVICES = 0x0272  # 未公开消息
HTCLIENT = 1
HTCAPTION = 2
HTLEFT, HTRIGHT, HTTOP, HTTOPLEFT, HTTOPRIGHT = 10, 11, 12, 13, 14
HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT = 15, 16, 17
HTMAXBUTTON = 9
SM_CXSIZEFRAME = 32
SM_CXPADDEDBORDER = 92
GWL_STYLE = -16
WS_MAXIMIZEBOX = 0x00010000
WS_MINIMIZEBOX = 0x00020000
WS_THICKFRAME = 0x00040000
WS_SYSMENU = 0x00080000
WS_CAPTION = 0x00C00000
SWP_FRAMECHANGED = 0x0020
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_DEFAULT, DWMWCP_DONOTROUND, DWMWCP_ROUND, DWMWCP_ROUNDSMALL = 0, 1, 2, 3
DWMWA_SYSTEMBACKDROP_TYPE = 38
DWMBT_NONE = 1
DWMBT_MAINWINDOW = 2       # Mica
DWMBT_TRANSIENTWINDOW = 3  # Acrylic
DWMBT_TABBEDWINDOW = 4     # Mica Alt


class _MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wt.HWND),
        ("message", wt.UINT),
        ("wParam", wt.WPARAM),
        ("lParam", wt.LPARAM),
        ("time", wt.DWORD),
        ("pt", wt.POINT),
        ("lPrivate", wt.DWORD),
    ]


class _NCCALCSIZE_PARAMS(ctypes.Structure):
    class _RECT3(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    _fields_ = [("rgrc", _RECT3 * 3), ("lppos", ctypes.c_void_p)]


# DefWindowProcW 需要显式的 64 位签名（LPARAM 是指针宽度，默认 c_int 会溢出）
_DefWindowProcW = ctypes.windll.user32.DefWindowProcW
_DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
_DefWindowProcW.restype = ctypes.c_ssize_t


class GalleryWindow(QMainWindow):
    def __init__(self, ui_path, parent=None):
        super().__init__(parent)
        self.setObjectName("MainWindow")
        self.setAttribute(Qt.WA_DontCreateNativeAncestors, True)

        loadUi(ui_path, self)

        self._bg_light = QPixmap(os.path.join(GALLERY_DIR, "resources", "images", "bg3.png"))
        self._bg_dark = QPixmap(os.path.join(GALLERY_DIR, "resources", "images", "bg2.png"))
        self._widget_bg_mode = 0  # 0=无 1=图片 2=DWM blur

        self._title_bar = None
        self._chrome_header = None
        self._chrome_menu_bar = None
        self._frameless_initialized = False

        # 窗口激活态 -> chrome header 的 bar-active 属性（样式据此调标题栏底色）
        self.installEventFilter(self)

    # =========================================================================
    # 标题栏 / 菜单栏安装（对应 FluentWindowFrame::installChromeHeader）
    # =========================================================================
    def titleBar(self):
        return self._title_bar

    def chromeHeader(self):
        return self._chrome_header

    def installChromeHeader(self, menu_bar):
        self._chrome_menu_bar = menu_bar

        if self._title_bar is None:
            self._title_bar = FluentTitleBar(self)

        if self._chrome_header is None:
            from PyQt5.QtWidgets import QVBoxLayout
            self._chrome_header = QWidget(self)
            self._chrome_header.setObjectName("fluent-chrome-header")
            layout = QVBoxLayout(self._chrome_header)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            layout.addWidget(self._title_bar)
            if menu_bar is not None:
                layout.addWidget(menu_bar)

        self.setMenuWidget(self._chrome_header)
        self._chrome_header.show()
        self._title_bar.show()
        if self._chrome_menu_bar is not None:
            self._chrome_menu_bar.show()

    def hitTestWidgets(self):
        """标题栏内需要正常接收鼠标事件的控件（对应 setHitTestVisible）。"""
        if self._title_bar is None:
            return []
        widgets = [self._title_bar.searchLineEdit(), self._title_bar.themeButton(),
                   self._title_bar.pinButton(), self._title_bar.minButton(),
                   self._title_bar.maxButton(), self._title_bar.closeButton()]
        widgets += self._title_bar.accentButtons()
        if self._chrome_menu_bar is not None:
            widgets.append(self._chrome_menu_bar)
        return widgets

    # =========================================================================
    # 事件
    # =========================================================================
    def eventFilter(self, watched, event):
        if watched is self:
            if event.type() in (QEvent.WindowActivate, QEvent.WindowDeactivate):
                if self._chrome_header is not None:
                    self._chrome_header.setProperty("bar-active",
                                                    event.type() == QEvent.WindowActivate)
                    self.style().polish(self._chrome_header)
        return super().eventFilter(watched, event)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._frameless_initialized:
            self._frameless_initialized = True
            self._setup_frameless_native()

    def closeEvent(self, event):
        # 退出前停掉所有仍在运行的动画（时间轴脉冲/导航宽度动画等），
        # 避免销毁期间动画定时器继续触发已删除对象（表现为退出时鼠标忙圈）
        try:
            from PyQt5.QtCore import QVariantAnimation
            for anim in self.findChildren(QVariantAnimation):
                anim.stop()
        except Exception:  # noqa: BLE001
            pass
        super().closeEvent(event)

    def _setup_frameless_native(self):
        """窗口首次显示后的原生层微调（同 qwindowkit winIdChanged）。"""
        try:
            hwnd = int(self.winId())
            user32 = ctypes.windll.user32

            # 移除 WS_SYSMENU：材质（Mica/Acrylic）+ 透明标题栏时防止原生
            # 系统按钮图标透出；右键菜单由 _show_title_bar_system_menu 提供
            style = user32.GetWindowLongW(hwnd, GWL_STYLE)
            user32.SetWindowLongW(hwnd, GWL_STYLE, style & ~WS_SYSMENU)

            # Win11：显式启用系统圆角（标准窗口的默认行为；Win10/更早系统忽略）
            value = wt.DWORD(DWMWCP_ROUND)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                wt.HWND(hwnd), wt.DWORD(DWMWA_WINDOW_CORNER_PREFERENCE),
                ctypes.byref(value), ctypes.sizeof(value))

            # 触发一次边框重建，让上述修改立即生效
            user32.SetWindowPos(
                wt.HWND(hwnd), None, 0, 0, 0, 0,
                SWP_FRAMECHANGED | 0x0001 | 0x0002 | 0x0004 | 0x0010)  # NOMOVE|NOSIZE|NOZORDER|NOACTIVATE
        except Exception as e:  # noqa: BLE001
            print("无边框原生设置失败:", e)

    # =========================================================================
    # 背景模式（对应 MainWindow::paintEvent / applyWidgetBgMode）
    # =========================================================================
    def setWidgetBgMode(self, mode):
        self._widget_bg_mode = mode
        self._apply_system_backdrop(mode == 2)
        self.update()

    def widgetBgMode(self):
        return self._widget_bg_mode

    def _apply_system_backdrop(self, enabled):
        """DWM blur 模式：窗口转为透明 + 启用系统亚克力材质。"""
        try:
            hwnd = wt.HWND(int(self.winId()))
            value = wt.DWORD(DWMBT_TRANSIENTWINDOW if enabled else DWMBT_NONE)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, wt.DWORD(DWMWA_SYSTEMBACKDROP_TYPE),
                ctypes.byref(value), ctypes.sizeof(value))
        except Exception as e:  # noqa: BLE001
            print("设置 DWM backdrop 失败:", e)

        # WA_TranslucentBackground 需要在窗口重建后生效
        was_visible = self.isVisible()
        if was_visible:
            self.hide()
        self.setAttribute(Qt.WA_TranslucentBackground, enabled)
        if was_visible:
            self.show()
            # 窗口重建后重新应用无边框原生设置（WS_SYSMENU/圆角等）
            self._setup_frameless_native()

    def paintEvent(self, event):
        if self._widget_bg_mode == 0:
            super().paintEvent(event)
            return

        # DWM blur：什么都不画，让系统材质透出
        if self._widget_bg_mode == 2:
            return

        if self._bg_light.isNull() or self._bg_dark.isNull():
            super().paintEvent(event)
            return

        painter = QPainter(self)
        is_dark = self.app_property_colorscheme() == 1
        painter.drawPixmap(self.rect(), self._bg_dark if is_dark else self._bg_light)

    @staticmethod
    def app_property_colorscheme():
        from PyQt5.QtWidgets import QApplication
        return QApplication.instance().property("_q_colorscheme")

    # =========================================================================
    # 更新日志（对应 MainWindow::loadChangelog，填充右侧停靠窗口）
    # =========================================================================
    def loadChangelog(self):
        log = self.log
        log.clear()
        try:
            with open(os.path.join(GALLERY_DIR, "resources", "changelog.txt"), encoding="utf-8") as f:
                content = f.read()
            for line in content.split("\n"):
                log.append(line)
        except OSError as e:
            log.append(f"无法打开changelog.txt, {e}")
        log.moveCursor(QTextCursor.Start)

    # =========================================================================
    # 无边框（对应 qwindowkit WidgetWindowAgent 的最小实现）
    # =========================================================================
    def _frame_thickness(self):
        user32 = ctypes.windll.user32
        return (user32.GetSystemMetrics(SM_CXSIZEFRAME)
                + user32.GetSystemMetrics(SM_CXPADDEDBORDER))

    def nativeEvent(self, eventType, message):
        try:
            return self._native_event_impl(eventType, message)
        except Exception:  # noqa: BLE001
            # 窗口销毁过程中子控件可能已被删除，任何异常都不能向外抛
            # （否则会引发消息风暴，表现为退出时鼠标忙圈转个不停）
            try:
                return super().nativeEvent(eventType, message)
            except Exception:  # noqa: BLE001
                return False, 0

    def _native_event_impl(self, eventType, message):
        if eventType == b"windows_generic_MSG":
            try:
                msg = _MSG.from_address(int(message))
            except Exception:  # noqa: BLE001
                return super().nativeEvent(eventType, message)

            # 销毁链路上的消息直接跳过（同 qwindowkit windowProc 的前置过滤）
            if msg.message in (WM_DESTROY, WM_CLOSE, WM_NCDESTROY,
                               WM_UAHDESTROYWINDOW, WM_UNREGISTER_WINDOW_SERVICES):
                return super().nativeEvent(eventType, message)

            if msg.message == WM_NCCALCSIZE and msg.wParam:
                # qwindowkit 的做法：先让 DefWindowProc 计算默认边框（保留
                # L/R/B 系统边框 -> DWM 阴影、1px 边框与 Win11 圆角），
                # 再把整个顶部框架（标题栏+上边框）去掉
                params = _NCCALCSIZE_PARAMS.from_address(int(msg.lParam))
                rect = params.rgrc[0]
                original_top = rect.top

                default_result = _DefWindowProcW(
                    wt.HWND(int(msg.hwnd)), WM_NCCALCSIZE, msg.wParam, msg.lParam)
                if default_result != 0:
                    return True, default_result
                rect.top = original_top

                if self.isMaximized() and not self.isFullScreen():
                    # 最大化时窗口比工作区大一圈缩放边框，把顶部缩回工作区
                    rect.top += self._frame_thickness()
                return True, 0

            if msg.message == WM_NCHITTEST:
                result = self._hit_test(int(msg.lParam))
                if result is not None:
                    return True, result

            if msg.message == WM_NCRBUTTONUP and self._title_bar is not None:
                # WS_SYSMENU 已移除（mica 下防止原生按钮透出），
                # 右键标题栏时手动弹系统菜单（同 qwindowkit systemMenuHandler）
                if self._show_title_bar_system_menu(int(msg.lParam)):
                    return True, 0

        return super().nativeEvent(eventType, message)

    def _show_title_bar_system_menu(self, l_param):
        from PyQt5.QtWidgets import QMenu

        dpr = self.devicePixelRatioF() or 1.0
        x = ctypes.c_short(l_param & 0xFFFF).value
        y = ctypes.c_short((l_param >> 16) & 0xFFFF).value
        local = self.mapFromGlobal(QPoint(int(x / dpr), int(y / dpr)))
        bar_rect = QRect(self._title_bar.mapTo(self, QPoint(0, 0)), self._title_bar.size())
        if not bar_rect.contains(local):
            return False

        maximized = self.isMaximized()
        minimized = self.isMinimized()
        menu = QMenu(self)
        restore_action = menu.addAction("还原(R)")
        move_action = menu.addAction("移动(M)")
        size_action = menu.addAction("大小(S)")
        minimize_action = menu.addAction("最小化(N)")
        maximize_action = menu.addAction("最大化(X)")
        menu.addSeparator()
        close_action = menu.addAction("关闭(C)")

        restore_action.setEnabled(minimized or maximized)
        move_action.setEnabled(not minimized and not maximized)
        size_action.setEnabled(not minimized and not maximized)
        maximize_action.setEnabled(not minimized and not maximized)

        def exec_menu():
            chosen = menu.exec_(self.mapToGlobal(local))
            if chosen == restore_action:
                self.showNormal()
            elif chosen == minimize_action:
                self.showMinimized()
            elif chosen == maximize_action:
                self.showMaximized()
            elif chosen == close_action:
                self.close()

        QTimer.singleShot(0, exec_menu)
        return True

    def _hit_test(self, l_param):
        # lParam 为屏幕坐标（有符号 16 位打包，物理像素）；
        # Qt 的 mapFromGlobal / width / height 都是逻辑坐标，需按 DPR 换算
        dpr = self.devicePixelRatioF() or 1.0
        x = ctypes.c_short(l_param & 0xFFFF).value
        y = ctypes.c_short((l_param >> 16) & 0xFFFF).value
        local = self.mapFromGlobal(QPoint(int(x / dpr), int(y / dpr)))

        border = 0 if self.isMaximized() else int(self._frame_thickness() / dpr)
        width = self.width()
        height = self.height()

        if border > 0:
            on_left = local.x() < border
            on_right = local.x() >= width - border
            on_top = local.y() < border
            on_bottom = local.y() >= height - border
            if on_top and on_left:
                return HTTOPLEFT
            if on_top and on_right:
                return HTTOPRIGHT
            if on_bottom and on_left:
                return HTBOTTOMLEFT
            if on_bottom and on_right:
                return HTBOTTOMRIGHT
            if on_left:
                return HTLEFT
            if on_right:
                return HTRIGHT
            if on_top:
                return HTTOP
            if on_bottom:
                return HTBOTTOM

        # 标题栏背景 = 拖动区；标题栏里的交互控件 = 客户区
        if self._title_bar is not None:
            bar_rect = QRect(self._title_bar.mapTo(self, QPoint(0, 0)), self._title_bar.size())
            if bar_rect.contains(local):
                for widget in self.hitTestWidgets():
                    wr = QRect(widget.mapTo(self, QPoint(0, 0)), widget.size())
                    if wr.contains(local):
                        return None  # 交给 Qt 处理（HTCLIENT）
                # 命中标题栏空白区域或纯展示的图标/文字标签 -> 拖动
                child = self._title_bar.childAt(self._title_bar.mapFrom(self, local))
                if (child is None or child is self._title_bar
                        or child in (self._title_bar._icon_label, self._title_bar._title_label)):
                    return HTCAPTION
                return None  # 未知子控件，交给 Qt

        return None
