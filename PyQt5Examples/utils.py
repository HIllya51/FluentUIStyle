import winreg

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QIcon, QPainter, QPixmap
from PyQt5.QtWidgets import QApplication


def create_fluent_icon(icon_code, color=None):
    """用 Segoe Fluent Icons 字体绘制一张 30x30 图标。

    color 为 None 时按主题取黑/白（工具栏、菜单等）；传调色板颜色时
    按该颜色绘制（导航树项图标，随调色板自动刷新）。
    样式插件构造时已把内嵌的 Segoe Fluent Icons 字体注册进 QFontDatabase，
    因此即使系统未安装该字体，setStyle("FluentUI3") 之后也能按字体名取到。
    """
    pixmap = QPixmap(30, 30)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform)
    font = QFont("Segoe Fluent Icons")
    font.setPixelSize(25)
    painter.setFont(font)
    if color is not None and color.isValid():
        pen_color = color
    else:
        is_dark = QApplication.instance().property("_q_colorscheme") == 1
        pen_color = Qt.white if is_dark else Qt.black
    painter.setPen(pen_color)
    painter.drawText(pixmap.rect(), Qt.AlignCenter, icon_code)
    painter.end()
    return QIcon(pixmap)


def is_system_dark_theme():
    """Qt5 没有 QStyleHints::colorScheme，读注册表判断系统深浅色主题。"""
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            return winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
    except OSError:
        return False


def apply_dwm_dark_titlebar(window, dark):
    """用 DWMWA_USE_IMMERSIVE_DARK_MODE(20) 让原生标题栏跟随应用主题。

    需要在窗口已创建平台窗口（show 之后或 winId() 被调用后）才生效。
    """
    try:
        import ctypes
        import ctypes.wintypes

        window.windowHandle()  # 确保平台窗口存在
        hwnd = int(window.windowHandle().winId())
        value = ctypes.c_int(1 if dark else 0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            ctypes.wintypes.HWND(hwnd),
            ctypes.wintypes.DWORD(20),
            ctypes.byref(value),
            ctypes.sizeof(value),
        )
    except Exception as e:  # noqa: BLE001 - 非关键路径，失败只提示
        print("无法切换原生标题栏深色模式:", e)


def query_installed_software():
    """枚举注册表中的已安装软件，供表格页展示（同 C++ PageInstalledSoftware）。"""
    software_list = []
    dedupe_keys = set()

    def append_registry(hive, subkey_path, source_label):
        try:
            key = winreg.OpenKey(hive, subkey_path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
        except OSError:
            return
        num_subkeys = winreg.QueryInfoKey(key)[0]
        for i in range(num_subkeys):
            try:
                subkey_name = winreg.EnumKey(key, i)
                with winreg.OpenKey(key, subkey_name) as subkey:
                    def get_val(name, default=""):
                        try:
                            return str(winreg.QueryValueEx(subkey, name)[0]).strip()
                        except OSError:
                            return default
                    display_name = get_val("DisplayName")
                    if not display_name: continue
                    try:
                        system_comp = winreg.QueryValueEx(subkey, "SystemComponent")[0]
                        if system_comp == 1: continue
                    except OSError:
                        pass
                    if get_val("ParentKeyName"): continue
                    release_type = get_val("ReleaseType").lower()
                    if "update" in release_type or "hotfix" in release_type: continue
                    version = get_val("DisplayVersion", "-")
                    publisher = get_val("Publisher", "-")
                    install_date = get_val("InstallDate", "-")
                    if len(install_date) == 8 and install_date.isdigit():
                        install_date = f"{install_date[:4]}-{install_date[4:6]}-{install_date[6:]}"
                    dedupe_key = f"{display_name}|{version}|{publisher}"
                    if dedupe_key in dedupe_keys: continue
                    dedupe_keys.add(dedupe_key)
                    software_list.append((display_name, version, publisher, install_date, source_label))
            except OSError:
                continue

    append_registry(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", "HKLM 64-bit")
    append_registry(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall", "HKLM 32-bit")
    append_registry(winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", "HKCU")
    software_list.sort(key=lambda x: x[0].lower())
    return software_list
