cmake_minimum_required(VERSION 3.16)

project(fluentw3uistyle VERSION 0.1 LANGUAGES CXX C)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTOUIC ON)
set(CMAKE_AUTORCC ON)
set(CMAKE_INCLUDE_CURRENT_DIR ON)

if(MSVC)
    # /utf-8: avoid C4819 when sources contain UTF-8 (e.g. Chinese comments) under CP936
    add_compile_options(/wd4273 /utf-8)

    # Keep Release optimized while retaining enough CodeView information for
    # post-mortem dump analysis. /Z7 avoids one shared compiler PDB becoming a
    # bottleneck under Ninja; the linker still emits the final target PDB.
    add_compile_options($<$<CONFIG:Release>:/Z7>)
    add_link_options(
        $<$<CONFIG:Release>:/DEBUG:FULL>
        $<$<CONFIG:Release>:/OPT:REF>
        $<$<CONFIG:Release>:/OPT:ICF>
    )
    message(STATUS "MSVC Release symbols    : enabled (/Z7, /DEBUG:FULL)")
endif()

find_package(QT NAMES Qt6 Qt5 REQUIRED COMPONENTS Core Gui Widgets Svg)
find_package(Qt${QT_VERSION_MAJOR} REQUIRED COMPONENTS
    Core
    Gui
    Widgets
    Svg
)

if(QT_VERSION_MAJOR EQUAL 6 AND QT_KNOWN_POLICY_QTP0002)
    qt_policy(SET QTP0002 NEW)
endif()

# Install into the Qt selected by the current Kit unless the caller explicitly
# supplied CMAKE_INSTALL_PREFIX. qmake is authoritative for both native Qt 5
# and Qt 6 layouts; the package directory is a fallback for unusual packages
# that do not expose the qmake target.
set(_qt_install_prefix "")
set(_qt_install_plugins "")
set(_qt_qmake_target "Qt${QT_VERSION_MAJOR}::qmake")
if(TARGET ${_qt_qmake_target})
    get_target_property(_qt_qmake_executable ${_qt_qmake_target} IMPORTED_LOCATION)
    if(_qt_qmake_executable AND EXISTS "${_qt_qmake_executable}")
        execute_process(
            COMMAND "${_qt_qmake_executable}" -query QT_INSTALL_PREFIX
            OUTPUT_VARIABLE _qt_install_prefix
            OUTPUT_STRIP_TRAILING_WHITESPACE
            ERROR_QUIET
        )
        execute_process(
            COMMAND "${_qt_qmake_executable}" -query QT_INSTALL_PLUGINS
            OUTPUT_VARIABLE _qt_install_plugins
            OUTPUT_STRIP_TRAILING_WHITESPACE
            ERROR_QUIET
        )
    endif()
endif()

if(NOT _qt_install_prefix)
    set(_qt_package_dir_variable "Qt${QT_VERSION_MAJOR}_DIR")
    set(_qt_package_dir "${${_qt_package_dir_variable}}")
    if(_qt_package_dir)
        get_filename_component(_qt_install_prefix "${_qt_package_dir}/../../.." ABSOLUTE)
    endif()
endif()

set(_legacy_default_install_prefix "${CMAKE_CURRENT_SOURCE_DIR}/install")
if(CMAKE_INSTALL_PREFIX_INITIALIZED_TO_DEFAULT
   OR "${CMAKE_INSTALL_PREFIX}" STREQUAL "${_legacy_default_install_prefix}")
    if(_qt_install_prefix)
        set(CMAKE_INSTALL_PREFIX "${_qt_install_prefix}" CACHE PATH "Install prefix" FORCE)
        set(_install_prefix_source "current Qt Kit")
    else()
        set(CMAKE_INSTALL_PREFIX "${CMAKE_CURRENT_SOURCE_DIR}/install" CACHE PATH "Install prefix" FORCE)
        set(_install_prefix_source "fallback project directory")
        message(WARNING "Unable to determine the Qt install prefix; using ${CMAKE_INSTALL_PREFIX}")
    endif()
else()
    set(_install_prefix_source "user or CMake cache")
endif()

set(_qt_plugins_install_dir "plugins")
if(_qt_install_prefix AND _qt_install_plugins)
    file(RELATIVE_PATH _qt_plugins_relative "${_qt_install_prefix}" "${_qt_install_plugins}")
    if(NOT _qt_plugins_relative MATCHES "^\\.\\.")
        set(_qt_plugins_install_dir "${_qt_plugins_relative}")
    endif()
endif()

include(GNUInstallDirs)

