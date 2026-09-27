"""ExStackedWidget 的纯 PyQt5 移植（ExWidgets/controls/exstackedwidget.cpp）。

带滑动动画的 QStackedWidget：切页时把前后两页 render 成 QPixmap，
用两个透明 QLabel 覆盖层做平行位移动画，结束后切回真实页面。

mainwindow.ui 的 <customwidgets> 通过 <header>exstackedwidget.h</header>
引用该类；PyQt5 的 uic 会导入同名 Python 模块并取出 ExStackedWidget，
因此本模块文件名不能改动。
"""

from PyQt5.QtCore import QEasingCurve, QParallelAnimationGroup, QPoint, QPropertyAnimation, QRect, Qt
from PyQt5.QtGui import QPainter, QPalette, QPixmap, QRegion
from PyQt5.QtWidgets import QLabel, QStackedWidget, QWidget


class ExStackedWidget(QStackedWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._vertical_mode = True
        self._duration = 300
        self._curve = QEasingCurve.InOutCubic
        self._animating = False
        self._target_index = -1
        self._pending_index = -1
        self._current_overlay = None
        self._next_overlay = None
        self._animation_group = None

    # ---- 配置 ----
    def setVerticalMode(self, vertical):
        self._vertical_mode = vertical

    def verticalMode(self):
        return self._vertical_mode

    def setSpeed(self, duration):
        self._duration = max(0, duration)

    def speed(self):
        return self._duration

    def setAnimation(self, curve):
        self._curve = curve

    def animation(self):
        return self._curve

    # ---- 接口 ----
    def addWidget(self, w):
        w.setBackgroundRole(QPalette.Base)
        return super().addWidget(w)

    def setCurrentIndex(self, index):
        self.slideToIndex(index)

    def setCurrentWidget(self, widget):
        self.slideToIndex(self.indexOf(widget))

    # ---- 动画 ----
    def slideToIndex(self, index):
        if index < 0 or index >= self.count():
            return

        if self._animating:
            # 动画进行中不硬切，排队最新目标，结束后继续
            self._pending_index = -1 if index == self._target_index else index
            return

        current = QStackedWidget.currentIndex(self)
        if current == index:
            QStackedWidget.setCurrentIndex(self, index)
            return

        if not self.isVisible() or current < 0 or self._duration <= 0:
            QStackedWidget.setCurrentIndex(self, index)
            return

        current_widget = self.currentWidget()
        next_widget = self.widget(index)
        if not current_widget or not next_widget:
            QStackedWidget.setCurrentIndex(self, index)
            return

        # QStackedWidget 是 QFrame，页面位于 contentsRect()；
        # 有边框时 rect() 的起点非零，直接用会让覆盖层错位
        area = self.contentsRect()
        if area.isEmpty():
            QStackedWidget.setCurrentIndex(self, index)
            return

        current_widget.setGeometry(area)
        next_widget.setGeometry(area)

        def render_page(page):
            pixmap = QPixmap(area.size())
            painter = QPainter(pixmap)
            painter.fillRect(pixmap.rect(), page.palette().brush(page.backgroundRole()))
            page.render(painter, QPoint(), QRegion(), QWidget.DrawChildren)
            painter.end()
            return pixmap

        current_pixmap = render_page(current_widget)
        next_pixmap = render_page(next_widget)

        current_overlay = QLabel(self)
        current_overlay.setPixmap(current_pixmap)
        current_overlay.setScaledContents(False)
        current_overlay.setGeometry(area)
        current_overlay.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        current_overlay.show()
        current_overlay.raise_()

        next_overlay = QLabel(self)
        next_overlay.setPixmap(next_pixmap)
        next_overlay.setScaledContents(False)
        next_overlay.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        forward = index > current
        origin = area.topLeft()
        if self._vertical_mode:
            offset = area.height()
            current_end = origin + QPoint(0, -offset if forward else offset)
            next_start = origin + QPoint(0, offset if forward else -offset)
        else:
            offset = area.width()
            current_end = origin + QPoint(-offset if forward else offset, 0)
            next_start = origin + QPoint(offset if forward else -offset, 0)

        next_overlay.setGeometry(QRect(next_start, area.size()))
        next_overlay.show()
        next_overlay.raise_()

        current_widget.hide()
        next_widget.hide()

        current_animation = QPropertyAnimation(current_overlay, b"pos", self)
        current_animation.setDuration(self._duration)
        current_animation.setEasingCurve(self._curve)
        current_animation.setStartValue(origin)
        current_animation.setEndValue(current_end)

        next_animation = QPropertyAnimation(next_overlay, b"pos", self)
        next_animation.setDuration(self._duration)
        next_animation.setEasingCurve(self._curve)
        next_animation.setStartValue(next_start)
        next_animation.setEndValue(origin)

        group = QParallelAnimationGroup(self)
        group.addAnimation(current_animation)
        group.addAnimation(next_animation)

        self._animating = True
        self._target_index = index
        self._current_overlay = current_overlay
        self._next_overlay = next_overlay
        self._animation_group = group

        group.finished.connect(self.finishAnimation)
        group.start()

    def finishAnimation(self):
        if self._animation_group is not None:
            self._animation_group.stop()
            self._animation_group.deleteLater()
            self._animation_group = None

        if 0 <= self._target_index < self.count():
            QStackedWidget.setCurrentIndex(self, self._target_index)

        current = self.currentWidget()
        if current is not None:
            current.setGeometry(self.contentsRect())
            current.show()

        for attr in ("_current_overlay", "_next_overlay"):
            overlay = getattr(self, attr)
            if overlay is not None:
                overlay.hide()
                overlay.deleteLater()
                setattr(self, attr, None)

        self._animating = False
        self._target_index = -1

        if self._pending_index >= 0 and self._pending_index != self.currentIndex():
            next_index = self._pending_index
            self._pending_index = -1
            self.slideToIndex(next_index)
        else:
            self._pending_index = -1
