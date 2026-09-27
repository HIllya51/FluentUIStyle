"""纯 PyQt5 构建的运行时页面。

对应 C++ Gallery 在 mainwindow.cpp 里动态 addWidget 的页面：
- pageIcons     图标库（PageSegoeIconGallery 的 Model-View-Delegate 移植）
- pageAbout     关于（PageAbout）
- pageDialogs   对话框（PageDialog 的标准 Qt 部分）
- pageChangelog 更新日志（PageChangelog + 纯 Python ExTimeline）
- page_5 填充 Mdi 页（setupMdiArea 的移植）
"""

import os
import re

from PyQt5.QtCore import (
    QAbstractListModel,
    QDate,
    QDateTime,
    QModelIndex,
    QSize,
    QSortFilterProxyModel,
    Qt,
    QTimer,
)
from PyQt5.QtGui import QColor, QFont, QPainter, QPalette
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QFontDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListView,
    QMdiArea,
    QMdiSubWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStyledItemDelegate,
    QStyle,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from exwidgets import ExMessageBox, ExTimeline, ExTimelineEvent
from gallerywindow import GALLERY_DIR


# =============================================================================
# 通用小部件
# =============================================================================

def make_page(stacked, object_name):
    page = QWidget()
    page.setObjectName(object_name)
    stacked.addWidget(page)
    return page


def create_card(parent=None):
    """WinUI3 卡片容器（isCard 属性由 FluentUI3Style 绘制卡片底色）。"""
    card = QWidget(parent)
    card.setProperty("isCard", True)
    card.setAttribute(Qt.WA_StyledBackground)
    layout = QVBoxLayout(card)
    layout.setSpacing(10)
    layout.setContentsMargins(10, 10, 10, 10)
    return card, layout


def wrap_in_scroll(parent_layout, frame_shape=QFrame.NoFrame, margin=16):
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(frame_shape)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroll.viewport().setAutoFillBackground(False)
    content = QWidget(scroll)
    content.setAutoFillBackground(False)
    scroll.setWidget(content)
    parent_layout.addWidget(scroll)
    content_layout = QVBoxLayout(content)
    content_layout.setContentsMargins(margin, margin, margin, margin)
    content_layout.setSpacing(16)
    return content_layout


def add_section_title(layout, title, desc="", point_size=18):
    t_label = QLabel(title)
    tf = t_label.font()
    tf.setBold(True)
    tf.setPointSize(point_size)
    t_label.setFont(tf)
    layout.addWidget(t_label)
    if desc:
        d_label = QLabel(desc)
        d_label.setWordWrap(True)
        layout.addWidget(d_label)
    return t_label


# =============================================================================
# 图标库页（PageSegoeIconGallery 的 Model-View-Delegate 移植）
# =============================================================================

_ICON_LINE_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*0x([0-9A-Fa-f]+)\s*,?\s*$")


def load_icon_entries():
    """解析 SegoeFluentIconsEnum.txt -> [(name, codepoint), ...]。"""
    entries = []
    path = os.path.join(GALLERY_DIR, "font-icon", "resource", "SegoeFluentIconsEnum.txt")
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                m = _ICON_LINE_RE.match(line)
                if m:
                    entries.append((m.group(1), int(m.group(2), 16)))
    except OSError as e:
        print("无法读取图标枚举文件:", e)
    return entries


class SegoeIconModel(QAbstractListModel):
    NameRole = Qt.UserRole + 1
    CodeRole = Qt.UserRole + 2
    CodeTextRole = Qt.UserRole + 3
    SearchRole = Qt.UserRole + 4

    def __init__(self, entries, parent=None):
        super().__init__(parent)
        self._entries = entries

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._entries)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row = index.row()
        if not 0 <= row < len(self._entries):
            return None
        name, code = self._entries[row]
        if role in (Qt.DisplayRole, self.NameRole):
            return name
        if role == self.CodeRole:
            return code
        if role == self.CodeTextRole:
            return "0x%04X" % code
        if role == self.SearchRole:
            return "%s 0x%x" % (name, code)
        if role == Qt.ToolTipRole:
            return "%s\n0x%04X\n点击复制编码" % (name, code)
        return None


