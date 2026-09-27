"""设置页构建（对应 C++ MainWindow::setupSettingsPage）。

把 Designer 里平铺的 radio 组重排为 WinUI3 风格的设置卡片：
图标 + 标题/描述 + 右侧组合框；RadioButton 继续作为状态桥接层但不再显示。
"""

import os

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QIcon, QPalette
from PyQt5.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListView,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from exwidgets import ExExpander
from gallerywindow import GALLERY_DIR

# SegoeIcon 码点
ICON_COLOR = "\ue790"
ICON_GLOBE = "\ue774"
ICON_PICTURE = "\ue8b9"
ICON_TASK_VIEW = "\ue7c4"
ICON_SETTINGS_DISPLAY_SOUND = "\ue7f3"
ICON_CHEVRON_RIGHT = "\ue76c"


def build_settings_page(window, on_about_clicked=None):
    """重建 pageSetting。on_about_clicked: 关于卡片的跳转回调。"""

    def remove_from_designer_layout():
        """把 Designer 布局中的旧控件取出来（radio 桥接层保留但隐藏）。"""
        sections = [
            (window.label_20, window.widgetColorSheme, None,
             [window.rBLightTheme, window.rBDarkTheme]),
            (window.labelUiLanguage, window.widgetUiLanguage, None,
             [window.rBLangZh_CN, window.rBLangEn_US, window.rBLangSystem]),
            (window.label_21, window.widgetWidgetMode, window.verticalLayout_2,
             [window.rBWidgtModeNormal, window.rBWidgetModePixmap, window.rBWidgetModeDwmBlur]),
            (window.label_22, window.widgetNavMode, window.verticalLayout_3,
             [window.rBOnlyIcon, window.rBIconAndText]),
            # 强调色内部是动态创建的按钮网格，仍作为一个完整内容
            (window.label_19, window.widgetAccentColor, window.verticalLayout, []),
        ]

        grid = window.gridLayout_29
        for label, content, nested_layout, rows in sections:
            if nested_layout is not None:
                nested_layout.removeWidget(label)
                nested_layout.removeWidget(content)
                grid.removeItem(nested_layout)
            else:
                grid.removeWidget(label)
                grid.removeWidget(content)
            label.hide()
            content.setProperty("isCard", None)
            content.setAttribute(Qt.WA_StyledBackground, False)
            if rows:
                content.hide()
            elif content.layout() is not None:
                content.layout().setContentsMargins(0, 0, 0, 0)

        if getattr(window, "verticalSpacer", None) is not None:
            grid.removeItem(window.verticalSpacer)
        grid.setContentsMargins(48, 32, 48, 40)
        grid.setHorizontalSpacing(0)
        grid.setVerticalSpacing(8)

        window.scrollArea.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        window.scrollAreaWidgetContents.setAutoFillBackground(False)

    remove_from_designer_layout()

    parent = window.scrollAreaWidgetContents

    # ---- 构建辅助 ----
    def make_text_block(title, description):
        text_widget = QWidget(parent)
        text_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        text_layout = QVBoxLayout(text_widget)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(1)

        title_label = QLabel(title, text_widget)
        title_label.setObjectName("settingsCardTitle")
        title_font = title_label.font()
        title_font.setPixelSize(15)
        title_label.setFont(title_font)
        text_layout.addWidget(title_label)

        if description:
            description_label = QLabel(description, text_widget)
            description_label.setObjectName("settingsCardDescription")
            description_palette = description_label.palette()
            description_palette.setColor(QPalette.WindowText,
                                         description_palette.color(QPalette.Mid))
            description_label.setPalette(description_palette)
            description_label.setWordWrap(True)
            text_layout.addWidget(description_label)
        return text_widget

    def make_icon_label(icon_code):
        icon_label = QLabel(parent)
        icon_font = QFont("Segoe Fluent Icons")
        icon_font.setPixelSize(22)
        icon_label.setFont(icon_font)
        icon_label.setText(icon_code)
        icon_label.setObjectName("settingsCardIcon")
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setFixedWidth(36)
        return icon_label

    def make_card_contents(icon_code, title, description, trailing, container):
        contents = QWidget(container)
        layout = QHBoxLayout(contents)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(14)
        layout.addWidget(make_icon_label(icon_code))
        layout.addWidget(make_text_block(title, description), 1)
        if trailing is not None:
            layout.addSpacing(16)
            layout.addWidget(trailing, 0, Qt.AlignVCenter)
        return contents

    def make_card(object_name, icon_code, title, description, trailing):
        card = make_card_contents(icon_code, title, description, trailing, parent)
        card.setObjectName(object_name)
        card.setAttribute(Qt.WA_StyledBackground)
        card.setProperty("isCard", True)
        card.setMinimumHeight(72)
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        return card

    def make_combo(object_name, items):
        combo = QComboBox(parent)
        combo.setObjectName(object_name)
        combo.addItems(items)
        combo.setMinimumWidth(170)
        combo.setMinimumHeight(32)
        combo.setView(QListView(combo))
        return combo

    def bind_combo_to_buttons(combo, buttons):
        initial_index = 0
        for index, button in enumerate(buttons):
            if button.isChecked():
                initial_index = index

            def on_toggled(checked, _index=index, _combo=combo):
                if checked and _combo.currentIndex() != _index:
                    _combo.blockSignals(True)
                    _combo.setCurrentIndex(_index)
                    _combo.blockSignals(False)

            button.toggled.connect(on_toggled)

        combo.setCurrentIndex(initial_index)

        def on_current_index_changed(index, _buttons=buttons):
            if 0 <= index < len(_buttons) and not _buttons[index].isChecked():
                _buttons[index].click()

        combo.currentIndexChanged.connect(on_current_index_changed)

    page_title = QLabel("设置", parent)
    page_title_font = page_title.font()
    page_title_font.setPixelSize(28)
    page_title_font.setBold(True)
    page_title.setFont(page_title_font)

    def make_section_title(text):
        label = QLabel(text, parent)
        font = label.font()
        font.setPixelSize(14)
        font.setBold(True)
        label.setFont(font)
        return label

    # ---- 各设置卡片 ----
    theme_combo = make_combo("settingsThemeCombo", ["浅色", "暗色"])
    bind_combo_to_buttons(theme_combo, [window.rBLightTheme, window.rBDarkTheme])

    background_combo = make_combo("settingsBackgroundCombo", ["正常", "图片", "DWM blur"])
    bind_combo_to_buttons(background_combo,
                          [window.rBWidgtModeNormal, window.rBWidgetModePixmap, window.rBWidgetModeDwmBlur])

    navigation_combo = make_combo("settingsNavigationCombo", ["仅图标", "图标和文本"])
    bind_combo_to_buttons(navigation_combo, [window.rBOnlyIcon, window.rBIconAndText])

    appearance_title = make_section_title("外观和行为")
    theme_card = make_card("settingsThemeCard", ICON_COLOR, "应用主题", "选择应用显示的主题", theme_combo)
    background_card = make_card("settingsBackgroundCard", ICON_PICTURE, "窗口背景",
                                "选择内容区域的背景效果", background_combo)
    navigation_card = make_card("settingsNavigationCard", ICON_TASK_VIEW, "导航样式",
                                "选择导航栏的显示方式", navigation_combo)

    # 强调色折叠面板
    accent_expander = ExExpander(parent)
    accent_expander.setObjectName("settingsAccentExpander")
    accent_header = make_card_contents(ICON_SETTINGS_DISPLAY_SOUND, "强调色",
                                       "选择控件使用的系统强调色", None, accent_expander)
    # 同 C++：HeaderButton 自带 16px 左内边距与 chevron 预留区，内容只留上下边距
    accent_header.layout().setContentsMargins(0, 12, 0, 12)
    accent_expander.setHeaderWidget(accent_header)
    accent_expander.addContentWidget(window.widgetAccentColor)
    accent_expander.setExpanded(False)

    # 关于卡片
    about_title = make_section_title("关于")
    about_button = QToolButton(parent)
    chevron_font = QFont("Segoe Fluent Icons")
    chevron_font.setPixelSize(16)
    about_button.setFont(chevron_font)
    about_button.setText(ICON_CHEVRON_RIGHT)
    about_button.setToolTip("查看项目信息")
    about_button.setAutoRaise(True)
    about_button.setFixedSize(36, 36)
    if on_about_clicked is not None:
        about_button.clicked.connect(lambda: on_about_clicked())

    version_label = QLabel("v0.1", parent)
    version_palette = version_label.palette()
    version_palette.setColor(QPalette.WindowText, version_palette.color(QPalette.Mid))
    version_label.setPalette(version_palette)

    about_trailing = QWidget(parent)
    about_trailing_layout = QHBoxLayout(about_trailing)
    about_trailing_layout.setContentsMargins(0, 0, 0, 0)
    about_trailing_layout.setSpacing(8)
    about_trailing_layout.addWidget(version_label)
    about_trailing_layout.addWidget(about_button)

    about_card = make_card("settingsAboutCard", "", "FluentUI3 Gallery",
                           "FluentUI3 Style 与扩展控件示例程序", about_trailing)
    about_icon = about_card.findChild(QLabel, "settingsCardIcon")
    if about_icon is not None:
        about_icon.setText("")
        about_icon.setPixmap(QIcon(os.path.join(GALLERY_DIR, "resources", "appicon.ico")).pixmap(24, 24))

    # ---- 排版 ----
    grid = window.gridLayout_29
    row = 0
    grid.addWidget(page_title, row, 0); row += 1
    grid.setRowMinimumHeight(row, 22); row += 1
    grid.addWidget(appearance_title, row, 0); row += 1
    grid.addWidget(theme_card, row, 0); row += 1
    # 无 i18n 支持，隐藏语言卡片（同 C++ 非 GALLERY_ENABLE_I18N 构建）
    grid.addWidget(background_card, row, 0); row += 1
    grid.addWidget(navigation_card, row, 0); row += 1
    grid.addWidget(accent_expander, row, 0); row += 1
    grid.setRowMinimumHeight(row, 28); row += 1
    grid.addWidget(about_title, row, 0); row += 1
    grid.addWidget(about_card, row, 0); row += 1
    grid.setRowStretch(row, 1)

    return {
        "theme_combo": theme_combo,
        "background_combo": background_combo,
        "navigation_combo": navigation_combo,
        "accent_expander": accent_expander,
    }
