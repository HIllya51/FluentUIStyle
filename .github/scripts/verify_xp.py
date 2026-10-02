"""Windows XP 兼容性校验：检查 SDK 目录中所有 DLL 的 PE 头与导入表。

用法: python verify_xp.py <stage_dir> [xp_exports_txt]

校验项（任一失败即退出码 1）：
  * Machine = i386 (0x14c)              —— 32 位构建
  * OperatingSystemVersion = 5.01       —— XP 加载器拒绝更高版本的模块
  * SubsystemVersion = 5.01
  * 不导入 XP 上不存在的运行时 DLL    —— 静态 CRT(/MT) + YY-Thunks 生效后，
    导入表应只剩系统 DLL（kernel32/user32/Qt5*.dll 等）
  * （提供 xp_exports_txt 时）导入的每个系统模块/函数都存在于
    YY-Thunks 自带的 XP SP3 导出表（Config/x86/5.1.2600.txt）——
    YY-Thunks 已接管的 API 不会出现在导入表里，剩下的必须 XP 原生可用

依赖: pip install pefile
"""

import pathlib
import sys

try:
    import pefile
except ImportError:
    sys.exit("pefile is not installed (pip install pefile)")

# XP 上不存在的 VC/UCRT 运行时（注意 msvcrt.dll 是系统 DLL，不算）
_BAD_IMPORTS = (
    "vcruntime140",
    "msvcp140",
    "concrt140",
    "vccorlib140",
    "ucrtbase",
    "api-ms-",
    "msvcr90",
    "msvcr100",
    "msvcr110",
    "msvcr120",
    "msvcr140",
)

# 随 SDK 分发、不在系统导出表里的模块（按前缀匹配）
_APP_MODULE_PREFIXES = ("qt5", "qt6", "exwidgets", "fluentui3style", "qwkcore", "qwkwidgets")

XP_VERSION = (5, 1)

_IMPORT_DIRS = [
    pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"],
    pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT"],
]


def load_xp_exports(path):
    """解析 YY-Thunks 的 XP 导出表（INI 风格：[module] 下 序号=函数名）。

    返回 {module小写: (函数名集合小写, 序号集合)}。
    """
    exports = {}
    module = None
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith("[") and line.endswith("]"):
                module = line[1:-1].lower()
                names, ordinals = exports.setdefault(module, (set(), set()))
            elif "=" in line and module is not None:
                key, name = line.split("=", 1)
                names.add(name.strip().lower())
                try:
                    ordinals.add(int(key.strip()))
                except ValueError:
                    pass
    return exports


def is_app_module(name):
    return any(name.startswith(p) for p in _APP_MODULE_PREFIXES)


def main():
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    root = pathlib.Path(sys.argv[1])
    if not root.is_dir():
        sys.exit(f"directory not found: {root}")

    xp_exports = None
    if len(sys.argv) == 3:
        xp_exports = load_xp_exports(sys.argv[2])
        print(f"XP export database: {len(xp_exports)} modules "
              f"({sum(len(v[0]) for v in xp_exports.values())} functions)")
        print()

    errors = []
    dlls = sorted(root.rglob("*.dll"))
    if not dlls:
        sys.exit(f"no DLLs found under {root}")

    for dll in dlls:
        pe = pefile.PE(str(dll), fast_load=True)
        pe.parse_data_directories(directories=_IMPORT_DIRS)
        try:
            machine = pe.FILE_HEADER.Machine
            if machine != 0x14C:
                errors.append(f"{dll}: machine 0x{machine:x} is not i386")

            oh = pe.OPTIONAL_HEADER
            os_ver = (oh.MajorOperatingSystemVersion, oh.MinorOperatingSystemVersion)
            sub_ver = (oh.MajorSubsystemVersion, oh.MinorSubsystemVersion)
            if os_ver != XP_VERSION:
                errors.append(
                    f"{dll}: OS version {os_ver[0]}.{os_ver[1]:02d} != 5.01"
                )
            if sub_ver != XP_VERSION:
                errors.append(
                    f"{dll}: subsystem version {sub_ver[0]}.{sub_ver[1]:02d} != 5.01"
                )

            module_names = []
            for attr in ("DIRECTORY_ENTRY_IMPORT", "DIRECTORY_ENTRY_DELAY_IMPORT"):
                for entry in getattr(pe, attr, []):
                    mod = entry.dll.decode(errors="replace").lower()
                    module_names.append(mod)
                    if any(bad in mod for bad in _BAD_IMPORTS):
                        errors.append(f"{dll}: imports {mod} (missing on Windows XP)")
                        continue
                    if is_app_module(mod):
                        continue  # 随 SDK 分发的 Qt/自家模块，按名跳过
                    if xp_exports is not None and mod not in xp_exports:
                        errors.append(
                            f"{dll}: imports module {mod} (does not exist on Windows XP)"
                        )
                        continue
                    if xp_exports is None:
                        continue
                    names, ordinals = xp_exports[mod]
                    for imp in entry.imports:
                        if imp.name is not None:
                            if imp.name.decode(errors="replace").lower() not in names:
                                errors.append(
                                    f"{dll}: {mod}!{imp.name.decode()} "
                                    "(not exported on Windows XP)"
                                )
                        elif imp.ordinal not in ordinals:
                            errors.append(
                                f"{dll}: {mod}!ordinal#{imp.ordinal} "
                                "(not exported on Windows XP)"
                            )
            print(f"  {dll.name}: imports = {module_names or ['<none>']}")
        finally:
            pe.close()

    print()
    for err in errors:
        print(f"ERROR: {err}")
    print(f"checked {len(dlls)} DLLs, {len(errors)} problem(s)")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