class SegoeIconDelegate(QStyledItemDelegate):
    """高性能轻量化卡片绘制委托：直接用字体绘制图标，不生成 QPixmap。"""

    def sizeHint(self, option, index):
        return QSize(114, 104)

    def paint(self, painter, option, index):
        from PyQt5.QtCore import QRect
        if not index.isValid():
            return
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        rect = option.rect.adjusted(3, 3, -3, -3)
        is_dark = option.palette.color(QPalette.Base).lightness() < 128
        is_hover = bool(option.state & QStyle.State_MouseOver)
        is_pressed = bool(option.state & QStyle.State_Sunken)

        # 悬停与按下态高亮圆角底色
        if is_hover or is_pressed:
            bg_color = QColor(255, 255, 255) if is_dark else QColor(0, 0, 0)
            bg_color.setAlpha(24 if is_pressed else 12)
            painter.setBrush(bg_color)
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(rect, 6.0, 6.0)

        name = index.data(SegoeIconModel.NameRole)
        code = index.data(SegoeIconModel.CodeRole)
        code_text = index.data(SegoeIconModel.CodeTextRole)

        # 1. Segoe Fluent Icons 图标字体
        icon_font = QFont("Segoe Fluent Icons")
        icon_font.setPixelSize(30)
        icon_font.setHintingPreference(QFont.PreferNoHinting)
        painter.setFont(icon_font)
        painter.setPen(QColor(255, 255, 255) if is_dark else QColor(26, 26, 26))
        icon_rect = QRect(rect.left(), rect.top() + 6, rect.width(), 36)
        painter.drawText(icon_rect, Qt.AlignCenter, chr(code))

        # 2. 图标名称
        name_font = QFont(option.font)
        name_font.setPixelSize(11)
        painter.setFont(name_font)
        painter.setPen(QColor(230, 230, 230) if is_dark else QColor(32, 32, 32))
        name_rect = QRect(rect.left() + 4, icon_rect.bottom() + 4, rect.width() - 8, 30)
        painter.drawText(name_rect, Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap, name)

        # 3. 16 进制编码
        code_font = QFont(name_font)
        code_font.setPixelSize(10)
        painter.setFont(code_font)
        sub_color = QColor(option.palette.color(QPalette.WindowText))
        sub_color.setAlpha(160 if is_dark else 130)
        painter.setPen(sub_color)
        code_rect = QRect(rect.left() + 4, rect.bottom() - 16, rect.width() - 8, 15)
        painter.drawText(code_rect, Qt.AlignHCenter | Qt.AlignBottom, code_text)

        painter.restore()


def setup_icons_page(window):
    stacked = window.stackedWidget
    page = make_page(stacked, "pageIcons")

    layout = QVBoxLayout(page)
    layout.setContentsMargins(11, 11, 11, 11)
    layout.setSpacing(10)

    add_section_title(layout, "Segoe Fluent Icons 图标库",
                      "点击图标复制 0x 编码；Python 中可用 chr(0xE8FB) 或 '\\ue8fb' 使用")

    top_bar = QHBoxLayout()
    search_edit = QLineEdit()
    search_edit.setPlaceholderText("输入名称或编码筛选")
    search_edit.setClearButtonEnabled(True)
    search_edit.setFixedWidth(240)
    hint_label = QLabel("共 0 个图标")
    top_bar.addWidget(search_edit)
    top_bar.addStretch(1)
    top_bar.addWidget(hint_label)
    layout.addLayout(top_bar)

    model = SegoeIconModel(load_icon_entries())
    hint_label.setText(f"共 {model.rowCount()} 个图标")

    proxy_model = QSortFilterProxyModel(page)
    proxy_model.setSourceModel(model)
    proxy_model.setFilterRole(SegoeIconModel.SearchRole)
    proxy_model.setFilterCaseSensitivity(Qt.CaseInsensitive)

    list_view = QListView(page)
    list_view.setViewMode(QListView.IconMode)
    list_view.setResizeMode(QListView.Adjust)
    list_view.setUniformItemSizes(True)
    list_view.setMovement(QListView.Static)
    list_view.setSpacing(4)
    list_view.setGridSize(QSize(114, 104))
    list_view.setSelectionMode(QAbstractItemView.NoSelection)
    list_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
    list_view.setFrameShape(QFrame.NoFrame)
    list_view.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
    list_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    list_view.setWordWrap(True)
    list_view.setMouseTracking(True)
    list_view.setItemDelegate(SegoeIconDelegate(list_view))
    list_view.setModel(proxy_model)
    layout.addWidget(list_view, 1)

    # 搜索实时联动
    search_edit.textChanged.connect(proxy_model.setFilterFixedString)

    # 点击复制到剪贴板并在状态栏提示（C++ 版为 ExInfoBar 通知）
    def on_clicked(index):
        if not index.isValid():
            return
        name = index.data(SegoeIconModel.NameRole)
        code = index.data(SegoeIconModel.CodeTextRole)
        QApplication.clipboard().setText(code)
        window.statusBar().showMessage(f"已复制到剪贴板 - 图标: {name}   编码: {code}", 2000)

    list_view.clicked.connect(on_clicked)
    return page


