"""C++ ExWidgets / Frameless 组件的纯 PyQt5 移植。

对应关系：
- ExTabWidget           <- ExWidgets/controls/extabwidget.cpp
- ExNavTreeWidget       <- ExWidgets/navigation/exnavtreewidget.cpp
- ExWinUINavigationView <- ExWidgets/navigation/exwinuinavigationview.cpp
- ExTimeline            <- ExWidgets/media/extimeline.cpp（精简：仅垂直 ContentOnRight 布局）
- FluentTitleBar        <- frameless/fluenttitlebar.cpp
- ExExpander            <- ExWidgets/controls/exexpander.cpp（1:1 移植）

图标码点取自 ExWidgets/controls/exfonticon.h 的 SegoeIcon 枚举。
"""

from PyQt5.QtCore import (
    QEvent,
    QEasingCurve,
    QModelIndex,
    QParallelAnimationGroup,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSize,
    Qt,
    QVariantAnimation,
    pyqtSignal,
)
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetricsF,
    QIcon,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QPixmap,
)
from PyQt5.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from utils import create_fluent_icon

# Segoe Fluent Icons 码点（SegoeIcon 枚举）
ICON_MINIMIZE = "\ue921"
ICON_MAXIMIZE = "\ue922"
ICON_RESTORE = "\ue923"
ICON_CLOSE = "\ue8bb"
ICON_THEME = "\ue706"
ICON_PIN = "\ue718"
ICON_PINNED = "\ue77a"
ICON_SEARCH = "\ue721"
ICON_CHEVRON_DOWN_MED = "\ue972"
ICON_CHEVRON_UP_MED = "\ue971"


# =============================================================================
# ExTabWidget —— 带滑动动画的 QTabWidget
# =============================================================================