message(STATUS "Qt install prefix       : ${_qt_install_prefix}")
message(STATUS "CMake install prefix    : ${CMAKE_INSTALL_PREFIX} (${_install_prefix_source})")
message(STATUS "Install runtime binaries: ${CMAKE_INSTALL_PREFIX}/${CMAKE_INSTALL_BINDIR}")
message(STATUS "Install libraries       : ${CMAKE_INSTALL_PREFIX}/${CMAKE_INSTALL_LIBDIR}")
message(STATUS "Install headers         : ${CMAKE_INSTALL_PREFIX}/${CMAKE_INSTALL_INCLUDEDIR}")
message(STATUS "Qt style plugin install : ${CMAKE_INSTALL_PREFIX}/${_qt_plugins_install_dir}/styles")

# Qt 6.10+ private CMake packages are required when using <private/...> headers.
# Older Qt 6.x installs (e.g. 6.6) often omit them; do not require globally.
set(FLUENT_QT_PRIVATE_LIBS "")
if(QT_VERSION_MAJOR EQUAL 6 AND QT_VERSION VERSION_GREATER_EQUAL "6.10.0")
    find_package(Qt6 REQUIRED COMPONENTS CorePrivate GuiPrivate WidgetsPrivate)
    list(APPEND FLUENT_QT_PRIVATE_LIBS
        Qt6::CorePrivate
        Qt6::GuiPrivate
        Qt6::WidgetsPrivate
    )
endif()

# Local desktop runs: keep all configs in the same output dir (Windows/MSVC convenience).
# Android application targets are MODULE_LIBRARY targets. Keep their library output in
# each target's build directory so Qt Creator can find the adjacent deployment JSON.
# Optional components such as Frameless also inherit these paths.
set(_out_bin "${CMAKE_BINARY_DIR}/bin")
set(_out_lib "${CMAKE_BINARY_DIR}/lib")

set(CMAKE_RUNTIME_OUTPUT_DIRECTORY "${_out_bin}")
set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY "${_out_lib}")
set(CMAKE_PDB_OUTPUT_DIRECTORY "${_out_bin}")
if(NOT ANDROID)
    set(CMAKE_LIBRARY_OUTPUT_DIRECTORY "${_out_lib}")
endif()

foreach(_cfg DEBUG RELEASE RELWITHDEBINFO MINSIZEREL)
    set(CMAKE_RUNTIME_OUTPUT_DIRECTORY_${_cfg} "${_out_bin}")
    set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY_${_cfg} "${_out_lib}")
    set(CMAKE_PDB_OUTPUT_DIRECTORY_${_cfg} "${_out_bin}")
    if(NOT ANDROID)
        set(CMAKE_LIBRARY_OUTPUT_DIRECTORY_${_cfg} "${_out_lib}")
    endif()
endforeach()

option(BUILD_LIBRARY "Build as library" ON)
option(BUILD_PLUGIN "Build as plugin (Windows only)" ON)
option(BUILD_FRAMELESS "Build the QWindowKit-based frameless window component" ON)
option(BUILD_EXAMPLES "Build example applications" ON)
option(BUILD_QTCREATOR_PLUGIN "Build Qt Creator extension plugin" OFF)

# --- Legacy Windows support（仅 FluentUI3StylePlugin，无 YY-Thunks） ---
# 老系统兼容全部在编译/链接层完成，不做任何运行时 API 模拟：
#   Win7 = 64 位 MSVC + 静态 CRT(/MT) + 子系统 6.01
#     * 插件自身的 Win32 API 全为 Vista 时代（SRWLock 等 Vista+ 在 Win7 均可用）
#     * /MT 消除 vcruntime140/ucrtbase 依赖（Win7 无 SP 装不上 KB2999226，
#       14.41+ redist 只支持 Win10+）
#     * 源码层：std::chrono 改 QDateTime —— 静态 CRT 的 _Xtime_get_ticks
#       静态引用 Win8+ 的 GetSystemTimePreciseAsFileTime
#   WinXP = 32 位 MSVC + VC-LTL(msvcrt.dll 模式) + /Zc:threadSafeInit- + 子系统 5.01
#     * VC-LTL 把 CRT 重定向到 XP 自带的系统 msvcrt.dll —— 静态 UCRT 的启动
#       对象静态引用 Vista+ 的 FlsAlloc/InitializeCriticalSectionEx 等，XP 上必死
#     * /Zc:threadSafeInit- 去掉 magic static 的 SRWLock 守卫（XP 无 SRWLock）
#     * 源码层：dwmapi 改运行时动态解析（XP 无 dwmapi.dll）+ QDateTime（同上）
# 用法：
#   cmake -G "Visual Studio 17 2022" -A x64  -DFLUENTUI3_LEGACY_WINDOWS=Win7
#   cmake -G "Visual Studio 17 2022" -A Win32 -DFLUENTUI3_LEGACY_WINDOWS=WinXP
set(FLUENTUI3_LEGACY_WINDOWS "" CACHE STRING
    "Build FluentUI3StylePlugin for legacy Windows: WinXP (x86) / Win7 (x64); empty = off")