# =============================================================================
# 关于页（PageAbout 移植）
# =============================================================================

def setup_about_page(window):
    stacked = window.stackedWidget
    page = make_page(stacked, "pageAbout")

    layout = QVBoxLayout(page)
    layout.setContentsMargins(11, 11, 11, 11)
    layout.setSpacing(15)
    content_layout = wrap_in_scroll(page.layout(), margin=11)
    content_layout.setSpacing(15)

    card, card_layout = create_card()
    card.setObjectName("aboutCard")
    card_layout.setContentsMargins(9, 9, 9, 9)

    title_label = QLabel("关于项目")
    title_label.setObjectName("aboutTitle")
    title_font = title_label.font()
    title_font.setPointSize(18)
    title_font.setBold(True)
    title_label.setFont(title_font)

    subtitle_label = QLabel("FluentUI3Style · Qt FluentUI (WinUI3) 风格实现 · PyQt5 Gallery")
    subtitle_label.setObjectName("aboutSubtitle")
    subtitle_palette = subtitle_label.palette()
    subtitle_palette.setColor(QPalette.WindowText, subtitle_palette.color(QPalette.Mid))
    subtitle_label.setPalette(subtitle_palette)

    from PyQt5.QtCore import PYQT_VERSION_STR, QT_VERSION_STR
    import sys

    content_label = QLabel(card)
    content_label.setObjectName("aboutProjectContent")
    content_label.setWordWrap(True)
    content_label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
    content_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
    content_label.setOpenExternalLinks(True)
    content_font = content_label.font()
    content_font.setPointSize(11)
    content_label.setFont(content_font)
    content_label.setTextFormat(Qt.RichText)
    content_label.setText(
        "<p>本项目定位为样式库，目标是将 Qt 现有控件呈现为 FluentUI（WinUI3）风格。</p>"
        "<p>由于 Qt 组件边界限制，部分 FluentUI 控件无法完全复刻；但会尽量基于现有控件，"
        "通过 Style 中的定制逻辑实现接近 FluentUI 的交互与视觉效果，例如：</p>"
        "<ul>"
        "<li>SwitchButton</li>"
        "<li>TabBar 实现 \"Pivot\" 和 \"Segmented\" 控件</li>"
        "</ul>"
        "<p>本示例为纯 PyQt5 移植版：使用 Qt5 构建的 FluentUI3StylePlugin.dll，"
        "通过 QApplication.setStyle(\"FluentUI3\") 加载，界面布局复用 C++ Gallery 的 mainwindow.ui。</p>"
        f"<p>运行环境：Python {sys.version.split()[0]} · PyQt5 {PYQT_VERSION_STR} · Qt {QT_VERSION_STR}</p>"
        "<p>项目主页：<a href=\"https://github.com/HIllya51/FluentUIStyle\">"
        "https://github.com/HIllya51/FluentUIStyle</a></p>"
    )

    card_layout.addWidget(title_label)
    card_layout.addWidget(subtitle_label)
    card_layout.addWidget(content_label, 1)
    content_layout.addWidget(card, 1)
    content_layout.addStretch()
    return page