class ExTabWidget(QTabWidget):
    """切页时用覆盖层做滑动动画（与 ExStackedWidget 同一套做法）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._vertical_mode = False
        self._duration = 250
        self._curve = QEasingCurve.InOutCubic
        self._animating = False
        self._last_index = -1
        self._current_overlay = None
        self._next_overlay = None
        self._animation_group = None
        self.currentChanged.connect(self._on_current_changed)

    def setVerticalMode(self, vertical):
        self._vertical_mode = vertical

    def setSpeed(self, duration):
        self._duration = max(0, duration)

    def setAnimation(self, curve):
        self._curve = curve

    def _on_current_changed(self, index):
        if index < 0 or index >= self.count():
            return

        if self._animating:
            self._finish_animation()

        if not self.isVisible() or self._last_index < 0 or self._last_index == index or self._duration <= 0:
            self._last_index = index
            return

        current_widget = self.widget(self._last_index)
        next_widget = self.widget(index)
        if not current_widget or not next_widget:
            self._last_index = index
            return

        stack = current_widget.parentWidget() or self
        area = QRect(QPoint(0, 0), stack.size())

        current_widget.resize(area.size())
        next_widget.resize(area.size())

        current_pixmap = QPixmap(area.size())
        current_pixmap.fill(Qt.transparent)
        current_widget.render(current_pixmap)

        next_pixmap = QPixmap(area.size())
        next_pixmap.fill(Qt.transparent)
        next_widget.render(next_pixmap)

        current_overlay = QLabel(stack)
        current_overlay.setPixmap(current_pixmap)
        current_overlay.setScaledContents(False)
        current_overlay.setGeometry(area)
        current_overlay.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        current_overlay.show()
        current_overlay.raise_()

        next_overlay = QLabel(stack)
        next_overlay.setPixmap(next_pixmap)
        next_overlay.setScaledContents(False)
        next_overlay.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        forward = index > self._last_index
        if self._vertical_mode:
            offset = area.height()
            current_end = QPoint(0, -offset if forward else offset)
            next_start = QPoint(0, offset if forward else -offset)
        else:
            offset = area.width()
            current_end = QPoint(-offset if forward else offset, 0)
            next_start = QPoint(offset if forward else -offset, 0)

        next_overlay.setGeometry(QRect(next_start, area.size()))
        next_overlay.show()
        next_overlay.raise_()

        next_widget.hide()

        current_animation = QPropertyAnimation(current_overlay, b"pos", self)
        current_animation.setDuration(self._duration)
        current_animation.setEasingCurve(self._curve)
        current_animation.setStartValue(QPoint(0, 0))
        current_animation.setEndValue(current_end)

        next_animation = QPropertyAnimation(next_overlay, b"pos", self)
        next_animation.setDuration(self._duration)
        next_animation.setEasingCurve(self._curve)
        next_animation.setStartValue(next_start)
        next_animation.setEndValue(QPoint(0, 0))

        group = QParallelAnimationGroup(self)
        group.addAnimation(current_animation)
        group.addAnimation(next_animation)

        self._animating = True
        self._current_overlay = current_overlay
        self._next_overlay = next_overlay
        self._animation_group = group
        group.finished.connect(self._finish_animation)
        group.start()

        self._last_index = index

    def _finish_animation(self):
        if self._animation_group is not None:
            self._animation_group.stop()
            self._animation_group.deleteLater()
            self._animation_group = None

        current = self.currentWidget()
        if current is not None:
            current.show()

        for attr in ("_current_overlay", "_next_overlay"):
            overlay = getattr(self, attr)
            if overlay is not None:
                overlay.deleteLater()
                setattr(self, attr, None)

        self._animating = False


# =============================================================================
# ExNavTreeWidget —— 支持紧凑/展开两种宽度模式的导航树
# =============================================================================

NAV_PAGE_ROLE = Qt.UserRole          # 页面索引
NAV_ICON_ROLE = Qt.UserRole + 1      # 图标码点
NAV_TEXT_ROLE = Qt.UserRole + 2      # 文本（紧凑模式下清空显示）
NAV_WAS_EXPANDED_ROLE = Qt.UserRole + 3
NAV_WAS_SELECTED_ROLE = Qt.UserRole + 4


class ExNavTreeWidget(QTreeWidget):
    pageIndexChanged = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ExNavTreeWidget")
        self._navigation_expanded = False
        self._auto_fixed_height = False
        self._navigation_compact_width = 44
        self._navigation_expanded_width = 200
        self._restorable_child = None

        font = QFont(self.font())
        font.setPixelSize(13)
        font.setFamily("微软雅黑")
        font.setHintingPreference(QFont.PreferNoHinting)
        self.setFont(font)

        self.setAnimated(True)
        self.setIconSize(QSize(20, 20))
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setRootIsDecorated(False)

        self.viewport().setAutoFillBackground(False)
        self.viewport().setAttribute(Qt.WA_StyledBackground, False)
        self.setFrameShape(QFrame.NoFrame)

        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setTextElideMode(Qt.ElideRight)
        self.setProperty("navigationViewIndicator", True)
        self.setProperty("ItemHeight", 38)
        self.header().setSectionResizeMode(0, QHeaderView.Fixed)
        self.setHeaderHidden(True)
        self.setColumnWidth(0, self._navigation_compact_width)
        self.setFixedWidth(self._navigation_compact_width)

        self._width_animation = QVariantAnimation(self)
        self._width_animation.setDuration(280)
        self._width_animation.setEasingCurve(QEasingCurve.OutCubic)
        self._width_animation.valueChanged.connect(
            lambda value: self._update_navigation_view_by_width(int(value)))
        self._width_animation.finished.connect(self._on_width_animation_finished)

        self.currentItemChanged.connect(self._handle_item_selection)

    # ---- 尺寸配置 ----
    def setCompactWidth(self, width):
        self._navigation_compact_width = max(1, width)
        if not self._navigation_expanded:
            self._width_animation.stop()
            self._update_navigation_view_by_width(self._navigation_compact_width)

    def setExpandedWidth(self, width):
        self._navigation_expanded_width = max(self._navigation_compact_width, width)
        if self._navigation_expanded:
            self._width_animation.stop()
            self._update_navigation_view_by_width(self._navigation_expanded_width)

    # ---- 项管理 ----
    def addNavigationItem(self, text, page_index, icon_code=""):
        item = QTreeWidgetItem(self)
        self.configureNavigationItem(item, text, page_index, icon_code)
        self._update_fixed_height()
        return item

    def configureNavigationItem(self, item, text, page_index, icon_code=""):
        if item is None:
            return
        item.setData(0, NAV_PAGE_ROLE, page_index)
        item.setData(0, NAV_TEXT_ROLE, text)
        item.setData(0, NAV_ICON_ROLE, icon_code)
        item.setToolTip(0, text)
        self._update_navigation_item_icon(item)
        self._update_navigation_item_text(item, self._navigation_expanded)

    def _update_navigation_item_icon(self, item):
        if item is None:
            return
        icon_code = item.data(0, NAV_ICON_ROLE)
        if icon_code:
            item.setIcon(0, create_fluent_icon(icon_code, self.palette().color(QPalette.Text)))
        for i in range(item.childCount()):
            self._update_navigation_item_icon(item.child(i))

    def _update_navigation_item_text(self, item, expanded):
        if item is None:
            return
        item.setText(0, item.data(0, NAV_TEXT_ROLE) if expanded else "")
        for i in range(item.childCount()):
            self._update_navigation_item_text(item.child(i), expanded)

    def _update_navigation_item_expansion(self, item, show_text):
        if item is None:
            return
        if item.childCount() > 0:
            if not show_text:
                item.setData(0, NAV_WAS_EXPANDED_ROLE, item.isExpanded())
                item.setExpanded(False)
            else:
                was_expanded = item.data(0, NAV_WAS_EXPANDED_ROLE)
                item.setExpanded(was_expanded if was_expanded is not None else False)
                item.setData(0, NAV_WAS_EXPANDED_ROLE, None)
        for i in range(item.childCount()):
            self._update_navigation_item_expansion(item.child(i), show_text)

    def _update_navigation_item_visibility_for_depth(self, item, visible_depth, current_depth=0):
        if item is None:
            return
        item.setHidden(current_depth > visible_depth)
        for i in range(item.childCount()):
            self._update_navigation_item_visibility_for_depth(item.child(i), visible_depth, current_depth + 1)

    # ---- 展开 / 紧凑 ----
    def setNavigationExpanded(self, expanded, animated=True):
        self._navigation_expanded = expanded
        target_width = self._navigation_expanded_width if expanded else self._navigation_compact_width
        if not animated:
            self._update_navigation_view_by_width(target_width)
            return

        current_width = self.width()
        if current_width == target_width:
            return

        self._width_animation.stop()
        self._width_animation.setStartValue(current_width)
        self._width_animation.setEndValue(target_width)
        self._width_animation.start()

    def navigationExpanded(self):
        return self._navigation_expanded

    def toggleNavigationMode(self):
        self.setNavigationExpanded(not self._navigation_expanded, True)

    def _on_width_animation_finished(self):
        target_width = (self._navigation_expanded_width if self._navigation_expanded
                        else self._navigation_compact_width)
        self._update_navigation_view_by_width(target_width)

    def _update_navigation_view_by_width(self, width):
        text_switch_width = self._navigation_compact_width + (
            self._navigation_expanded_width - self._navigation_compact_width) * 2 // 3
        show_text = width >= text_switch_width
        visible_depth = 2 ** 31 - 1 if show_text else 1  # INT_MAX

        old_icon_mode = self.property("navigationIconMode")
        will_be_icon_mode = not show_text
        mode_flipped = (bool(old_icon_mode) != will_be_icon_mode)
        if mode_flipped:
            if will_be_icon_mode:
                current = self.currentItem()
                if current is not None and current.parent() is not None:
                    top_level = current
                    while top_level.parent() is not None:
                        top_level = top_level.parent()
                    # 保存真实子节点，恢复展开模式时重新选中
                    self._restorable_child = current
                    self.setCurrentItem(top_level)
            else:
                current = self.currentItem()
                if current is not None and current.parent() is None:
                    saved_child = self._restorable_child
                    if saved_child is not None:
                        self.setCurrentItem(saved_child)
                        self._restorable_child = None

        self.setProperty("navigationIconMode", will_be_icon_mode)

        self.setUpdatesEnabled(False)
        self.setFixedWidth(width)

        scroll_bar_extent = self.style().pixelMetric(self.style().PM_ScrollBarExtent, None, self)
        frame_border_width = self.frameWidth() * 2
        safe_column_width = max(self._navigation_compact_width, width - scroll_bar_extent - frame_border_width)
        self.setColumnWidth(0, safe_column_width)

        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            self._update_navigation_item_text(item, show_text)
            self._update_navigation_item_visibility_for_depth(item, visible_depth)
            if mode_flipped:
                self._update_navigation_item_expansion(item, show_text)

        self.setUpdatesEnabled(True)
        self.viewport().update()

    # ---- 高度 ----
    def setAutoHeightByItemsEnabled(self, enabled):
        self._auto_fixed_height = enabled
        self._update_fixed_height()

    def _update_fixed_height(self):
        if self._auto_fixed_height:
            item_height = self.property("ItemHeight")
            if not item_height or item_height <= 0:
                item_height = 38
            self.setFixedHeight(self.topLevelItemCount() * item_height)

    # ---- 事件 ----
    def _handle_item_selection(self, current, _previous):
        if current is None:
            return
        page_data = current.data(0, NAV_PAGE_ROLE)
        if page_data is None:
            return
        self.pageIndexChanged.emit(int(page_data))

    def changeEvent(self, event):
        super().changeEvent(event)
        if event is None:
            return
        if event.type() in (QEvent.PaletteChange, QEvent.ApplicationPaletteChange, QEvent.StyleChange):
            for i in range(self.topLevelItemCount()):
                self._update_navigation_item_icon(self.topLevelItem(i))

    def mousePressEvent(self, event):
        pos = event.pos()
        index = self.indexAt(pos)
        self.setCurrentIndex(index)

        # 紧凑图标模式下不显示右侧箭头，整个 Item 区域点击都作为选中处理
        if (index.isValid() and self.model().hasChildren(index)
                and not self.property("navigationIconMode")):
            r = self.visualRect(index)
            is_reverse = self.layoutDirection() == Qt.RightToLeft
            # 箭头由样式绘制在最右侧 22px，这里给 30px 的宽裕点击区
            arrow_zone = 30
            is_arrow_click = (pos.x() < r.left() + arrow_zone) if is_reverse else (pos.x() > r.right() - arrow_zone)
            if is_arrow_click:
                if self.isExpanded(index):
                    self.collapse(index)
                else:
                    self.expand(index)
                event.accept()
                return

        super().mousePressEvent(event)


# =============================================================================
# ExWinUINavigationView —— 主导航 + 分隔线 + 底部导航
# =============================================================================

class ExWinUINavigationView(QWidget):
    pageIndexChanged = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ExWinUINavigationView")
        self._stacked_widget = None

        self._main_nav = ExNavTreeWidget(self)
        self._main_nav.setObjectName("mainNavView")

        self._line = QFrame(self)
        self._line.setObjectName("line")
        self._line.setFrameShape(QFrame.HLine)
        self._line.setFrameShadow(QFrame.Sunken)
        self._line.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)

        self._footer_nav = ExNavTreeWidget(self)
        self._footer_nav.setObjectName("footerNavView")
        self._footer_nav.setAnimated(False)
        self._footer_nav.setAutoHeightByItemsEnabled(True)

        self._main_nav.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Expanding)
        self._main_nav.setIndentation(20)
        nav_font = QFont(self._main_nav.font())
        nav_font.setPointSize(10)
        self._main_nav.setFont(nav_font)

        self._footer_nav.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        self._footer_nav.setIndentation(20)
        self._footer_nav.setFont(nav_font)

        main_container = QWidget(self)
        main_layout = QVBoxLayout(main_container)
        main_layout.setContentsMargins(6, 6, 6, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self._main_nav)

        footer_container = QWidget(self)
        footer_layout = QVBoxLayout(footer_container)
        footer_layout.setContentsMargins(6, 0, 6, 6)
        footer_layout.setSpacing(0)
        footer_layout.addWidget(self._footer_nav)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(main_container, 1)
        lay.addWidget(self._line, 0)
        lay.addWidget(footer_container, 0)

        self._main_nav.currentItemChanged.connect(
            lambda current, _prev: self._handle_cross_view_selection(self._main_nav, self._footer_nav, current))
        self._footer_nav.currentItemChanged.connect(
            lambda current, _prev: self._handle_cross_view_selection(self._footer_nav, self._main_nav, current))

        self._main_nav.pageIndexChanged.connect(self._on_page_index_changed)
        self._footer_nav.pageIndexChanged.connect(self._on_page_index_changed)

    def _on_page_index_changed(self, page_index):
        if self._stacked_widget is not None:
            self._stacked_widget.setCurrentIndex(page_index)
        self.pageIndexChanged.emit(page_index)

    def mainNavView(self):
        return self._main_nav

    def footerNavView(self):
        return self._footer_nav

    def setStackedWidget(self, stack):
        self._stacked_widget = stack
        self._stacked_widget.setCurrentIndex(self.selectedPageIndex())

    def stackedWidget(self):
        return self._stacked_widget

    def setSelectedPageIndex(self, page_index):
        def walk_tree(tree):
            stack = [tree.topLevelItem(i) for i in range(tree.topLevelItemCount())]
            while stack:
                item = stack.pop(0)
                if item is not None and item.data(0, NAV_PAGE_ROLE) == page_index:
                    tree.setCurrentItem(item)
                    return True
                for i in range(item.childCount()):
                    stack.append(item.child(i))
            return False

        return walk_tree(self._main_nav) or walk_tree(self._footer_nav)

    def selectedPageIndex(self):
        def item_page(item):
            if item is None:
                return -1
            page_data = item.data(0, NAV_PAGE_ROLE)
            return int(page_data) if page_data is not None else -1

        main_page = item_page(self._main_nav.currentItem() if self._main_nav else None)
        if main_page >= 0:
            return main_page
        return item_page(self._footer_nav.currentItem() if self._footer_nav else None)

    def setNavigationExpanded(self, expanded, animated=True):
        if self._main_nav:
            self._main_nav.setNavigationExpanded(expanded, animated)
        if self._footer_nav:
            self._footer_nav.setNavigationExpanded(expanded, animated)

    def navigationExpanded(self):
        return bool(self._main_nav) and self._main_nav.navigationExpanded()

    def addNavigationItem(self, text, page_index, icon_code=""):
        return self.addMainNavigationItem(text, page_index, icon_code)

    def addMainNavigationItem(self, text, page_index, icon_code=""):
        if not self._main_nav:
            return None
        item = self._main_nav.addNavigationItem(text, page_index, icon_code)
        if item is not None and self._main_nav.currentItem() is None and self._main_nav.topLevelItemCount() == 1:
            self._main_nav.setCurrentItem(item)
        return item

    def addFooterNavigationItem(self, text, page_index, icon_code=""):
        return self._footer_nav.addNavigationItem(text, page_index, icon_code) if self._footer_nav else None

    def clearFooterSelection(self):
        if not self._footer_nav:
            return
        self._footer_nav.clearSelection()
        self._footer_nav.setCurrentIndex(QModelIndex())

    def _handle_cross_view_selection(self, activated_nav, peer_nav, current):
        if (current is None or not activated_nav or not peer_nav or not peer_nav.selectionModel()
                or not peer_nav.selectionModel().hasSelection()):
            return

        activated_is_footer = activated_nav == self._footer_nav
        peer_nav.setProperty("navigationDirection", "down" if activated_is_footer else "up")
        activated_nav.setProperty("navigationDirection", "up" if activated_is_footer else "down")

        peer_nav.clearSelection()
        peer_nav.setCurrentIndex(QModelIndex())
        if peer_nav.viewport():
            peer_nav.viewport().update()


# =============================================================================
# ExTimeline —— 纯 Python 时间轴（垂直 + ContentOnRight）
# =============================================================================

TIMELINE_AXIS_GAP = 12.0
TIMELINE_TEXT_GAP = 4.0
TIMELINE_MIN_EVENT_HEIGHT = 44.0


class ExTimelineEvent:
    NORMAL, PENDING, CURRENT, COMPLETED, WARNING, ERROR = range(6)

    def __init__(self, timestamp, title, description="", status=NORMAL):
        self.timestamp = timestamp  # QDateTime
        self.title = title
        self.description = description
        self.status = status


class ExTimeline(QWidget):
    """垂直时间轴：左侧时间戳 + 轴线节点 + 右侧内容（ContentOnRight）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ExTimeline")
        self._events = []
        self._node_size = 14
        self._line_width = 2.0
        self._item_spacing = 18
        self._content_padding = 12
        self._timestamp_width = 100
        self._timestamp_format = "yyyy-MM-dd"
        self._in_resize = False

        self._pulse_animation = QVariantAnimation(self)
        self._pulse_animation.setDuration(1500)
        self._pulse_animation.setStartValue(0.0)
        self._pulse_animation.setEndValue(1.0)
        self._pulse_animation.setLoopCount(-1)
        self._pulse_animation.valueChanged.connect(lambda _value: self.update())
        self._update_pulse_state()

    def _update_pulse_state(self):
        has_current = any(e.status == ExTimelineEvent.CURRENT for e in self._events)
        if has_current and self.isVisible() and self.isEnabled():
            if self._pulse_animation.state() != QVariantAnimation.Running:
                self._pulse_animation.start()
        elif self._pulse_animation.state() == QVariantAnimation.Running:
            self._pulse_animation.stop()

    def showEvent(self, event):
        super().showEvent(event)
        self._update_pulse_state()

    def addEvent(self, timestamp, title, description="", status=ExTimelineEvent.NORMAL):
        self._events.append(ExTimelineEvent(timestamp, title, description, status))
        self._update_pulse_state()
        self.updateGeometry()

    def setTimestampFormat(self, fmt):
        self._timestamp_format = fmt

    def setTimestampWidth(self, width):
        self._timestamp_width = width

    # ---- 布局 ----
    def _title_font(self):
        font = QFont(self.font())
        font.setWeight(QFont.DemiBold)
        return font

    def _description_font(self):
        font = QFont(self.font())
        font.setWeight(QFont.Normal)
        if font.pixelSize() > 0:
            font.setPixelSize(max(9, font.pixelSize() - 1))
        else:
            font.setPointSize(max(9, font.pointSize() - 1))
        return font

    def _timestamp_font(self):
        return self._description_font()

    def _event_color(self, event):
        if event.status == ExTimelineEvent.COMPLETED:
            return QColor("#107C10")
        if event.status == ExTimelineEvent.PENDING:
            return self._default_rail_color()
        if event.status == ExTimelineEvent.WARNING:
            return QColor("#F2A900")
        if event.status == ExTimelineEvent.ERROR:
            return QColor("#D13438")
        # Current / Normal —— 强调色（Qt5 下 Highlight 即强调色定制点）
        return self.palette().color(QPalette.Highlight)

    def _default_rail_color(self):
        base = self.palette().color(QPalette.Base)
        text = self.palette().color(QPalette.Text)
        amount = 0.22
        return QColor(
            round(base.red() * (1 - amount) + text.red() * amount),
            round(base.green() * (1 - amount) + text.green() * amount),
            round(base.blue() * (1 - amount) + text.blue() * amount),
        )

    def _row_height(self, event, width):
        title_font = self._title_font()
        description_font = self._description_font()
        timestamp_font = self._timestamp_font()
        title_metrics = QFontMetricsF(title_font)

        side_width = max(40.0, width - self._timestamp_width - TIMELINE_AXIS_GAP * 2 - self._node_size
                         - self._content_padding * 2)
        content_height = title_metrics.height()
        if event.description:
            bounds = QFontMetricsF(description_font).boundingRect(
                QRectF(0, 0, side_width, 10000.0),
                Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap,
                event.description)
            content_height += TIMELINE_TEXT_GAP + bounds.height()
        timestamp_height = (QFontMetricsF(timestamp_font).height()
                            if not event.timestamp.isNull() else 0.0)
        body_height = max(content_height, timestamp_height, float(self._node_size))
        return int(max(TIMELINE_MIN_EVENT_HEIGHT, body_height)) + self._item_spacing

    def sizeHint(self):
        width = max(240, self.parentWidget().width() if self.parentWidget() else 240)
        return QSize(width, self._total_height(width))

    def _total_height(self, width):
        return sum(self._row_height(e, width) for e in self._events)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 宽度变化后描述换行高度随之变化，动态修正最小高度（配合 QScrollArea）。
        # setMinimumHeight 会再次触发 resizeEvent，必须加防重入保护。
        if self._in_resize:
            return
        self._in_resize = True
        try:
            new_height = self._total_height(self.width())
            if new_height != self.minimumHeight():
                self.setMinimumHeight(new_height)
        finally:
            self._in_resize = False

    # ---- 绘制 ----
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        width = self.width()
        title_font = self._title_font()
        description_font = self._description_font()
        timestamp_font = self._timestamp_font()
        title_metrics = QFontMetricsF(title_font)

        left = float(self._content_padding)
        right = float(width - self._content_padding)
        axis_x = left + self._timestamp_width + TIMELINE_AXIS_GAP + self._node_size * 0.5
        gap = self._node_size * 0.5 + TIMELINE_AXIS_GAP

        y = 0.0
        rail_color = self._default_rail_color()
        for index, ev in enumerate(self._events):
            row_rect = QRectF(left, y, width - left * 2, self._row_height(ev, width))
            top = row_rect.top() + max(4.0, self._item_spacing * 0.25)
            node_center_y = top + max(title_metrics.height(), float(self._node_size)) * 0.5

            content_rect = QRectF(axis_x + gap, top, max(0.0, right - axis_x - gap), row_rect.bottom() - top)
            timestamp_rect = QRectF(left, top, max(0.0, axis_x - gap - left), title_metrics.height())

            # 轨道
            painter.setPen(QPen(rail_color, self._line_width, Qt.SolidLine, Qt.FlatCap))
            if index > 0:
                painter.drawLine(QPointF(axis_x, row_rect.top()), QPointF(axis_x, node_center_y))
            if index + 1 < len(self._events):
                painter.drawLine(QPointF(axis_x, node_center_y), QPointF(axis_x, row_rect.bottom()))

            self._draw_node(painter, ev, QPointF(axis_x, node_center_y), self._event_color(ev))

            # 标题
            title_text = title_metrics.elidedText(ev.title, Qt.ElideRight, int(content_rect.width()))
            painter.setFont(title_font)
            painter.setPen(self.palette().color(QPalette.Text))
            painter.drawText(
                QRectF(content_rect.left(), top, content_rect.width(), title_metrics.height()),
                Qt.AlignLeft | Qt.AlignVCenter, title_text)

            # 描述
            if ev.description:
                description_color = QColor(self.palette().color(QPalette.Text))
                description_color.setAlpha(170)
                painter.setFont(description_font)
                painter.setPen(description_color)
                description_rect = QRectF(
                    content_rect.left(),
                    top + title_metrics.height() + TIMELINE_TEXT_GAP,
                    content_rect.width(),
                    max(0.0, row_rect.bottom() - top - title_metrics.height() - TIMELINE_TEXT_GAP))
                painter.drawText(description_rect, Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, ev.description)

            # 时间戳
            if not ev.timestamp.isNull():
                timestamp_color = QColor(self.palette().color(QPalette.Text))
                timestamp_color.setAlpha(150)
                painter.setFont(timestamp_font)
                painter.setPen(timestamp_color)
                timestamp = ev.timestamp.toString(self._timestamp_format)
                painter.drawText(
                    timestamp_rect, Qt.AlignRight | Qt.AlignVCenter,
                    QFontMetricsF(timestamp_font).elidedText(timestamp, Qt.ElideRight, int(timestamp_rect.width())))

            y += self._row_height(ev, width)

        painter.end()

    def _draw_node(self, painter, event, center, color):
        radius = self._node_size * 0.5

        if event.status == ExTimelineEvent.CURRENT:
            progress = self._pulse_animation.currentValue()
            if progress is None:
                progress = 0.0
            ring_color = QColor(color)
            ring_color.setAlpha(round(105.0 * (1.0 - progress)))
            painter.setPen(QPen(ring_color, 1.5))
            painter.setBrush(Qt.NoBrush)
            ring_radius = radius + 2.0 + progress * 6.0
            painter.drawEllipse(center, ring_radius, ring_radius)

        outlined = event.status in (ExTimelineEvent.NORMAL, ExTimelineEvent.PENDING)
        pen = QPen(color, 1.0)
        brush = QBrush(color)
        if event.status == ExTimelineEvent.NORMAL:
            pen.setWidthF(4.0)
            brush = QBrush(self.palette().color(QPalette.Base))
        elif event.status == ExTimelineEvent.PENDING:
            pen.setWidthF(2.0)
            brush = QBrush(self.palette().color(QPalette.Base))

        painter.setPen(pen)
        painter.setBrush(brush)
        adjusted_radius = max(0.0, radius - pen.widthF() * 0.5)
        painter.drawEllipse(center, adjusted_radius, adjusted_radius)

        symbol_color = color if outlined else QColor(Qt.white)
        painter.setPen(QPen(symbol_color, max(1.2, self._node_size * 0.11), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        if event.status == ExTimelineEvent.COMPLETED:
            check = QPainterPath()
            check.moveTo(center + QPointF(-radius * 0.42, 0.0))
            check.lineTo(center + QPointF(-radius * 0.10, radius * 0.30))
            check.lineTo(center + QPointF(radius * 0.46, -radius * 0.34))
            painter.drawPath(check)
        elif event.status == ExTimelineEvent.ERROR:
            painter.drawLine(center + QPointF(-radius * 0.30, -radius * 0.30),
                             center + QPointF(radius * 0.30, radius * 0.30))
            painter.drawLine(center + QPointF(radius * 0.30, -radius * 0.30),
                             center + QPointF(-radius * 0.30, radius * 0.30))


# =============================================================================
# FluentTitleBar —— 无边框窗口标题栏
# =============================================================================

class FluentAccentColorButton(QToolButton):
    def __init__(self, color=QColor(), parent=None):
        super().__init__(parent)
        self._color = color
        self._is_default = not color.isValid()
        self.setCheckable(True)
        self.setAutoRaise(True)
        self.setFixedSize(20, 20)
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        center = QRectF(self.rect()).center()
        min_dimension = min(self.width(), self.height())
        r_outer = min_dimension / 2.0 - 2.0

        base_color = self._color if self._color.isValid() else QColor("#0078D4")
        draw_color = QColor(base_color)
        if self.isDown():
            draw_color = draw_color.darker(115)
        elif self.underMouse():
            draw_color = draw_color.lighter(112)

        is_dark = QApplication.instance().property("_q_colorscheme") == 1

        if self.isChecked():
            # 选中态：外圈 + 内实心点
            painter.setPen(QPen(draw_color, 2.0))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(center, r_outer - 0.5, r_outer - 0.5)
            r_inner = max(3.2, r_outer - 2.5)
            painter.setPen(Qt.NoPen)
            painter.setBrush(draw_color)
            painter.drawEllipse(center, r_inner, r_inner)
        else:
            outline_color = (QColor(255, 255, 255, 120 if self.underMouse() else 60) if is_dark
                             else QColor(0, 0, 0, 90 if self.underMouse() else 40))
            painter.setPen(QPen(outline_color, 1.0))
            painter.setBrush(draw_color)
            r_fill = r_outer - 0.5 if self.underMouse() else r_outer - 1.2
            painter.drawEllipse(center, r_fill, r_fill)
        painter.end()


def _caption_icon_font(pixel_size=11):
    font = QFont("Segoe Fluent Icons")
    font.setPixelSize(pixel_size)
    font.setStyleStrategy(QFont.PreferAntialias)
    return font


def _create_caption_button(parent, object_name, glyph, width=46, pixel_size=11):
    button = QToolButton(parent)
    button.setObjectName(object_name)
    button.setAutoRaise(True)
    button.setToolButtonStyle(Qt.ToolButtonTextOnly)
    button.setFont(_caption_icon_font(pixel_size))
    button.setText(glyph)
    button.setFixedSize(width, 40)
    return button


class FluentTitleBar(QWidget):
    accentColorChanged = pyqtSignal(QColor)

    def __init__(self, window, parent=None):
        super().__init__(parent or window)
        self.setObjectName("fluent-title-bar")
        self._window = window
        self._theme_dark = False
        self._pinned = False
        self._current_accent_index = 0
        self.setFixedHeight(40)
        self.setAttribute(Qt.WA_StyledBackground, True)

        self._icon_label = QLabel(self)
        self._icon_label.setFixedSize(16, 16)
        self._icon_label.setScaledContents(True)

        self._title_label = QLabel(self)
        self._title_label.setObjectName("fluent-title-label")

        self._accent_button_group = QButtonGroup(self)
        self._accent_button_group.setExclusive(True)
        self._accent_colors = [QColor(), QColor("#5B5FC7"), QColor("#107C41")]
        self._accent_buttons = []
        for i, color in enumerate(self._accent_colors):
            btn = FluentAccentColorButton(parent=self)
            btn.setObjectName(f"win_caption_accent_{i}")
            btn._color = color
            btn._is_default = not color.isValid()
            btn.setToolTip("默认强调色" if not color.isValid() else f"强调色: {color.name()}")
            self._accent_buttons.append(btn)
            self._accent_button_group.addButton(btn, i)
        self._accent_button_group.idClicked.connect(self._on_accent_button_clicked)

        self._theme_button = _create_caption_button(self, "win_caption_theme", ICON_THEME, 40, 16)
        self._pin_button = _create_caption_button(self, "win_caption_pin", ICON_PIN, 40, 16)
        self._pin_button.setCheckable(True)
        self._min_button = _create_caption_button(self, "win_caption_minimize", ICON_MINIMIZE)
        self._max_button = _create_caption_button(self, "win_caption_maximize", ICON_MAXIMIZE)
        self._max_button.setCheckable(True)
        self._close_button = _create_caption_button(self, "win_caption_close", ICON_CLOSE)

        self._search_line_edit = QLineEdit(self)
        self._search_line_edit.setMinimumWidth(300)
        self._search_line_edit.setPlaceholderText("搜索...")
        self._search_line_edit.setClearButtonEnabled(True)
        self._search_action = self._search_line_edit.addAction(
            self._search_icon(False), QLineEdit.TrailingPosition)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self._icon_label)
        layout.addWidget(self._title_label)
        layout.addStretch()
        layout.addWidget(self._search_line_edit, 0, Qt.AlignCenter)
        layout.addStretch()
        for btn in self._accent_buttons:
            layout.addWidget(btn, 0, Qt.AlignVCenter)
        layout.addSpacing(4)
        layout.addWidget(self._theme_button)
        layout.addWidget(self._pin_button)
        layout.addWidget(self._min_button)
        layout.addWidget(self._max_button)
        layout.addWidget(self._close_button)

        self._min_button.clicked.connect(window.showMinimized)

        def toggle_maximized():
            if window.isMaximized():
                window.showNormal()
            else:
                window.showMaximized()

        self._max_button.clicked.connect(toggle_maximized)
        self._close_button.clicked.connect(window.close)
        self._pin_button.toggled.connect(lambda _checked: self.updatePinButton())

        self.updateTitle()
        self.updateIcon()
        self.updateMaxButton()
        self.updateThemeButton()
        self.updatePinButton()
        self.updateAccentButtons()
        window.installEventFilter(self)

    # ---- 访问 ----
    def themeButton(self):
        return self._theme_button

    def pinButton(self):
        return self._pin_button

    def minButton(self):
        return self._min_button

    def maxButton(self):
        return self._max_button

    def closeButton(self):
        return self._close_button

    def searchLineEdit(self):
        return self._search_line_edit

    def accentButtons(self):
        return self._accent_buttons

    def currentAccentColor(self):
        if 0 <= self._current_accent_index < len(self._accent_colors):
            return self._accent_colors[self._current_accent_index]
        return QColor()

    # ---- 更新 ----
    def setThemeDark(self, dark):
        if self._theme_dark == dark:
            return
        self._theme_dark = dark
        self.updateThemeButton()
        self.updateAccentButtons()
        self._search_action.setIcon(self._search_icon(dark))

    def setPinned(self, pinned):
        self._pinned = pinned
        if self._pin_button.isChecked() != pinned:
            self._pin_button.setChecked(pinned)
        else:
            self.updatePinButton()

    def _search_icon(self, dark_theme):
        icon_size = 32
        icon_font = QFont("Segoe Fluent Icons")
        icon_font.setPixelSize(icon_size)
        pixmap = QPixmap(icon_size, icon_size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        painter.setFont(icon_font)
        painter.setPen(Qt.white if dark_theme else Qt.black)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, ICON_SEARCH)
        painter.end()
        return QIcon(pixmap)

    def eventFilter(self, watched, event):
        if watched == self._window:
            if event.type() == QEvent.WindowIconChange:
                self.updateIcon()
            elif event.type() == QEvent.WindowTitleChange:
                self.updateTitle()
            elif event.type() == QEvent.WindowStateChange:
                self.updateMaxButton()
        return super().eventFilter(watched, event)

    def updateTitle(self):
        self._title_label.setText(self._window.windowTitle())

    def updateIcon(self):
        icon = self._window.windowIcon()
        if icon.isNull():
            icon = QApplication.windowIcon()
        if icon.isNull():
            self._icon_label.clear()
            return
        self._icon_label.setPixmap(icon.pixmap(16, 16))

    def updateMaxButton(self):
        maximized = self._window.isMaximized()
        self._max_button.setChecked(maximized)
        self._max_button.setText(ICON_RESTORE if maximized else ICON_MAXIMIZE)

    def updateThemeButton(self):
        self._theme_button.setText(ICON_THEME)
        self._theme_button.setToolTip("切换到浅色主题" if self._theme_dark else "切换到暗色主题")

    def updatePinButton(self):
        pinned = self._pin_button.isChecked()
        self._pinned = pinned
        self._pin_button.setText(ICON_PINNED if pinned else ICON_PIN)
        self._pin_button.setToolTip("取消置顶" if pinned else "置顶窗口")
        self._pin_button.update()

    def updateAccentButtons(self):
        for i, btn in enumerate(self._accent_buttons):
            color = self._accent_colors[i] if i < len(self._accent_colors) else QColor()
            btn._color = color
            btn.setChecked(i == self._current_accent_index)
            btn.update()

    def _on_accent_button_clicked(self, button_id):
        if button_id < 0 or button_id >= len(self._accent_colors):
            return
        self._current_accent_index = button_id
        self.updateAccentButtons()
        self.accentColorChanged.emit(self._accent_colors[button_id])


# =============================================================================
# ExMessageBox —— WinUI3 ContentDialog 风格消息框（exmessagebox.cpp 移植）
# =============================================================================

# WinUI 3 ContentDialog 设计常量
_MSG_CORNER_RADIUS = 8
_MSG_PADDING = 16
_MSG_TITLE_CONTENT_GAP = 12
_MSG_CONTENT_BUTTON_GAP = 16
_MSG_BUTTON_SPACING = 8
_MSG_TITLE_FONT_PX = 20
_MSG_BODY_FONT_PX = 14
_MSG_INFORMATIVE_FONT_PX = 13
_MSG_SHADOW_MARGIN = 8
_MSG_DIALOG_MIN_WIDTH = 320
_MSG_DIALOG_MAX_WIDTH = 548


class ExMessageBox(QMessageBox):
    """WinUI3 ContentDialog 风格的消息框：无边框 + 手绘圆角卡片/阴影 + 遮罩。"""

    def __init__(self, *args):
        # 支持 ExMessageBox(parent) 与 ExMessageBox(icon, title, text, buttons, parent)
        parent = None
        if len(args) == 1 and isinstance(args[0], QWidget):
            super().__init__(args[0])
        elif len(args) >= 4:
            super().__init__(args[0], args[1], args[2], args[3],
                             args[4] if len(args) > 4 else None)
        else:
            super().__init__()
        self._card_widget = None
        self._button_box = None
        self._button_area = None
        self._custom_content_widget = None
        self._overlay = None
        self._overlay_parent = None
        self._center_buttons = True
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.setAttribute(Qt.WA_TranslucentBackground)

    # ---- 自定义内容 ----
    def setContentWidget(self, widget):
        self._custom_content_widget = widget

    def setCenterButtons(self, center):
        self._center_buttons = center

    def centerButtons(self):
        return self._center_buttons

    # ---- 布局重建 ----
    def _reset_layout(self):
        icon_label = self.findChild(QLabel, "qt_msgboxex_icon_label")
        text_label = self.findChild(QLabel, "qt_msgbox_label")
        info_label = self.findChild(QLabel, "qt_msgbox_informativelabel")
        button_box = self.findChild(QDialogButtonBox, "qt_msgbox_buttonbox")

        if text_label is None or button_box is None:
            return
        if self._card_widget is not None:
            return

        # 删除 QMessageBox 默认布局（对应 C++ 的 delete q->layout()；
        # 不能用 QWidget().setLayout() 的技巧——那会把子控件一并过户销毁）
        if self.layout() is not None:
            from PyQt5 import sip
            sip.delete(self.layout())

        outer_layout = QVBoxLayout(self)
        outer_layout.setObjectName("OuterLayout")
        outer_layout.setContentsMargins(_MSG_SHADOW_MARGIN, _MSG_SHADOW_MARGIN,
                                        _MSG_SHADOW_MARGIN, _MSG_SHADOW_MARGIN)
        outer_layout.setSpacing(0)

        self._card_widget = QWidget(self)
        self._card_widget.setObjectName("FluentMessageBoxCard")
        outer_layout.addWidget(self._card_widget)

        inner_layout = QVBoxLayout(self._card_widget)
        inner_layout.setObjectName("CardInnerLayout")
        inner_layout.setContentsMargins(_MSG_PADDING, _MSG_PADDING, _MSG_PADDING, 0)
        inner_layout.setSpacing(0)

        if not self.windowTitle():
            self.setWindowTitle(QApplication.applicationName())
        title_label = QLabel(self.windowTitle(), self._card_widget)
        title_label.setObjectName("FluentMessageBoxTitle")
        title_label.setWordWrap(True)
        title_font = title_label.font()
        title_font.setPixelSize(_MSG_TITLE_FONT_PX)
        title_font.setWeight(QFont.DemiBold)
        title_label.setFont(title_font)
        inner_layout.addWidget(title_label)
        inner_layout.addSpacing(_MSG_TITLE_CONTENT_GAP)

        text_font = text_label.font()
        text_font.setHintingPreference(QFont.PreferNoHinting)
        text_font.setPixelSize(_MSG_BODY_FONT_PX)
        text_label.setFont(text_font)
        text_label.setWordWrap(True)

        has_icon = icon_label is not None and icon_label.pixmap() is not None and not icon_label.pixmap().isNull()
        if has_icon:
            from PyQt5.QtWidgets import QHBoxLayout as _HBL
            content_row = _HBL()
            content_row.setSpacing(12)
            content_row.addWidget(icon_label, 0, Qt.AlignVCenter)
            content_row.addWidget(text_label, 1)
            inner_layout.addLayout(content_row)
        else:
            inner_layout.addWidget(text_label)
            if icon_label is not None:
                icon_label.hide()
        if icon_label is not None:
            icon_label.setParent(self._card_widget)
        text_label.setParent(self._card_widget)

        if info_label is not None:
            info_font = info_label.font()
            info_font.setHintingPreference(QFont.PreferNoHinting)
            info_font.setPixelSize(_MSG_INFORMATIVE_FONT_PX)
            info_label.setFont(info_font)
            info_label.setContentsMargins(0, 7, 0, 0)
            inner_layout.addWidget(info_label)

        from PyQt5.QtWidgets import QCheckBox as _QCB
        check_box = self.findChild(_QCB)
        if check_box is not None:
            cb_font = check_box.font()
            cb_font.setHintingPreference(QFont.PreferNoHinting)
            check_box.setFont(cb_font)
            check_box.setContentsMargins(0, 7, 0, 0)
            check_box.setParent(self._card_widget)
            inner_layout.addWidget(check_box)

        for w in self.findChildren(QWidget):
            if w.inherits("QMessageBoxDetailsText"):
                inner_layout.addWidget(w)

        if self._custom_content_widget is not None:
            self._custom_content_widget.setParent(self._card_widget)
            inner_layout.addWidget(self._custom_content_widget)

        inner_layout.addSpacing(_MSG_CONTENT_BUTTON_GAP)

        from PyQt5.QtWidgets import QHBoxLayout as _HBL2
        button_area = _HBL2()
        button_area.setObjectName("ButtonAreaLayout")
        if self._center_buttons:
            button_area.addStretch()
        button_area.setSpacing(_MSG_BUTTON_SPACING)
        button_area.setContentsMargins(0, 12, 0, 12)

        button_box.setParent(self._card_widget)
        for ab in button_box.buttons():
            pb = ab
            f = pb.font()
            f.setHintingPreference(QFont.PreferNoHinting)
            f.setPixelSize(max(1, (f.pixelSize() if f.pixelSize() > 0 else 13) + 1))
            pb.setFont(f)
            pb.setDefault(False)
            ab.setMinimumWidth(120)

        # QDialogButtonBox 内部限制了按钮布局，取出后强制布局
        box_layout = button_box.layout()
        if box_layout is not None:
            while True:
                item = box_layout.takeAt(0)
                if item is None:
                    break
                w = item.widget()
                if w is not None:
                    button_area.addWidget(w, 0, Qt.AlignVCenter)
        else:
            button_area.addWidget(button_box)

        if self._center_buttons:
            button_area.addStretch()
        button_box.hide()

        inner_layout.addLayout(button_area)
        self._button_box = button_box
        self._button_area = button_area

        self.setMinimumWidth(_MSG_DIALOG_MIN_WIDTH + 2 * _MSG_SHADOW_MARGIN)
        self.setMaximumWidth(_MSG_DIALOG_MAX_WIDTH + 2 * _MSG_SHADOW_MARGIN)

    # ---- 遮罩 ----
    def _show_overlay(self):
        top_level = self.parentWidget() or QApplication.activeWindow()
        if top_level is None:
            return
        while top_level.parentWidget() is not None:
            top_level = top_level.parentWidget()

        if self._overlay is None:
            self._overlay = QWidget(top_level)
            self._overlay.setObjectName("ExMessageBoxOverlay")
            self._overlay.setAttribute(Qt.WA_StyledBackground, True)
            # WinUI 3 SmokeFillColorDefault
            self._overlay.setStyleSheet("background-color: rgba(0, 0, 0, 77);")
            self._overlay_parent = top_level
            top_level.installEventFilter(self)
        self._overlay.setGeometry(top_level.rect())
        self._overlay.show()
        self._overlay.raise_()

    def _hide_overlay(self):
        if self._overlay is not None:
            if self._overlay_parent is not None:
                self._overlay_parent.removeEventFilter(self)
                self._overlay_parent = None
            self._overlay.hide()
            self._overlay.deleteLater()
            self._overlay = None

    # ---- 执行 ----
    def exec_(self):
        self._show_overlay()
        result = QDialog.exec_(self)
        self._hide_overlay()
        return result

    def setVisible(self, visible):
        if visible:
            self._reset_layout()
            self._show_overlay()
        else:
            self._hide_overlay()
        QMessageBox.setVisible(self, visible)

    def setDetailedText(self, text):
        QMessageBox.setDetailedText(self, text)
        for btn in self.findChildren(QPushButton):
            if btn.inherits("DetailButton"):
                btn.clicked.connect(self.adjustSize)

    # ---- 绘制：柔和阴影 + 圆角卡片 + 上下分区底色 + 边框 ----
    def paintEvent(self, event):
        if self._card_widget is None:
            return
        from PyQt5.QtGui import QPainterPath as _QPainterPath

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        card_rect = QRect(self.rect())
        card_rect.adjust(_MSG_SHADOW_MARGIN, _MSG_SHADOW_MARGIN,
                         -_MSG_SHADOW_MARGIN, -_MSG_SHADOW_MARGIN)

        dark = QApplication.palette().window().color().lightness() < 128

        painter.setPen(Qt.NoPen)
        layers = 4
        for i in range(layers, 0, -1):
            expand = i * 1.5
            alpha = 6 + (layers - i) * 4 if dark else 3 + (layers - i) * 2
            sr = QRectF(card_rect.adjusted(int(-expand), int(-expand + 1),
                                           int(expand), int(expand + 1)))
            sp = _QPainterPath()
            sp.addRoundedRect(sr, _MSG_CORNER_RADIUS + expand, _MSG_CORNER_RADIUS + expand)
            painter.setBrush(QColor(0, 0, 0, alpha))
            painter.drawPath(sp)

        path = _QPainterPath()
        path.addRoundedRect(QRectF(card_rect), _MSG_CORNER_RADIUS, _MSG_CORNER_RADIUS)
        painter.setClipPath(path)

        if self._button_area is not None:
            mapped_top_left = self._button_area.parentWidget().mapTo(
                self, self._button_area.geometry().topLeft())
            split_y = mapped_top_left.y()
        else:
            split_y = card_rect.bottom()

        top_area = QRect(card_rect)
        top_area.setBottom(split_y)
        painter.fillRect(top_area, self.palette().base() if dark else Qt.white)

        bottom_area = QRect(card_rect)
        bottom_area.setTop(split_y)
        painter.fillRect(bottom_area, self.palette().window())

        painter.setClipping(False)
        border_color = QColor(255, 255, 255, 20) if dark else QColor(0, 0, 0, 15)
        painter.setPen(QPen(border_color, 1.0))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(QRectF(card_rect).adjusted(0.5, 0.5, -0.5, -0.5),
                                _MSG_CORNER_RADIUS, _MSG_CORNER_RADIUS)

    # 拦截 QMessageBox 的尺寸调整逻辑
    def showEvent(self, event):
        QDialog.showEvent(self, event)

    def resizeEvent(self, event):
        QDialog.resizeEvent(self, event)

    def event(self, e):
        if e.type() == QEvent.LayoutRequest:
            return QDialog.event(self, e)
        return QMessageBox.event(self, e)

    def eventFilter(self, watched, event):
        if self._overlay is not None and event.type() == QEvent.Resize:
            if isinstance(watched, QWidget):
                self._overlay.setGeometry(watched.rect())
        return QMessageBox.eventFilter(self, watched, event)

    # ---- 静态便捷接口 ----
    @staticmethod
    def information(parent, title, text, buttons=QMessageBox.Ok, default_button=QMessageBox.NoButton):
        box = ExMessageBox(QMessageBox.Information, title, text, buttons, parent)
        if default_button != QMessageBox.NoButton:
            box.setDefaultButton(default_button)
        return QMessageBox.StandardButton(box.exec_())

    @staticmethod
    def warning(parent, title, text, buttons=QMessageBox.Ok, default_button=QMessageBox.NoButton):
        box = ExMessageBox(QMessageBox.Warning, title, text, buttons, parent)
        if default_button != QMessageBox.NoButton:
            box.setDefaultButton(default_button)
        return QMessageBox.StandardButton(box.exec_())

    @staticmethod
    def critical(parent, title, text, buttons=QMessageBox.Ok, default_button=QMessageBox.NoButton):
        box = ExMessageBox(QMessageBox.Critical, title, text, buttons, parent)
        if default_button != QMessageBox.NoButton:
            box.setDefaultButton(default_button)
        return QMessageBox.StandardButton(box.exec_())

    @staticmethod
    def question(parent, title, text, buttons=QMessageBox.Yes | QMessageBox.No,
                 default_button=QMessageBox.NoButton):
        box = ExMessageBox(QMessageBox.Question, title, text, buttons, parent)
        if default_button != QMessageBox.NoButton:
            box.setDefaultButton(default_button)
        return QMessageBox.StandardButton(box.exec_())


# =============================================================================
# ExExpander —— 简版折叠面板（设置页强调色卡片使用）
# ExExpander —— 折叠面板（ExWidgets/controls/exexpander.cpp 的 1:1 移植）
# Header 与 Content 自绘为连续的白色圆角卡片；chevron 按钮区带悬停高亮，
# 箭头随展开进度旋转 180°；展开动画 167ms OutCubic（裁剪视口方案）。
# =============================================================================

# 设计常量（同 exexpander.cpp 匿名命名空间）
_EXP_CORNER_RADIUS = 4
_EXPANDER_MIN_WIDTH = 96
_EXP_HEADER_MIN_HEIGHT = 48
_EXP_HEADER_CONTENT_PADDING = 16
_EXP_CONTENT_PADDING = 16
_EXP_CHEVRON_CONTENT_SPACING = 20
_EXP_CHEVRON_TRAILING_MARGIN = 8
_EXP_CHEVRON_BUTTON_SIZE = 32


def _exp_is_dark_palette(palette):
    app = QApplication.instance()
    if app is not None:
        color_scheme = app.property("_q_colorscheme")
        if color_scheme is not None:
            return int(color_scheme) == 1
    return palette.color(QPalette.Window).lightness() < 128


def _exp_card_background(palette):
    """winUI3CardBackgroundColor 的等价实现（普通模式预合成到不透明）。"""
    dark = _exp_is_dark_palette(palette)
    wallpaper_mode = False
    app = QApplication.instance()
    if app is not None:
        mode = app.property("_q_widget_mode")
        wallpaper_mode = mode is not None and int(mode) >= 1

    base = QColor(palette.color(QPalette.Base))
    if base.alpha() == 0:
        base = QColor(palette.color(QPalette.Window))
    if base.alpha() == 0:
        base = QColor(0x1E, 0x1E, 0x1E) if dark else QColor(0xFF, 0xFF, 0xFF)

    card = QColor(255, 255, 255, 13) if dark else QColor(255, 255, 255, 179)
    if card.alpha() == 255:
        return QColor(card)

    alpha = card.alphaF()
    result = QColor(round(base.red() * (1.0 - alpha) + card.red() * alpha),
                    round(base.green() * (1.0 - alpha) + card.green() * alpha),
                    round(base.blue() * (1.0 - alpha) + card.blue() * alpha))
    if wallpaper_mode:
        result.setAlpha(max(72 if dark else 92, min(160, base.alpha())))
    return result


def _exp_card_border(palette):
    # cardStrokeColorBalanced
    return QColor(0x25, 0x25, 0x25) if _exp_is_dark_palette(palette) else QColor(0xE9, 0xE9, 0xE9)


def _exp_chevron_button_background(palette, is_down):
    # subtlePressedColor / subtleHighlightColor
    if _exp_is_dark_palette(palette):
        return QColor(255, 255, 255, 11) if is_down else QColor(255, 255, 255, 15)
    return QColor(0, 0, 0, 14) if is_down else QColor(0, 0, 0, 10)


def _exp_rounded_panel_path(rect, round_top_left, round_top_right, round_bottom_right, round_bottom_left):
    from PyQt5.QtGui import QPainterPath

    radius = min(float(_EXP_CORNER_RADIUS), min(rect.width(), rect.height()) * 0.5)
    path = QPainterPath()
    path.moveTo(rect.left() + (radius if round_top_left else 0.0), rect.top())
    path.lineTo(rect.right() - (radius if round_top_right else 0.0), rect.top())
    if round_top_right:
        path.quadTo(rect.right(), rect.top(), rect.right(), rect.top() + radius)
    else:
        path.lineTo(rect.right(), rect.top())
    path.lineTo(rect.right(), rect.bottom() - (radius if round_bottom_right else 0.0))
    if round_bottom_right:
        path.quadTo(rect.right(), rect.bottom(), rect.right() - radius, rect.bottom())
    else:
        path.lineTo(rect.right(), rect.bottom())
    path.lineTo(rect.left() + (radius if round_bottom_left else 0.0), rect.bottom())
    if round_bottom_left:
        path.quadTo(rect.left(), rect.bottom(), rect.left(), rect.bottom() - radius)
    else:
        path.lineTo(rect.left(), rect.bottom())
    path.lineTo(rect.left(), rect.top() + (radius if round_top_left else 0.0))
    if round_top_left:
        path.quadTo(rect.left(), rect.top(), rect.left() + radius, rect.top())
    else:
        path.lineTo(rect.left(), rect.top())
    path.closeSubpath()
    return path


class _ExpanderContentPanel(QWidget):
    """Content 面板：与 Header 组成连续容器，只有最远端保留外圆角。"""

    def __init__(self, expander, content):
        super().__init__(expander)
        self._expander = expander
        self._outer_edge = False
        self.setMinimumHeight(_EXP_HEADER_MIN_HEIGHT)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(_EXP_CONTENT_PADDING, _EXP_CONTENT_PADDING,
                                  _EXP_CONTENT_PADDING, _EXP_CONTENT_PADDING)
        layout.setSpacing(0)
        content.setParent(self)
        layout.addWidget(content)
        content.show()

    def setOuterEdge(self, outer_edge):
        if self._outer_edge == outer_edge:
            return
        self._outer_edge = outer_edge
        self.update()

    def paintEvent(self, event):
        from PyQt5.QtGui import QPainterPath

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        bounds = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        # 本移植仅支持向下展开（Down）：上边开放，下边在最外层面板时保留圆角
        fill_path = _exp_rounded_panel_path(bounds, False, False,
                                            self._outer_edge, self._outer_edge)
        painter.fillPath(fill_path, _exp_card_background(self.palette()))

        # 只绘制左右边与远离 Header 的横边（该横边同时是分隔线）
        border_path = QPainterPath()
        border_path.moveTo(bounds.left(), bounds.top())
        border_path.lineTo(bounds.left(),
                           bounds.bottom() - (_EXP_CORNER_RADIUS if self._outer_edge else 0))
        if self._outer_edge:
            border_path.quadTo(bounds.left(), bounds.bottom(),
                               bounds.left() + _EXP_CORNER_RADIUS, bounds.bottom())
        else:
            border_path.lineTo(bounds.left(), bounds.bottom())
        border_path.lineTo(bounds.right() - (_EXP_CORNER_RADIUS if self._outer_edge else 0),
                           bounds.bottom())
        if self._outer_edge:
            border_path.quadTo(bounds.right(), bounds.bottom(),
                               bounds.right(), bounds.bottom() - _EXP_CORNER_RADIUS)
        else:
            border_path.lineTo(bounds.right(), bounds.bottom())
        border_path.lineTo(bounds.right(), bounds.top())
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(_exp_card_border(self.palette()), 1.0))
        painter.drawPath(border_path)