set_property(CACHE FLUENTUI3_LEGACY_WINDOWS PROPERTY STRINGS "" WinXP Win7)

if(FLUENTUI3_LEGACY_WINDOWS)
    if(NOT WIN32 OR NOT MSVC)
        message(FATAL_ERROR "FLUENTUI3_LEGACY_WINDOWS is only available with the MSVC toolchain")
    endif()
    if(FLUENTUI3_LEGACY_WINDOWS STREQUAL "Win7")
        if(NOT CMAKE_SIZEOF_VOID_P EQUAL 8)
            message(FATAL_ERROR "FLUENTUI3_LEGACY_WINDOWS=Win7 requires the 64-bit toolchain (-A x64)")
        endif()
        set(_legacy_subsystem "6.01")
    elseif(FLUENTUI3_LEGACY_WINDOWS STREQUAL "WinXP")
        if(NOT CMAKE_SIZEOF_VOID_P EQUAL 4)
            message(FATAL_ERROR "FLUENTUI3_LEGACY_WINDOWS=WinXP requires the 32-bit toolchain (-A Win32)")
        endif()
        # VC-LTL：同名 CRT 库前置查找路径，把 CRT 重定向到系统 msvcrt.dll
        set(WindowsTargetPlatformMinVersion "5.1.2600.0")
        include(FetchContent)
        FetchContent_Declare(vc_ltl
            URL https://github.com/Chuyu-Team/VC-LTL5/releases/download/v5.2.1/VC-LTL-Binary.7z
            URL_HASH SHA256=d37f2201bc32a56a3bc79b8e609281aab90973afbc9de3d7eaa3b030b102c9b7
            DOWNLOAD_EXTRACT_TIMESTAMP true)
        FetchContent_MakeAvailable(vc_ltl)
        include("${vc_ltl_SOURCE_DIR}/VC-LTL helper for cmake.cmake")
        set(_legacy_subsystem "5.01")
    else()
        message(FATAL_ERROR
            "FLUENTUI3_LEGACY_WINDOWS must be WinXP or Win7, got '${FLUENTUI3_LEGACY_WINDOWS}'")
    endif()
    # MSVC_RUNTIME_LIBRARY 属性在每个 target 创建时取值，必须在 add_subdirectory 之前设置。
    # WinXP 用 /MT 与 VC-LTL 的静态库形态（libucrt/libvcruntime）配对；Win7 直接全静态。
    set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
    message(STATUS "Legacy Windows target : ${FLUENTUI3_LEGACY_WINDOWS} "
                   "(subsystem ${_legacy_subsystem})")
endif()

if(NOT WIN32)
    set(BUILD_PLUGIN OFF)
endif()

# Android windows already use the Activity surface and must not install a desktop title bar.
if(ANDROID)
    set(BUILD_FRAMELESS OFF CACHE BOOL
        "Build the QWindowKit-based frameless window component" FORCE
    )
endif()

add_subdirectory(ExWidgets)

option(EXWIDGETS_BUILD_TESTS "构建 ExWidgets 控件回归测试" OFF)
if(EXWIDGETS_BUILD_TESTS)
    enable_testing()
    add_subdirectory(tests/ExWidgets)
endif()

if(BUILD_LIBRARY)
    add_subdirectory(fluentui3style)
endif()

if(BUILD_FRAMELESS)
    add_subdirectory(frameless)
endif()

if(BUILD_PLUGIN)
    add_subdirectory(fluentui3style/plugin)
endif()

if(BUILD_QTCREATOR_PLUGIN)
    add_subdirectory(QtCreatorPlugin)
endif()

if(BUILD_EXAMPLES)
    add_subdirectory(Examples)
endif()

# 老系统选项只挂到 FluentUI3StylePlugin（legacy 产物只发布该 DLL；
# EXE/静态库不在 legacy 产物里，无需处理）。
if(FLUENTUI3_LEGACY_WINDOWS AND TARGET FluentUI3StylePlugin)
    target_link_options(FluentUI3StylePlugin PRIVATE
        "/SUBSYSTEM:WINDOWS,${_legacy_subsystem}")
    set(_legacy_plugin_extra "")
    if(FLUENTUI3_LEGACY_WINDOWS STREQUAL "WinXP")
        # 关闭 magic static 的线程安全初始化：其 SRWLock 守卫在 XP 上不存在。
        # 样式插件仅由 GUI 线程使用，非线程安全初始化可接受。
        target_compile_options(FluentUI3StylePlugin PRIVATE "/Zc:threadSafeInit-")
        set(_legacy_plugin_extra ", /Zc:threadSafeInit-")
    endif()
    message(STATUS "Legacy plugin options  : FluentUI3StylePlugin "
                   "(subsystem ${_legacy_subsystem}${_legacy_plugin_extra})")
