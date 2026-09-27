"""TabBar 多种样式展示页（对应 C++ PageTab，pages/basic/pagetab.cpp）。"""

from PyQt5.QtCore import QEasingCurve, QSize, Qt
from PyQt5.QtGui import QColor, QFont, QIcon, QPainter, QPalette, QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QFrame,
    QLabel,
    QScrollArea,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from exwidgets import ExTabWidget

K_TAB_BAR_FLUENT_ICON_PX = 16
K_PIVOT_TAB_ICON_PX = 22


def create_fluent_icon_px(icon_code, pixel_size=16, color=None):
    """按指定像素尺寸绘制字体图标（PageTab 图标为 16/22px，非默认 25px）。"""
    size = pixel_size + 4
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform)
    font = QFont("Segoe Fluent Icons")
    font.setPixelSize(pixel_size)
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

# 各 Tab 条使用的图标集（SegoeIcon 码点）
CAPSULE_ICONS = ["\ue80f", "\ue721", "\ue713", "\ue897", "\ue946"]
SEGMENTED_ICONS = ["\uec64", "\uef58", "\ue99a", "\ue7ed", "\uf163"]
SEGMENTED_ICON_ONLY_ICONS = ["\ue722", "\ue714", "\ue90b", "\ue753"]
NAVIGATION_ICONS = ["\uec64", "\ue8b7", "\ue81c", "\ue9ce", "\ue713"]


def _apply_section_heading_font(label, pixel_size):
    font = label.font()
    font.setBold(True)
    font.setPixelSize(pixel_size)
    label.setFont(font)


def _apply_section_description_style(label):
    label.setStyleSheet("color: gray; font-size: 12px;")


def _style_tab_page_label(page, background):
    palette = page.palette()
    palette.setColor(QPalette.Window, background)
    palette.setColor(QPalette.WindowText, Qt.black)
    palette.setColor(QPalette.Text, Qt.black)
    page.setAutoFillBackground(True)
    page.setPalette(palette)