# =============================================================================
# 对话框页（PageDialog 移植，仅标准 Qt 对话框部分）
# =============================================================================

def setup_dialogs_page(window):
    stacked = window.stackedWidget
    page = make_page(stacked, "pageDialogs")
    page.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    root = QVBoxLayout(page)
    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(0)
    content_layout = wrap_in_scroll(root)

    add_section_title(content_layout, "常用对话框（Qt Widgets）",
                      "以下按钮会弹出模态或非模态对话框，用于在 Fluent 样式下查看常见 Qt 对话框外观。",
                      point_size=16)

    def status(msg):
        window.statusBar().showMessage(str(msg), 3000)

    def add_card_section(section_title):
        card, v = create_card()
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(10)
        content_layout.addWidget(card)
        title = QLabel(section_title, card)
        tf = title.font()
        tf.setBold(True)
        tf.setPixelSize(14)
        title.setFont(tf)
        v.addWidget(title)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addStretch(0)
        v.addLayout(row)
        return row

    def add_buttons(row, buttons):
        for b in buttons:
            row.insertWidget(row.count() - 1, b)

    # --- 消息框 (ExMessageBox，WinUI3 ContentDialog) ---
    row_msg = add_card_section("消息框 (ExMessageBox)")
    btn_info = QPushButton("信息")
    btn_info.clicked.connect(lambda: ExMessageBox.information(window, "信息", "这是一条信息消息。"))
    btn_warn = QPushButton("警告")
    btn_warn.clicked.connect(lambda: ExMessageBox.warning(window, "警告", "这是一条警告消息。"))
    btn_crit = QPushButton("严重")
    btn_crit.clicked.connect(lambda: ExMessageBox.critical(window, "严重", "这是一条严重错误消息。"))
    btn_quest = QPushButton("询问")
    btn_quest.clicked.connect(lambda: status(
        "询问结果: " + ("Yes" if ExMessageBox.question(window, "询问", "是否继续？") == QMessageBox.Yes else "No")))
    btn_save_prompt = QPushButton("是否保存文件…")

    def ask_save():
        ret = ExMessageBox.question(window, "保存文件", "文档已修改，是否在关闭前保存？",
                                    QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                                    QMessageBox.Save)
        names = {QMessageBox.Save: "保存", QMessageBox.Discard: "放弃", QMessageBox.Cancel: "取消"}
        status("保存询问结果: " + names.get(ret, str(ret)))
    btn_save_prompt.clicked.connect(ask_save)

    btn_detail_info = QPushButton("详细信息")

    def show_detail():
        box = ExMessageBox(QMessageBox.Information, "操作结果", "文件已成功导出。", QMessageBox.Ok, window)
        box.setInformativeText("该文件保存在以下路径:\nC:\\Users\\Public\\Documents\\Report.pdf")
        box.exec_()
    btn_detail_info.clicked.connect(show_detail)

    btn_check_box = QPushButton("复选框")

    def show_checkbox():
        box = ExMessageBox(QMessageBox.Warning, "安全警告", "您即将执行一个危险操作。",
                           QMessageBox.Yes | QMessageBox.No, window)
        box.setInformativeText("继续执行可能会导致数据丢失。")
        cb = QCheckBox("不再提醒我")
        box.setCheckBox(cb)
        ret = box.exec_()
        status("复选框结果: %s, 勾选: %s" % ("Yes" if ret == QMessageBox.Yes else "No", cb.isChecked()))
    btn_check_box.clicked.connect(show_checkbox)

    btn_password = QPushButton("密码输入")

    def ask_password():
        # 对应 C++ ExMessageBox::setContentWidget：在消息框内嵌一个密码输入框
        box = ExMessageBox(QMessageBox.Information, "验证身份", "请输入管理员密码以继续操作。",
                           QMessageBox.Ok | QMessageBox.Cancel, window)
        line_edit = QLineEdit(box)
        line_edit.setEchoMode(QLineEdit.Password)
        line_edit.setPlaceholderText("输入密码")
        box.setContentWidget(line_edit)
        ret = box.exec_()
        if ret == QMessageBox.Ok:
            status("密码输入: " + "*" * len(line_edit.text()))
    btn_password.clicked.connect(ask_password)

    add_buttons(row_msg, [btn_info, btn_warn, btn_crit, btn_quest,
                          btn_save_prompt, btn_detail_info, btn_check_box, btn_password])

    # --- 输入框 (QInputDialog) ---
    row_in = add_card_section("输入框 (QInputDialog)")
    btn_text = QPushButton("单行文本")
    btn_text.clicked.connect(lambda: QInputDialog.getText(
        window, "输入文本", "请输入内容：", QLineEdit.Normal, "示例"))
    btn_int = QPushButton("整数")
    btn_int.clicked.connect(lambda: QInputDialog.getInt(
        window, "输入整数", "数值：", 42, -1000, 1000, 1))
    btn_double = QPushButton("浮点数")
    btn_double.clicked.connect(lambda: QInputDialog.getDouble(
        window, "输入浮点数", "数值：", 3.14, -1000.0, 1000.0, 2))
    btn_item = QPushButton("列表选择")
    btn_item.clicked.connect(lambda: QInputDialog.getItem(
        window, "选择一项", "请选择：", ["选项 A", "选项 B", "选项 C"], 0, False))
    btn_multi = QPushButton("多行文本")
    btn_multi.clicked.connect(lambda: QInputDialog.getMultiLineText(
        window, "多行输入", "内容：", "第一行\n第二行"))
    add_buttons(row_in, [btn_text, btn_int, btn_double, btn_item, btn_multi])

    # --- 颜色与字体 ---
    row_pick = add_card_section("颜色与字体")
    btn_color = QPushButton("选择颜色…")
    btn_color.clicked.connect(lambda: QColorDialog.getColor(
        QColor(0, 0, 255), window, "选择颜色"))
    btn_font = QPushButton("选择字体…")

    def pick_font():
        font, ok = QFontDialog.getFont(window.font(), window, "选择字体")
        if ok:
            status("选择的字体: %s" % font.family())
    btn_font.clicked.connect(pick_font)
    add_buttons(row_pick, [btn_color, btn_font])

    # --- 进度对话框 (QProgressDialog) ---
    row_prog = add_card_section("进度对话框 (QProgressDialog)")
    btn_prog = QPushButton("短时进度…")

    def run_short_progress():
        dlg = QProgressDialog("正在处理…", "取消", 0, 100, window)
        dlg.setWindowTitle("进度")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setValue(0)
        state = {"value": 0}

        def step():
            if dlg.wasCanceled():
                return
            state["value"] += 5
            dlg.setValue(state["value"])
            if state["value"] < 100:
                QTimer.singleShot(40, step)
            else:
                status("短时进度: 完成")
        QTimer.singleShot(40, step)
    btn_prog.clicked.connect(run_short_progress)
    add_buttons(row_prog, [btn_prog])

    # --- 自定义对话框 (QDialog + QDialogButtonBox) ---
    row_custom = add_card_section("自定义对话框 (QDialog + QDialogButtonBox)")
    btn_custom = QPushButton("打开示例对话框…")

    def open_custom_dialog():
        dlg = QDialog(window)
        dlg.setWindowTitle("示例对话框")
        v = QVBoxLayout(dlg)
        v.addWidget(QLabel("这是一个带 QDialogButtonBox 的简单对话框。", dlg))
        bbox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, dlg)
        bbox.accepted.connect(dlg.accept)
        bbox.rejected.connect(dlg.reject)
        v.addWidget(bbox)
        dlg.resize(420, 140)
        dlg.exec_()
    btn_custom.clicked.connect(open_custom_dialog)
    add_buttons(row_custom, [btn_custom])

    content_layout.addStretch()
    return page


