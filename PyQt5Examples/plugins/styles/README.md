可选的样式插件放置目录。

如果不想把 `FluentUI3StylePlugin.dll` 复制到 PyQt5 的安装目录
（`site-packages\PyQt5\Qt5\plugins\styles`），也可以把它放到本目录，
`main.py` 会通过 `QCoreApplication.addLibraryPath` 把本目录注册进去。

要求：
- DLL 必须是 Qt 5.15.x 构建（与 PyQt5 自带的 Qt 版本一致，否则无法加载）
- DLL 位数需与 Python 一致（64 位 Python 用 x64 DLL）
- 所依赖的 Qt 运行库（Qt5Widgets.dll 等）会由 PyQt5 自带的环境提供
