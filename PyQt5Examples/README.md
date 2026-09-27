# FluentUI3 PyQt5 Gallery

以 C++ Gallery（`Examples/Gallery`）为蓝本的纯 PyQt5 移植版：不依赖任何 C++ 构建的
界面组件，界面布局复用 `Examples/Gallery/mainwindow.ui`（通过 `PyQt5.uic` 加载进
Python 子类 `GalleryWindow`），样式来自 Qt5 构建的 `FluentUI3StylePlugin.dll`。

## 运行

```bash
pip install -r requirements.txt   # PyQt5==5.15.11（自带 Qt 5.15.2）
python main.py
```

前置条件：

1. **样式插件**：把 Qt5 构建（与 PyQt5 自带 Qt 版本一致，即 5.15.x）、位数与
   Python 一致的 `FluentUI3StylePlugin.dll` 放入 `site-packages\PyQt5\Qt5\plugins\styles`，
   或本目录的 `plugins\styles`（`main.py` 会自动注册该目录）。
2. **资源**：`Examples/Gallery/mainwindow.ui`、`resources/`（背景图、图标、
   changelog）与 `font-icon/resource/SegoeFluentIconsEnum.txt` 需存在（相对路径引用）。

环境变量：`GALLERY_FRAMELESS=0` 可退回原生标题栏（默认启用无边框方案）。

## 与 C++ 实现的对应关系

| 本目录文件 | C++ 侧来源 |
| --- | --- |
| `main.py` | `main.cpp` + `MainWindow` 构造流程编排 |
| `gallerywindow.py` | `MainWindow::paintEvent`（背景图/DWM 材质）、`FluentWindowFrame`（无边框）、`installChromeHeader`、`loadChangelog` |
| `mainwindow.py` | `buildMainMenus`、`rebuildMenuAndToolBar`、`initializeNavigationView`、`applyThemeIndex/applyWidgetBgMode/applyAccentColor`、`updateActionIcons`、`setupAccentColorWidget`、`on_*` 槽、右键菜单图标 |
| `settings_page.py` | `setupSettingsPage`（WinUI3 设置卡片 + ExExpander） |
| `exstackedwidget.py` | `ExStackedWidget`（纵向滑页动画，InOutSine 300ms） |
| `exwidgets.py` | `ExTabWidget`、`ExNavTreeWidget`、`ExWinUINavigationView`、`ExTimeline`、`FluentTitleBar`、`ExExpander` |
| `basic_showcase.py` / `tab_showcase.py` / `table_showcase.py` | 基础页配置、`PageTab`、`PageInstalledSoftware` |
| `extra_pages.py` | `PageSegoeIconGallery`、`PageAbout`、`PageDialog`（标准对话框部分）、`PageChangelog`、`setupMdiArea` |
| `utils.py` | `createFluentIcon`、注册表软件枚举、DWM 深色标题栏、系统深浅色检测 |

### 无边框方案（替代 qwindowkit）

`GalleryWindow.nativeEvent` 采用与 qwindowkit 相同的技术：

- **`WM_NCCALCSIZE`**：先调 `DefWindowProcW` 让系统计算默认边框，再把整个顶部
  框架（标题栏+上边框）去掉——左/右/下保留系统边框，因此 DWM 阴影、1px 系统
  边框和 **Win11 圆角**都与原生窗口一致（这正是 C++ 版的观感来源）。
- **`WM_NCHITTEST`**：标题栏空白 = `HTCAPTION`（拖动），边缘 = 8 向缩放，
  其余交给 Qt。lParam 为物理像素，按 `devicePixelRatioF` 换算成 Qt 逻辑坐标。
- 首次显示时移除 `WS_SYSMENU`（mica/亚克力下防止原生按钮透出）并显式设置
  `DWMWA_WINDOW_CORNER_PREFERENCE = DWMWCP_ROUND`；右键标题栏弹自绘系统菜单。
- 最大化时客户区顶部按 `SM_CXSIZEFRAME + SM_CXPADDEDBORDER` 内缩回工作区，
  窗口尺寸恰好等于屏幕工作区。

> 退出说明：uic 加载的大控件树 + Python 重写的虚函数在解释器关闭阶段的析构顺序
> 存在竞态段错误（表现为退出时鼠标忙圈），因此 `main.py` 在事件循环结束后直接
> `os._exit()` 结束进程——实测 WM_CLOSE 后 32ms 干净退出。

### 与 PySide6 示例（PyExamples）的差异

| 差异点 | 说明 |
| --- | --- |
| UI 加载 | `QUiLoader` → `PyQt5.uic.loadUi`，加载进 `GalleryWindow(QMainWindow)` 子类（需要重写 `nativeEvent/paintEvent`）；`ExStackedWidget` 由 `exstackedwidget.py` 模块提供 |
| QAction | PyQt5 中位于 `PyQt5.QtWidgets`（PySide6 为 `QtGui`） |
| QLineEdit 尾部图标 | `QLineEdit.TrailingPosition`（PySide6 为 `QLineEdit.ActionPosition.TrailingPosition`） |
| 每控件强调色 | Qt5 无 `QPalette.Accent`（Qt 6.6+），Qt5 构建的样式由 `PaletteManager` 全局管理强调色（`_q_accent_color`），`changeAccentPalette` 为 no-op（与 C++ 一致） |
| 系统主题跟随 | Qt5 无 `QStyleHints::colorScheme`，启动时读注册表 `AppsUseLightTheme` 判断深浅色 |
| 图标项哈希 | PyQt5 的 `QTreeWidgetItem` 不可哈希，导航树用专用 `ExNavTreeWidget` 管理（码点存 `UserRole+1`） |

## 页面结构

- .ui 内置页（0-6）：基础控件 / 表格（已安装软件，懒加载）/ 列表 / 树 / TabBar 样式 / Mdi / 设置（WinUI3 卡片）
- 纯 Python 运行时页（7-10）：图标库（1403 个 Segoe Fluent Icons，Model-View-Delegate，点击复制编码）/ 关于 / 常用对话框 / 更新日志时间轴
- ExWidgets 子树及“系统监视”等 C++ 专属页面无对应实现，按 C++ 的条件逻辑自动跳过
- 右侧停靠窗口 `日志 And 提示`：加载 `resources/changelog.txt`（同 C++ `loadChangelog`）

## 主题相关 API

```python
app.setProperty("_q_colorscheme", 1)   # 0=浅色 1=暗色
app.setProperty("_q_themestyle", 0)    # 0=Fluent 配色 1=Teams 配色
app.setProperty("_q_accent_color", QColor("#881798"))
app.setProperty("_q_widget_mode", 1)   # 0=无 1=图片壁纸 2=DWM 亚克力
app.setStyle("FluentUI3")              # 修改上述属性后重新应用样式生效
```
