"""Build a single Windows x64 EXE in an isolated packaging environment.

Install requirements-build.txt into a virtual environment, then run this script
with that environment's Python. Personal data is never included as a resource.
"""
from pathlib import Path
import subprocess
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def main():
    if sys.platform != 'win32' or sys.maxsize <= 2**32:
        raise SystemExit('Build with 64-bit Python on Windows.')
    version = tomllib.loads((ROOT/'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
    build = ROOT/'build'
    build.mkdir(exist_ok=True)
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
               '--onefile', '--windowed', '--name', f'Lean-Plan-{version}-Windows-x64',
               '--distpath', str(ROOT/'dist'), '--workpath', str(build/'pyinstaller'),
               '--specpath', str(build), '--add-data', f'{ROOT / "static"};static',
               '--copy-metadata', 'pywebview', '--collect-all', 'webview',
               '--collect-all', 'pythonnet', '--collect-all', 'clr_loader',
               '--hidden-import', 'webview.platforms.edgechromium',
               '--hidden-import', 'webview.platforms.winforms']
    for module in ('PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'gi', 'objc',
                   'cefpython3', 'tkinter', 'webview.platforms.android',
                   'webview.platforms.cocoa', 'webview.platforms.gtk', 'webview.platforms.qt'):
        command.extend(['--exclude-module', module])
    icon = ROOT/'tools/leanplan.ico'
    if icon.is_file():
        command.extend(['--icon', str(icon), '--add-data', f'{icon};tools'])
    command.append(str(ROOT/'app.py'))
    subprocess.run(command, cwd=ROOT, check=True)


if __name__ == '__main__':
    main()