class _ExpanderContentStack(QWidget):
    def __init__(self, expander):
        super().__init__(expander)
        self.setMinimumWidth(_EXPANDER_MIN_WIDTH)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)


class _ExpanderContentViewport(QWidget):
    """外层视口：展开时一次性占满高度，动画只改变内部裁剪窗口。"""

    def __init__(self, expander, panel):
        super().__init__(expander)
        self._expander = expander
        self._clip_viewport = QWidget(self)
        self._panel = panel
        self.setMinimumWidth(_EXPANDER_MIN_WIDTH)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        panel.setParent(self._clip_viewport)
        panel.installEventFilter(self)
        self._clip_viewport.show()
        panel.show()
        self._full_height = 0
        self._viewport_progress = 0.0

    def prepareAnimation(self):
        self._set_full_height(self._full_panel_height())
        self._update_panel_geometry()

    def setViewportProgress(self, progress):
        self._viewport_progress = max(0.0, min(1.0, progress))
        self._update_layout_height()
        self._update_panel_geometry()

    def sizeHint(self):
        result = self._panel.sizeHint().expandedTo(QSize(_EXPANDER_MIN_WIDTH, 0))
        result.setHeight(self._layout_height())
        return result

    def minimumSizeHint(self):
        return QSize(_EXPANDER_MIN_WIDTH, 0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if event.oldSize().width() != event.size().width():
            self._set_full_height(self._full_panel_height())
        self._update_panel_geometry()

    def eventFilter(self, watched, event):
        if (watched is self._panel and event.type() == QEvent.LayoutRequest
                and self._expander._expansion_animation.state() != QVariantAnimation.Running):
            self.prepareAnimation()
        return super().eventFilter(watched, event)

    def _layout_height(self):
        if self._expander.isExpanded():
            return self._full_height
        return round(self._full_height * self._viewport_progress)

    def _set_full_height(self, height):
        height = max(0, height)
        if self._full_height == height:
            # expanded 状态可能刚切换，布局高度计算方式已变
            self._update_layout_height()
            return
        self._full_height = height
        self._update_layout_height()

    def _update_layout_height(self):
        height = self._layout_height()
        if self.maximumHeight() == height:
            return
        self.setMaximumHeight(height)
        self.updateGeometry()
        self._expander._root_layout.invalidate()
        self._expander.updateGeometry()

    def _full_panel_height(self):
        return max(0, self._panel.sizeHint().height())

    def _update_panel_geometry(self):
        visible_height = round(self._full_height * self._viewport_progress)
        clip_geometry = QRect(0, 0, self.width(), visible_height)
        if self._clip_viewport.geometry() != clip_geometry:
            self._clip_viewport.setGeometry(clip_geometry)
        panel_geometry = QRect(0, 0, self.width(), self._full_height)
        if self._panel.geometry() != panel_geometry:
            self._panel.setGeometry(panel_geometry)


class _ExpanderHeaderButton(QAbstractButton):
    def __init__(self, expander):
        super().__init__(expander)
        self._expander = expander
        self._progress = 0.0
        self._header_widget = None
        self.setCheckable(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(_EXPANDER_MIN_WIDTH, _EXP_HEADER_MIN_HEIGHT)
        # Header 只采用自身内容高度，不参与 Content 的展开/收起动画
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setAttribute(Qt.WA_Hover, True)

        self._layout = QHBoxLayout(self)
        self._layout.setSpacing(0)
        self._update_layout_margins()

        self._label = QLabel(self)
        self._label.setWordWrap(True)
        self._label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._layout.addWidget(self._label, 1)

    def setHeader(self, text):
        self._label.setText(text)
        self._label.setVisible(self._header_widget is None and bool(text))
        self.updateGeometry()

    def setHeaderWidget(self, widget):
        if self._header_widget is widget:
            self._label.setVisible(widget is None and bool(self._label.text()))
            return
        if self._header_widget is not None:
            self._layout.removeWidget(self._header_widget)
            self._header_widget.setParent(None)
        self._header_widget = widget
        if widget is not None:
            widget.setParent(self)
            self._layout.addWidget(widget, 1)
            widget.show()
        self._label.setVisible(widget is None and bool(self._label.text()))
        self.updateGeometry()

    def takeHeaderWidget(self):
        widget = self._header_widget
        if widget is not None:
            self._layout.removeWidget(widget)
            widget.setParent(None)
            self._header_widget = None
            self._label.setVisible(bool(self._label.text()))
            self.updateGeometry()
        return widget

    def headerWidgetDestroyed(self):
        self._header_widget = None
        self._label.setVisible(bool(self._label.text()))
        self.updateGeometry()

    def setExpansionProgress(self, progress):
        self._progress = max(0.0, min(1.0, progress))
        self.update()

    def event(self, event):
        result = super().event(event)
        if event.type() in (QEvent.Enter, QEvent.Leave, QEvent.HoverEnter, QEvent.HoverLeave,
                            QEvent.EnabledChange, QEvent.LayoutDirectionChange):
            if event.type() == QEvent.LayoutDirectionChange:
                self._update_layout_margins()
            self.update()
        return result

    def paintEvent(self, event):
        from PyQt5.QtGui import QPainterPath
        from PyQt5.QtWidgets import QStyle, QStyleOptionFocusRect

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        connected = self._expander.isExpanded() and self._expander.hasContentWidgets()
        # 向下展开：顶部圆角；底部在未连接内容时保留圆角
        bounds = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        header_path = _exp_rounded_panel_path(bounds, True, True, not connected, not connected)
        painter.fillPath(header_path, _exp_card_background(self.palette()))
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(_exp_card_border(self.palette()), 1.0))
        painter.drawPath(header_path)

        # chevron 按钮区（悬停/按下时 subtle 高亮）
        rtl = self.layoutDirection() == Qt.RightToLeft
        chevron_x = (_EXP_CHEVRON_TRAILING_MARGIN if rtl
                     else self.width() - _EXP_CHEVRON_TRAILING_MARGIN - _EXP_CHEVRON_BUTTON_SIZE)
        chevron_rect = QRectF(chevron_x, (self.height() - _EXP_CHEVRON_BUTTON_SIZE) * 0.5,
                              _EXP_CHEVRON_BUTTON_SIZE, _EXP_CHEVRON_BUTTON_SIZE)
        if self.isEnabled() and (self.underMouse() or self.isDown()):
            painter.setPen(Qt.NoPen)
            painter.setBrush(_exp_chevron_button_background(self.palette(), self.isDown()))
            painter.drawRoundedRect(chevron_rect, _EXP_CORNER_RADIUS, _EXP_CORNER_RADIUS)

        # chevron 图标随展开进度旋转 180°
        angle = 180.0 * self._progress
        painter.save()
        painter.translate(chevron_rect.center())
        painter.rotate(angle)
        painter.setPen(self.palette().color(
            QPalette.Active if self.isEnabled() else QPalette.Disabled, QPalette.Text))
        icon_font = QFont("Segoe Fluent Icons")
        icon_font.setPixelSize(15)
        painter.setFont(icon_font)
        glyph_rect = QRectF(-_EXP_CHEVRON_BUTTON_SIZE * 0.5, -_EXP_CHEVRON_BUTTON_SIZE * 0.5,
                            _EXP_CHEVRON_BUTTON_SIZE, _EXP_CHEVRON_BUTTON_SIZE)
        painter.drawText(glyph_rect, Qt.AlignCenter, ICON_CHEVRON_DOWN_MED)
        painter.restore()

        if self.hasFocus():
            option = QStyleOptionFocusRect()
            option.initFrom(self)
            option.rect = self.rect().adjusted(3, 3, -3, -3)
            option.backgroundColor = self.palette().color(QPalette.Window)
            self.style().drawPrimitive(QStyle.PE_FrameFocusRect, option, painter, self)

    def _update_layout_margins(self):
        chevron_side = (_EXP_CHEVRON_CONTENT_SPACING + _EXP_CHEVRON_BUTTON_SIZE
                        + _EXP_CHEVRON_TRAILING_MARGIN)
        if self.layoutDirection() == Qt.RightToLeft:
            self._layout.setContentsMargins(chevron_side, 0, _EXP_HEADER_CONTENT_PADDING, 0)
        else:
            self._layout.setContentsMargins(_EXP_HEADER_CONTENT_PADDING, 0, chevron_side, 0)


class ExExpander(QWidget):
    """折叠面板（对应 C++ ExWidgets/controls/exexpander.cpp，仅支持向下展开）。"""

    expanding = pyqtSignal()
    collapsed = pyqtSignal()
    expandedChanged = pyqtSignal(bool)
    expansionFinished = pyqtSignal(bool)
    headerChanged = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._expanded = False
        self._expand_direction = "down"
        self._animation_enabled = True
        self._animation_duration = 167
        self._expansion_progress = 0.0
        self._header = ""
        self._header_widget = None
        self._content_widgets = []
        self._content_panels = []

        self._root_layout = QVBoxLayout(self)
        self._root_layout.setContentsMargins(0, 0, 0, 0)
        self._root_layout.setSpacing(0)

        self._header_button = _ExpanderHeaderButton(self)
        self._content_stack = _ExpanderContentStack(self)
        self._content_layout = QVBoxLayout(self._content_stack)
        self._content_container = _ExpanderContentViewport(self, self._content_stack)

        self._expansion_animation = QVariantAnimation(self)

        self.setMinimumWidth(_EXPANDER_MIN_WIDTH)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)

        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(0)
        self._content_container.prepareAnimation()
        self._content_container.setViewportProgress(0.0)
        self._content_container.hide()

        self._rebuild_layout()

        self._header_button.clicked.connect(self.toggle)
        self._expansion_animation.valueChanged.connect(self._on_animation_value)
        self._expansion_animation.finished.connect(self._finish_transition)

    # ---- 状态 ----
    def header(self):
        return self._header

    def setHeader(self, header):
        if self._header == header:
            return
        self._header = header
        self._header_button.setHeader(header)
        self.headerChanged.emit(header)

    def isExpanded(self):
        return self._expanded

    def expandDirection(self):
        return self._expand_direction

    def animationDuration(self):
        return self._animation_duration

    def setAnimationDuration(self, duration):
        self._animation_duration = max(0, duration)

    def isAnimationEnabled(self):
        return self._animation_enabled

    def setAnimationEnabled(self, enabled):
        self._animation_enabled = enabled
        if not enabled and self._expansion_animation.state() == QVariantAnimation.Running:
            self._expansion_animation.stop()
            self._finish_transition()

    def headerWidget(self):
        return self._header_widget

    def setHeaderWidget(self, widget):
        if widget in (self, self._header_button, self._content_container, self._content_stack):
            return
        if self._header_widget is not None:
            self._header_button.takeHeaderWidget()
        self._header_button.setHeaderWidget(widget)
        self._header_widget = widget
        self.updateGeometry()

    def takeHeaderWidget(self):
        widget = self._header_button.takeHeaderWidget()
        self._header_widget = None
        self.updateGeometry()
        return widget

    def contentWidgets(self):
        return list(self._content_widgets)

    def addContentWidget(self, widget):
        if widget is None or widget is self or widget is self._header_button:
            return
        if widget in self._content_widgets:
            return
        panel = _ExpanderContentPanel(self, widget)
        self._content_widgets.append(widget)
        self._content_panels.append(panel)
        self._rebuild_content_layout()
        self._refresh_content_geometry()

    def hasContentWidgets(self):
        return bool(self._content_panels)

    # ---- 展开/收起 ----
    def setExpanded(self, expanded):
        if self._expanded == expanded:
            return
        self._expanded = expanded
        self._header_button.setChecked(expanded)
        if expanded:
            self.expanding.emit()
        self.expandedChanged.emit(expanded)
        self._header_button.update()

        self._expansion_animation.stop()
        can_animate = (self._animation_enabled and self._animation_duration > 0
                       and self.parentWidget() is not None and self.parentWidget().isVisible())
        if not can_animate:
            self._expansion_progress = 1.0 if expanded else 0.0
            self._header_button.setExpansionProgress(self._expansion_progress)
            if expanded:
                self._content_container.setVisible(self.hasContentWidgets())
                self._content_stack.setVisible(self.hasContentWidgets())
                self._root_layout.activate()
            self._content_container.prepareAnimation()
            self._content_stack.setVisible(expanded and self.hasContentWidgets())
            self._content_container.setViewportProgress(self._expansion_progress)
            self._content_container.setVisible(expanded and self.hasContentWidgets())
            self.updateGeometry()
            if not expanded:
                self.collapsed.emit()
            self.expansionFinished.emit(expanded)
            return

        # 展开时外层视口先一次性进入最终布局，动画只改变内部裁剪窗口；
        # 收起时仍逐步回收布局高度，完成后再隐藏。
        self._content_container.setVisible(self.hasContentWidgets())
        self._content_stack.setVisible(self.hasContentWidgets())
        self._content_container.prepareAnimation()
        self._root_layout.activate()
        self._content_container.setViewportProgress(self._expansion_progress)

        if expanded:
            duration = max(1, self._animation_duration * 2 - 1)
            if self._expansion_progress < 1.0:
                self._expansion_animation.setDuration(
                    max(1, round(duration * (1.0 - self._expansion_progress))))
                self._expansion_animation.setEasingCurve(QEasingCurve.OutCubic)
                self._expansion_animation.setStartValue(self._expansion_progress)
                self._expansion_animation.setEndValue(1.0)
                self._expansion_animation.start()
            else:
                self._finish_transition()
            return

        if self._expansion_progress > 0.0:
            self._expansion_animation.setDuration(
                max(1, round(self._animation_duration * self._expansion_progress)))
            self._expansion_animation.setEasingCurve(QEasingCurve.OutCubic)
            self._expansion_animation.setStartValue(self._expansion_progress)
            self._expansion_animation.setEndValue(0.0)
            self._expansion_animation.start()
        else:
            self._finish_transition()

    def toggle(self):
        self.setExpanded(not self._expanded)

    def isAnimationRunning(self):
        return self._expansion_animation.state() == QVariantAnimation.Running

    # ---- 尺寸 ----
    def sizeHint(self):
        return self._root_layout.sizeHint()

    def minimumSizeHint(self):
        return self._root_layout.minimumSize()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.PaletteChange, QEvent.ApplicationPaletteChange,
                            QEvent.StyleChange, QEvent.LayoutDirectionChange, QEvent.EnabledChange):
            self._header_button.update()
            for panel in self._content_panels:
                panel.update()

    # ---- 内部 ----
    def _on_animation_value(self, value):
        self._expansion_progress = float(value)
        self._header_button.setExpansionProgress(self._expansion_progress)
        self._content_container.setViewportProgress(self._expansion_progress)

    def _rebuild_content_layout(self):
        for panel in self._content_panels:
            self._content_layout.removeWidget(panel)
            panel.setOuterEdge(False)
        if not self._content_panels:
            return
        for panel in self._content_panels:
            self._content_layout.addWidget(panel)
            panel.show()
        # 最后追加的 Content 距离 Header 最远，负责整体外圆角
        self._content_panels[-1].setOuterEdge(True)

    def _refresh_content_geometry(self):
        self._content_layout.activate()
        self._content_container.prepareAnimation()
        self._content_container.setViewportProgress(self._expansion_progress)
        visible = ((self._expanded or self._expansion_animation.state() == QVariantAnimation.Running)
                   and self.hasContentWidgets())
        self._content_stack.setVisible(visible)
        self._content_container.setVisible(visible)
        self._header_button.update()
        self.updateGeometry()

    def _rebuild_layout(self):
        self._root_layout.removeWidget(self._header_button)
        self._root_layout.removeWidget(self._content_container)
        self._root_layout.addWidget(self._header_button)
        self._root_layout.addWidget(self._content_container)

    def _finish_transition(self):
        self._expansion_progress = 1.0 if self._expanded else 0.0
        self._header_button.setExpansionProgress(self._expansion_progress)
        self._content_container.prepareAnimation()
        self._content_container.setViewportProgress(self._expansion_progress)
        self._content_stack.setVisible(self._expanded and self.hasContentWidgets())
        self._content_container.setVisible(self._expanded and self.hasContentWidgets())
        self.updateGeometry()
        if not self._expanded:
            self.collapsed.emit()
        self.expansionFinished.emit(self._expanded)
