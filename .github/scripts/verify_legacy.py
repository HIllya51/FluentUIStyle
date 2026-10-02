"""Legacy Windows 兼容性校验：检查 SDK 目录中所有 DLL 的 PE 头与导入表。

用法: python verify_legacy.py <stage_dir> <exports_txt> <WinXP|Win7>

exports_txt 取自 YY-Thunks-Objs.zip：
  WinXP -> Config/x86/5.1.2600.txt   (XP SP3，32 位)
  Win7  -> Config/x64/6.1.7600.txt   (Win7 RTM 无 SP，64 位)

校验项（任一失败即退出码 1）：
  * Machine 与目标架构一致            —— WinXP=i386(0x14c)，Win7=x64(0x8664)
  * OperatingSystemVersion / SubsystemVersion 与目标一致
    —— WinXP=5.01，Win7=6.01（老系统加载器拒绝更高版本的模块）
  * 不导入老系统上拿不到的 VC/UCRT 运行时
    —— 静态 CRT(/MT) + YY-Thunks 生效后，导入表应只剩系统 DLL
    （Win7 无 SP：KB2999226 只到 SP1，14.41+ redist 只要 Win10+）
  * 导入的每个系统模块/函数都存在于目标系统的导出表 —— YY-Thunks 已接管的
    API 不会出现在导入表里，剩下的必须目标系统原生可用

依赖: pip install pefile
"""

import pathlib
import sys

try:
    import pefile
except ImportError:
    sys.exit("pefile is not installed (pip install pefile)")

# 老系统上拿不到的 VC/UCRT 运行时（注意 msvcrt.dll 是系统 DLL，不算）
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

_TARGETS = {
    "WinXP": {"machine": 0x14C, "version": (5, 1), "label": "Windows XP SP3 (x86)"},
    "Win7": {"machine": 0x8664, "version": (6, 1), "label": "Windows 7 RTM (x64)"},
}

_IMPORT_DIRS = [
    pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"],
    pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT"],
]


def load_exports(path):
    """解析 YY-Thunks 的系统导出表（INI 风格：[module] 下 序号=函数名）。

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
    if len(sys.argv) != 4 or sys.argv[3] not in _TARGETS:
        sys.exit(__doc__)
    root = pathlib.Path(sys.argv[1])
    if not root.is_dir():
        sys.exit(f"directory not found: {root}")

    target = _TARGETS[sys.argv[3]]
    want_version = target["version"]
    exports = load_exports(sys.argv[2])
    print(f"Target: {target['label']}")
    print(f"Export database: {len(exports)} modules "
          f"({sum(len(v[0]) for v in exports.values())} functions)")
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
            if machine != target["machine"]:
                errors.append(
                    f"{dll}: machine 0x{machine:x} is not "
                    f"0x{target['machine']:x}"
                )

            oh = pe.OPTIONAL_HEADER
            os_ver = (oh.MajorOperatingSystemVersion, oh.MinorOperatingSystemVersion)
            sub_ver = (oh.MajorSubsystemVersion, oh.MinorSubsystemVersion)
            if os_ver != want_version:
                errors.append(
                    f"{dll}: OS version {os_ver[0]}.{os_ver[1]:02d} != "
                    f"{want_version[0]}.{want_version[1]:02d}"
                )
            if sub_ver != want_version:
                errors.append(
                    f"{dll}: subsystem version {sub_ver[0]}.{sub_ver[1]:02d} != "
                    f"{want_version[0]}.{want_version[1]:02d}"
                )

            module_names = []
            for attr in ("DIRECTORY_ENTRY_IMPORT", "DIRECTORY_ENTRY_DELAY_IMPORT"):
                for entry in getattr(pe, attr, []):
                    mod = entry.dll.decode(errors="replace").lower()
                    module_names.append(mod)
                    if any(bad in mod for bad in _BAD_IMPORTS):
                        errors.append(
                            f"{dll}: imports {mod} (unavailable on legacy Windows)"
                        )
                        continue
                    if is_app_module(mod):
                        continue  # 随 SDK 分发的 Qt/自家模块，按名跳过
                    if mod not in exports:
                        errors.append(
                            f"{dll}: imports module {mod} "
                            "(does not exist on target system)"
                        )
                        continue
                    names, ordinals = exports[mod]
                    for imp in entry.imports:
                        if imp.name is not None:
                            if imp.name.decode(errors="replace").lower() not in names:
                                errors.append(
                                    f"{dll}: {mod}!{imp.name.decode()} "
                                    "(not exported on target system)"
                                )
                        elif imp.ordinal not in ordinals:
                            errors.append(
                                f"{dll}: {mod}!ordinal#{imp.ordinal} "
                                "(not exported on target system)"
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
