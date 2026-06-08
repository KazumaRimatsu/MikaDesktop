"""
HOW TO USE
1.pip install -r requirements.txt
2.python build.py build
"""

import sys
import os
from pathlib import Path

from cx_Freeze import setup, Executable

# 项目根目录
ROOT_DIR = Path(__file__).parent

# 基础依赖包
PACKAGES = [
    "core",
    "core.thread_mgr",
    "core.make_app_icon",
    "features",
]

# 第三方包（cx_freeze 会自动检测大部分，这里显式列出可能遗漏的）
INCLUDES = [
    "PySide6",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "PIL",
    "loguru",
    "psutil",
    "pynput",
    "win32com",
    "win32com.shell",
    "win32con",
    "win32gui",
    "win32process",
    "win32timezone",
    "win32api",
    "win32print",
    "winreg",
    "requests",
    "BlurWindow",
    "BlurWindow.blurWindow",
    "ctypes",
    "hashlib",
    "json",
    "datetime",
    "threading",
    "uuid",
    "subprocess",
    "gc",
    "io",
    "warnings",
    "dataclasses",
    "enum",
    "typing",
]

# 需要拷贝的资源文件
INCLUDE_FILES = []

# res/ 目录下的资源文件
res_dir = ROOT_DIR / "res"
if res_dir.exists():
    for f in res_dir.iterdir():
        if f.is_file():
            INCLUDE_FILES.append((str(f), os.path.join("res", f.name)))

# app_model.png
app_model = ROOT_DIR / "core" / "make_app_icon" / "app_model.png"
if app_model.exists():
    INCLUDE_FILES.append((str(app_model), os.path.join("core", "make_app_icon", "app_model.png")))

# 排除不需要的模块
EXCLUDES = [
    "tkinter",
    "unittest",
    "email",
    "xml",
    "xmlrpc",
    "pdb",
    "distutils",
    "test",
]

build_exe_options = {
    "packages": PACKAGES,
    "includes": INCLUDES,
    "include_files": INCLUDE_FILES,
    "excludes": EXCLUDES,
    "optimize": 2,
    "build_exe": "dist/MikaDesktop",
}

# 基础可执行文件配置
base = None
if sys.platform == "win32":
    base = "gui"  # 无控制台窗口的 GUI 应用

executables = [
    Executable(
        script=str(ROOT_DIR / "dock.py"),
        base=base,
        target_name="MikaDesktop.exe",
        icon=str(ROOT_DIR / "core" / "make_app_icon" / "app_model.png"),
    )
]

setup(
    name="MikaDesktop",
    version="0.0.0",
    description="",
    options={"build_exe": build_exe_options},
    executables=executables,
)