# =============================================================================
# 更新日志页（PageChangelog + 纯 Python ExTimeline）
# =============================================================================

_HEADER_RE = re.compile(r"^【更新内容(\d{4})-(\d{1,2})-(\d{1,2})】$")
_ITEM_PREFIX_RE = re.compile(r"^\s*\d+[\.、]?\s*")


def load_changelog_entries():
    """解析 changelog.txt -> [(QDate, title, description), ...]（同 C++ loadChangelogEntries）。"""
    entries = []
    path = os.path.join(GALLERY_DIR, "resources", "changelog.txt")
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().split("\n")
    except OSError:
        return entries

    current_date = None
    changes = []

    def append_entry():
        if current_date is None or not changes:
            return
        normalized = []
        for change in changes:
            stripped = _ITEM_PREFIX_RE.sub("", change)
            if stripped.strip():
                normalized.append(stripped)
        if not normalized:
            return
        title = normalized.pop(0)
        description = "\n".join("• " + c for c in normalized)
        entries.append((current_date, title, description))

    for line in lines:
        line = line.strip()
        match = _HEADER_RE.match(line)
        if match:
            append_entry()
            current_date = QDate(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            changes = []
        elif current_date is not None and line:
            changes.append(line)
    append_entry()
    return entries


def setup_changelog_page(window):
    stacked = window.stackedWidget
    page = make_page(stacked, "pageChangelog")

    layout = QVBoxLayout(page)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(10)

    title = QLabel("更新日志")
    title_font = title.font()
    title_font.setPointSize(16)
    title_font.setBold(True)
    title.setFont(title_font)
    layout.addWidget(title)

    description = QLabel("按时间轴展示项目的主要更新。")
    description.setProperty("isSecondaryText", True)
    layout.addWidget(description)

    card, card_layout = create_card(page)
    card_layout.setContentsMargins(16, 16, 16, 16)

    scroll = QScrollArea(card)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.viewport().setAutoFillBackground(False)
    timeline = ExTimeline(scroll)
    timeline.setObjectName("changelogTimeline")
    timeline.setTimestampFormat("yyyy-MM-dd")
    timeline.setTimestampWidth(100)
    scroll.setWidget(timeline)

    entries = load_changelog_entries()
    for index, (timestamp, entry_title, entry_description) in enumerate(entries):
        timeline.addEvent(timestamp, entry_title, entry_description,
                          ExTimelineEvent.CURRENT if index == 0 else ExTimelineEvent.COMPLETED)
    if not entries:
        timeline.addEvent(QDateTime(), "无法读取 changelog.txt",
                          "请检查 Gallery 资源文件配置。", ExTimelineEvent.ERROR)

    card_layout.addWidget(scroll)
    layout.addWidget(card, 1)
    return page


# =============================================================================
# Mdi 页（setupMdiArea 移植，填充 .ui 中预留的 page_5）
# =============================================================================

def setup_mdi_page(window):
    page = window.page_5

    mdi_area = QMdiArea(page)
    mdi_area.setViewMode(QMdiArea.SubWindowView)
    mdi_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    mdi_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

    # 添加子窗口
    for i in range(3):
        sub_window = QMdiSubWindow()
        sub_window.setWidget(QTextEdit())
        sub_window.setAttribute(Qt.WA_DeleteOnClose)
        sub_window.setWindowTitle("子窗口 %d" % (i + 1))
        mdi_area.addSubWindow(sub_window)
        sub_window.show()

    # 视图模式切换按钮
    switch_view_btn = QPushButton("切换视图模式", page)
    switch_view_btn.clicked.connect(
        lambda: mdi_area.setViewMode(
            QMdiArea.TabbedView
            if mdi_area.viewMode() == QMdiArea.SubWindowView
            else QMdiArea.SubWindowView
        )
    )

    layout = QVBoxLayout(page)
    layout.addWidget(switch_view_btn)
    layout.addWidget(mdi_area)