endif()

# --- Install (DLL / import lib / headers / CMake packages) ---
install(TARGETS ExWidgets
    EXPORT ExWidgetsTargets
    RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
    LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
    ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
)

if(MSVC)
    install(FILES $<TARGET_PDB_FILE:ExWidgets>
        DESTINATION ${CMAKE_INSTALL_BINDIR}
        OPTIONAL
    )
endif()

if(BUILD_LIBRARY)
    install(TARGETS FluentUI3Style
        EXPORT FluentUI3StyleTargets
        RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
        LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
        ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
    )

    if(MSVC)
        install(FILES $<TARGET_PDB_FILE:FluentUI3Style>
            DESTINATION ${CMAKE_INSTALL_BINDIR}
            OPTIONAL
        )
    endif()
endif()

install(DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/ExWidgets/"
    DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/ExWidgets
    FILES_MATCHING PATTERN "*.h"
)

install(DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/FluentUI3Colors/"
    DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/FluentUI3Colors
    FILES_MATCHING PATTERN "*.h"
)

if(TARGET Frameless)
    install(TARGETS Frameless
        EXPORT FramelessTargets
        ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
        INCLUDES DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/Frameless
    )
    install(DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/frameless/"
        DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/Frameless
        FILES_MATCHING PATTERN "*.h"
    )
endif()

if(BUILD_LIBRARY)
    install(DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/fluentui3style/"
        DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/FluentUI3Style
        FILES_MATCHING PATTERN "*.h"
        PATTERN "plugin" EXCLUDE
    )
endif()

include(CMakePackageConfigHelpers)

set(_cfg_dir "${CMAKE_CURRENT_BINARY_DIR}/cmake")
file(MAKE_DIRECTORY "${_cfg_dir}")

configure_package_config_file(
    "${CMAKE_CURRENT_SOURCE_DIR}/cmake/ExWidgetsConfig.cmake.in"
    "${_cfg_dir}/ExWidgetsConfig.cmake"
    INSTALL_DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/ExWidgets
)

write_basic_package_version_file(
    "${_cfg_dir}/ExWidgetsConfigVersion.cmake"
    VERSION ${PROJECT_VERSION}
    COMPATIBILITY SameMinorVersion
)

install(EXPORT ExWidgetsTargets
    FILE ExWidgetsTargets.cmake
    NAMESPACE ExWidgets::
    DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/ExWidgets
)

install(FILES
    "${_cfg_dir}/ExWidgetsConfig.cmake"
    "${_cfg_dir}/ExWidgetsConfigVersion.cmake"
    DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/ExWidgets
)

if(TARGET Frameless)
    configure_package_config_file(
        "${CMAKE_CURRENT_SOURCE_DIR}/cmake/FramelessConfig.cmake.in"
        "${_cfg_dir}/FramelessConfig.cmake"
        INSTALL_DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/Frameless
    )

    write_basic_package_version_file(
        "${_cfg_dir}/FramelessConfigVersion.cmake"
        VERSION ${PROJECT_VERSION}
        COMPATIBILITY SameMinorVersion
    )

    install(EXPORT FramelessTargets
        FILE FramelessTargets.cmake
        NAMESPACE Frameless::
        DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/Frameless
    )

    install(FILES
        "${_cfg_dir}/FramelessConfig.cmake"
        "${_cfg_dir}/FramelessConfigVersion.cmake"
        DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/Frameless
    )
endif()

if(BUILD_LIBRARY)
    configure_package_config_file(
        "${CMAKE_CURRENT_SOURCE_DIR}/cmake/FluentUI3StyleConfig.cmake.in"
        "${_cfg_dir}/FluentUI3StyleConfig.cmake"
        INSTALL_DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/FluentUI3Style
    )

    write_basic_package_version_file(
        "${_cfg_dir}/FluentUI3StyleConfigVersion.cmake"
        VERSION ${PROJECT_VERSION}
        COMPATIBILITY SameMinorVersion
    )

    install(EXPORT FluentUI3StyleTargets
        FILE FluentUI3StyleTargets.cmake
        NAMESPACE FluentUI3Style::
        DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/FluentUI3Style
    )

    install(FILES
        "${_cfg_dir}/FluentUI3StyleConfig.cmake"
        "${_cfg_dir}/FluentUI3StyleConfigVersion.cmake"
        DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/FluentUI3Style
    )
endif()

if(BUILD_PLUGIN)
    install(TARGETS FluentUI3StylePlugin
        RUNTIME DESTINATION ${_qt_plugins_install_dir}/styles
        LIBRARY DESTINATION ${_qt_plugins_install_dir}/styles
    )
endif()