def setup_tab_showcase(window, controller):
    page4_layout = QVBoxLayout(window.page_4)
    page4_layout.setContentsMargins(0, 0, 0, 0)
    page4_layout.setSpacing(0)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.StyledPanel)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroll.viewport().setAutoFillBackground(False)
    scroll.viewport().setAttribute(Qt.WA_StyledBackground, False)

    content_widget = QWidget()
    content_widget.setAutoFillBackground(False)
    scroll.setWidget(content_widget)
    page4_layout.addWidget(scroll)

    main_layout = QVBoxLayout(content_widget)
    main_layout.setContentsMargins(11, 11, 11, 11)
    main_layout.setSpacing(15)

    main_title = QLabel("TabBar多种样式示例")
    main_title.setObjectName("tsw_main_title")
    main_title_font = main_title.font()
    main_title_font.setPointSize(18)
    main_title_font.setBold(True)
    main_title.setFont(main_title_font)
    main_layout.addWidget(main_title)

    def create_tab_widget_container():
        widget = QWidget()
        widget.setProperty("isCard", True)
        widget.setAttribute(Qt.WA_StyledBackground)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        return widget, layout

    tracked_bars = {}

    def add_tab_bar_section(layout, section_id, title, description, tab_style):
        title_label = QLabel(title)
        title_label.setObjectName(f"tsw_{section_id}_title")
        _apply_section_heading_font(title_label, 14)
        layout.addWidget(title_label)

        if description:
            desc_label = QLabel(description)
            desc_label.setObjectName(f"tsw_{section_id}_desc")
            _apply_section_description_style(desc_label)
            layout.addWidget(desc_label)

        tab_bar = QTabBar()
        tab_bar.setObjectName(f"tsw_{section_id}_bar")
        tab_bar.setDrawBase(False)
        tab_bar.setExpanding(False)
        tab_bar.setProperty("tabBarStyle", tab_style)
        if tab_style in (2, 3, 4):  # Pivot 系列：粗体 15px + 22px 图标
            pivot_font = tab_bar.font()
            pivot_font.setPixelSize(15)
            pivot_font.setWeight(QFont.Bold)
            tab_bar.setFont(pivot_font)
            tab_bar.setIconSize(QSize(K_PIVOT_TAB_ICON_PX, K_PIVOT_TAB_ICON_PX))
        elif tab_style in (6, 7, 9):  # Segmented 系列
            tab_bar.setAttribute(Qt.WA_StyledBackground, True)
        for text in ("Home", "Search", "Settings", "Help", "About"):
            tab_bar.addTab(text)
        layout.addWidget(tab_bar)
        tracked_bars[section_id] = tab_bar
        return tab_bar

    # ================= 1. Pivot =================
    pivot_widget, pivot_layout = create_tab_widget_container()
    add_tab_bar_section(pivot_layout, "pivot_grow", "Pivot Grow TabBar", "特点：选中时会有一个生长动画效果。", 2)
    add_tab_bar_section(pivot_layout, "pivot_slide", "Pivot Slide TabBar", "特点：选中时会有一个滑动动画效果。", 3)
    add_tab_bar_section(pivot_layout, "pivot_stretch", "Pivot Stretch TabBar", "特点：选中时会有一个拉伸动画效果。", 4)
    pivot_layout.addStretch()
    main_layout.addWidget(pivot_widget, 1)

    # ================= 2. Segmented =================
    seg_widget, seg_layout = create_tab_widget_container()
    add_tab_bar_section(seg_layout, "seg_slide", "Segmented Slide TabBar", "特点：Segmented风格，选中时会有一个滑动动画效果。", 6)
    add_tab_bar_section(seg_layout, "seg_fade", "Segmented Fade TabBar", "特点：Segmented风格，选中时会有一个淡入淡出动画效果。", 7)
    add_tab_bar_section(seg_layout, "seg_winui3", "Segmented WinUI3 TabBar", "特点：Segmented风格，WinUI3 的选中指示器效果。", 9)

    winui3_icon_bar = QTabBar()
    winui3_icon_bar.setObjectName("tsw_seg_winui3_icon_bar")
    winui3_icon_bar.setAttribute(Qt.WA_StyledBackground, True)
    winui3_icon_bar.setDrawBase(False)
    winui3_icon_bar.setExpanding(False)
    winui3_icon_bar.setProperty("tabBarStyle", 9)
    for _ in range(5):
        winui3_icon_bar.addTab("")
    winui3_icon_bar.setCurrentIndex(0)
    seg_layout.addWidget(winui3_icon_bar)
    tracked_bars["seg_winui3_icon_only"] = winui3_icon_bar

    def add_gallery_bar(object_name, tabs, selected, expanding, max_width_per):
        gallery_bar = QTabBar()
        gallery_bar.setObjectName(object_name)
        gallery_bar.setAttribute(Qt.WA_StyledBackground, True)
        gallery_bar.setDrawBase(False)
        gallery_bar.setProperty("tabBarStyle", 6)
        gallery_bar.setProperty("segmentedSemiRound", True)
        gallery_bar.setProperty("segmentedBackgroundColor", QColor("#D9D9DD"))
        gallery_bar.setProperty("segmentedBackgroundColorDark", QColor("#3F3F46"))
        gallery_bar.setProperty("segmentedSelectedColor", QColor("#FFFFFF"))
        gallery_bar.setProperty("segmentedSelectedColorDark", QColor("#5C5C64"))
        gallery_bar.setProperty("segmentedHoverColor", QColor("#E6E6EA"))
        gallery_bar.setProperty("segmentedHoverColorDark", QColor("#4A4A52"))
        gallery_bar.setProperty("segmentedPressedColor", QColor("#D0D0D4"))
        gallery_bar.setProperty("segmentedPressedColorDark", QColor("#55555D"))
        for text in tabs:
            gallery_bar.addTab(text)
        gallery_bar.setCurrentIndex(selected)
        gallery_bar.setExpanding(expanding)
        gallery_bar.setMaximumWidth(max_width_per * gallery_bar.count())
        seg_layout.addWidget(gallery_bar)
        return gallery_bar

    custom_label = QLabel("Segmented Gallery Style")
    custom_label.setObjectName("tsw_seg_gallery_title")
    _apply_section_heading_font(custom_label, 14)
    seg_layout.addWidget(custom_label)
    custom_desc = QLabel("特点：半圆胶囊 + 自定义背景/选中/悬停/按下色")
    custom_desc.setObjectName("tsw_seg_gallery_desc")
    _apply_section_description_style(custom_desc)
    seg_layout.addWidget(custom_desc)

    add_gallery_bar("tsw_seg_demo_gallery_bar", ["Weekly", "Daily", "Monthly"], 1, True, 150)
    add_gallery_bar("tsw_seg_purple_gallery_bar", ["Overview", "Stats", "Goals", "History"], 0, True, 150)
    icon_only_gallery_bar = add_gallery_bar("tsw_seg_icononly_bar", ["", "", "", ""], 1, False, 56)
    tracked_bars["seg_icon_only_gallery"] = icon_only_gallery_bar

    seg_layout.addStretch()
    main_layout.addWidget(seg_widget, 1)

    # ================= 3. Pill =================
    pill_widget, pill_layout = create_tab_widget_container()
    pill_label = QLabel("Pill TabBar")
    pill_label.setObjectName("tsw_pill_title")
    _apply_section_heading_font(pill_label, 14)
    pill_layout.addWidget(pill_label)

    pill_bar = QTabBar()
    pill_bar.setObjectName("tsw_pill_bar")
    pill_bar.setTabsClosable(True)
    pill_bar.setExpanding(False)
    pill_bar.setProperty("tabBarStyle", 5)
    for text in ("Home", "Search", "Settings", "Help", "About"):
        pill_bar.addTab(text)
    pill_layout.addWidget(pill_bar)
    pill_layout.addStretch()
    main_layout.addWidget(pill_widget, 1)

    # ================= 4. Capsule =================
    cap_widget, cap_layout = create_tab_widget_container()
    cap_label = QLabel("Capsule TabBar")
    cap_label.setObjectName("tsw_cap_title")
    _apply_section_heading_font(cap_label, 14)
    cap_desc = QLabel("特点：浏览器标签样式。")
    cap_desc.setObjectName("tsw_cap_desc")
    _apply_section_description_style(cap_desc)
    cap_layout.addWidget(cap_label)
    cap_layout.addWidget(cap_desc)

    cap_tab_widget = ExTabWidget()
    cap_tab_widget.setObjectName("tsw_cap_tabwidget")
    cap_tab_widget.setMinimumHeight(200)
    cap_tab_widget.setTabsClosable(True)
    cap_tab_widget.setMovable(True)

    cap_bar = cap_tab_widget.tabBar()
    cap_bar.setAutoFillBackground(False)
    cap_bar.setExpanding(False)
    cap_bar.setProperty("TextAlign", int(Qt.AlignVCenter | Qt.AlignLeft))
    cap_bar.setProperty("tabBarStyle", 1)  # Capsule
    cap_bar.setDrawBase(False)

    page_names = ["Home", "Search", "Settings", "Help", "About"]
    full_names = ["Home Page", "Search Page", "Settings Page", "Help Page", "About Page"]
    page_colors = [QColor(255, 228, 225), QColor(224, 255, 255), QColor(240, 255, 240),
                   QColor(255, 250, 205), QColor(230, 230, 250)]
    for i in range(5):
        page = QLabel(full_names[i])
        page.setObjectName(f"tsw_cap_body_{i}")
        page.setAlignment(Qt.AlignCenter)
        _style_tab_page_label(page, page_colors[i])
        cap_tab_widget.addTab(page, page_names[i])
    cap_layout.addWidget(cap_tab_widget)
    main_layout.addWidget(cap_widget, 1)

    # ================= 5. Navigation =================
    nav_widget, nav_layout = create_tab_widget_container()
    nav_label = QLabel("Navigation TabBar")
    nav_label.setObjectName("tsw_nav_title")
    _apply_section_heading_font(nav_label, 14)
    nav_desc = QLabel("特点：适合用于侧边栏的导航菜单，选项卡垂直排列，选中时指示器有个变长效果")
    nav_desc.setObjectName("tsw_nav_desc")
    _apply_section_description_style(nav_desc)
    nav_layout.addWidget(nav_label)
    nav_layout.addWidget(nav_desc)

    nav_tab_widget = ExTabWidget()
    nav_tab_widget.setObjectName("tsw_nav_tabwidget")
    nav_tab_widget.setTabPosition(ExTabWidget.West)
    nav_tab_widget.setVerticalMode(True)
    nav_tab_widget.setSpeed(220)
    nav_tab_widget.setAnimation(QEasingCurve.OutCubic)
    nav_tab_widget.setMinimumHeight(300)

    nav_bar = nav_tab_widget.tabBar()
    nav_bar.setShape(QTabBar.RoundedWest)
    nav_bar.setDrawBase(False)
    nav_tab_widget.setMovable(False)
    nav_bar.setExpanding(False)
    nav_bar.setProperty("TextAlign", int(Qt.AlignVCenter | Qt.AlignLeft))
    nav_bar.setProperty("tabBarStyle", 8)  # Navigation

    nav_full_names = ["Overview Page", "Files Page", "History Page", "Insights Page", "Settings Page"]
    nav_names = ["Overview", "Files", "History", "Insights", "Settings"]
    nav_page_colors = [QColor(244, 248, 255), QColor(240, 251, 246), QColor(255, 248, 238),
                       QColor(248, 243, 255), QColor(245, 245, 245)]
    for i in range(5):
        page = QLabel(nav_full_names[i])
        page.setObjectName(f"tsw_nav_body_{i}")
        page.setAlignment(Qt.AlignCenter)
        page.setMinimumHeight(220)
        _style_tab_page_label(page, nav_page_colors[i])
        nav_tab_widget.addTab(page, nav_names[i])

    nav_layout.addWidget(nav_tab_widget, 1)
    main_layout.addWidget(nav_widget, 1)

    main_layout.addStretch()

    # ---- 图标（对应 PageTab::updateTabIcons）----
    def update_tab_icons():
        icon_color = QApplication.palette().color(QPalette.WindowText)

        def set_bar_icons(bar, codes, icon_px=K_TAB_BAR_FLUENT_ICON_PX):
            if bar is None:
                return
            for i, code in enumerate(codes):
                if i < bar.count():
                    bar.setTabIcon(i, create_fluent_icon_px(code, icon_px, icon_color))

        for section_id in ("pivot_grow", "pivot_slide", "pivot_stretch"):
            set_bar_icons(tracked_bars.get(section_id), CAPSULE_ICONS, K_PIVOT_TAB_ICON_PX)
        for i, code in enumerate(CAPSULE_ICONS):
            if i < cap_tab_widget.count():
                cap_tab_widget.setTabIcon(i, create_fluent_icon_px(code, K_TAB_BAR_FLUENT_ICON_PX, icon_color))
        for section_id in ("seg_slide", "seg_fade", "seg_winui3", "seg_winui3_icon_only"):
            set_bar_icons(tracked_bars.get(section_id), SEGMENTED_ICONS)
        set_bar_icons(tracked_bars.get("seg_icon_only_gallery"), SEGMENTED_ICON_ONLY_ICONS)
        for i, code in enumerate(NAVIGATION_ICONS):
            if i < nav_tab_widget.count():
                nav_tab_widget.setTabIcon(i, create_fluent_icon_px(code, K_TAB_BAR_FLUENT_ICON_PX, icon_color))

    controller.register_tab_icons_updater(update_tab_icons)
    update_tab_icons()


