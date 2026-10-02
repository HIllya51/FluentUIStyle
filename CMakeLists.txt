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

# --- Legacy Windows support (YY-Thunks + static CRT) ---
# 产出老系统可加载的 DLL（YY-Thunks Readme §2.4.1 手动配置的 CMake 化）：
#   * 静态 CRT (/MT) —— 老系统没有 vcruntime140/ucrtbase 的可靠官方通道
#     （XP 完全没有；Win7 无 SP 装不上 KB2999226，14.41+ redist 只要 Win10+）
#   * YY-Thunks obj —— 链接期接管新版 Windows API 导入（WinXP→x86 obj，Win7→x64 obj）
#   * 子系统版本降级 —— 老系统加载器拒绝更高 SubsystemVersion 的模块
#   * DLL 入口替换为 DllMainCRTStartupForYY_Thunks + alternatename 还原原入口
#     —— 老 DLL 的 thread_local 依赖该入口注册的 TLS 回调，直接用 CRT 默认入口会加载即崩
# 目标：
#   WinXP = 32 位 MSVC + objs/x86/YY_Thunks_for_WinXP.obj + 子系统 5.01
#   Win7  = 64 位 MSVC + objs/x64/YY_Thunks_for_Win7.obj  + 子系统 6.01
# 用法：
#   cmake -G "Visual Studio 17 2022" -A Win32 \
#         -DFLUENTUI3_LEGACY_WINDOWS=WinXP \
#         -DYY_THUNKS_OBJ=<dir>/objs/x86/YY_Thunks_for_WinXP.obj
#   cmake -G "Visual Studio 17 2022" -A x64 \
#         -DFLUENTUI3_LEGACY_WINDOWS=Win7 \
#         -DYY_THUNKS_OBJ=<dir>/objs/x64/YY_Thunks_for_Win7.obj
set(FLUENTUI3_LEGACY_WINDOWS "" CACHE STRING
    "Target legacy Windows via YY-Thunks + static CRT: WinXP (x86) / Win7 (x64); empty = off")
set(YY_THUNKS_OBJ "" CACHE FILEPATH
    "Path to YY_Thunks_for_WinXP.obj / YY_Thunks_for_Win7.obj from YY-Thunks-Objs.zip (required by FLUENTUI3_LEGACY_WINDOWS)")

if(FLUENTUI3_LEGACY_WINDOWS)
    if(NOT WIN32 OR NOT MSVC)
        message(FATAL_ERROR "FLUENTUI3_LEGACY_WINDOWS is only available with the MSVC toolchain")
    endif()
    if(FLUENTUI3_LEGACY_WINDOWS STREQUAL "WinXP")
        set(_legacy_subsystem "5.01")
        set(_legacy_alternate
            "/alternatename:_YY_ThunksOriginalDllMainCRTStartup@12=__DllMainCRTStartup@12")
        set(_legacy_arch "32-bit (-A Win32)")
        set(_legacy_ptr 4)
    elseif(FLUENTUI3_LEGACY_WINDOWS STREQUAL "Win7")
        set(_legacy_subsystem "6.01")
        set(_legacy_alternate
            "/alternatename:YY_ThunksOriginalDllMainCRTStartup=_DllMainCRTStartup")
        set(_legacy_arch "64-bit (-A x64)")
        set(_legacy_ptr 8)
    else()
        message(FATAL_ERROR
            "FLUENTUI3_LEGACY_WINDOWS must be WinXP or Win7, got '${FLUENTUI3_LEGACY_WINDOWS}'")
    endif()
    if(NOT CMAKE_SIZEOF_VOID_P EQUAL _legacy_ptr)
        message(FATAL_ERROR
            "FLUENTUI3_LEGACY_WINDOWS=${FLUENTUI3_LEGACY_WINDOWS} requires the "
            "${_legacy_arch} toolchain")
    endif()
    if(NOT YY_THUNKS_OBJ OR NOT EXISTS "${YY_THUNKS_OBJ}")
        message(FATAL_ERROR
            "FLUENTUI3_LEGACY_WINDOWS requires YY_THUNKS_OBJ to point at the matching "
            "objs/<arch>/YY_Thunks_for_${FLUENTUI3_LEGACY_WINDOWS}.obj "
            "(https://github.com/Chuyu-Team/YY-Thunks releases)")
    endif()
    # MSVC_RUNTIME_LIBRARY 属性在每个 target 创建时取值，必须在 add_subdirectory 之前设置
    set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
    message(STATUS "Legacy Windows target: ${FLUENTUI3_LEGACY_WINDOWS} "
                   "(YY-Thunks: ${YY_THUNKS_OBJ}, static CRT, subsystem ${_legacy_subsystem})")
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

# YY-Thunks 链接选项只挂到共享库目标（EXE 不能用 DLL 入口；静态库不参与链接）。
# obj 提供的 __imp_ 桩在链接期优先于导入库成员，MSVC 循环扫库语义下顺序无关。
if(FLUENTUI3_LEGACY_WINDOWS)
    foreach(_legacy_target IN ITEMS ExWidgets FluentUI3Style FluentUI3StylePlugin QWKCore QWKWidgets)
        if(TARGET ${_legacy_target})
            get_target_property(_legacy_type ${_legacy_target} TYPE)
            if(_legacy_type STREQUAL "SHARED_LIBRARY" OR _legacy_type STREQUAL "MODULE_LIBRARY")
                target_link_options(${_legacy_target} PRIVATE
                    "${YY_THUNKS_OBJ}"
                    "/SUBSYSTEM:WINDOWS,${_legacy_subsystem}"
                    "/ENTRY:DllMainCRTStartupForYY_Thunks"
                    "${_legacy_alternate}"
                )
                message(STATUS "YY-Thunks linked into : ${_legacy_target}")
            endif()
        endif()
    endforeach()
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
