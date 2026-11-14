"""Bundle the existing Python interpreter and desktop dependencies locally.

No installer, PATH changes, network dependencies or administrator rights.
Run using the Python installation that contains pywebview.
"""
from pathlib import Path
import shutil
import sys


ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'.runtime'
SOURCE=Path(sys.base_prefix)


def main():
    DEST.mkdir(exist_ok=True)
    for pattern in ('python*.exe','python*.dll','vcruntime*.dll','LICENSE.txt'):
        for file in SOURCE.glob(pattern):
            shutil.copy2(file,DEST/file.name)
    ignored=shutil.ignore_patterns('__pycache__','test','tests','idlelib','turtledemo','tkinter','ensurepip','site-packages')
    shutil.copytree(SOURCE/'Lib',DEST/'Lib',ignore=ignored,dirs_exist_ok=True)
    shutil.copytree(SOURCE/'DLLs',DEST/'DLLs',ignore=shutil.ignore_patterns('__pycache__'),dirs_exist_ok=True)
    packages=SOURCE/'Lib'/'site-packages'
    target=DEST/'Lib'/'site-packages'
    target.mkdir(exist_ok=True)
    names=('webview','bottle.py','proxy_tools','typing_extensions.py','pythonnet','clr_loader','clr.py','cffi','pycparser')
    for name in names:
        path=packages/name
        if path.is_dir():
            shutil.copytree(path,target/name,ignore=shutil.ignore_patterns('__pycache__','__pyinstaller','tests'),dirs_exist_ok=True)
        else:
            shutil.copy2(path,target/name)
    for file in packages.glob('_cffi_backend*.pyd'):
        shutil.copy2(file,target/file.name)
    # pywebview's importlib.metadata lookup needs its package metadata.
    for pattern in ('pywebview-*.dist-info','pythonnet-*.dist-info','clr_loader-*.dist-info','proxy_tools-*.dist-info','bottle-*.dist-info','cffi-*.dist-info'):
        for folder in packages.glob(pattern):
            shutil.copytree(folder,target/folder.name,dirs_exist_ok=True)
    size=sum(file.stat().st_size for file in DEST.rglob('*') if file.is_file())
    print(f'Portable runtime: {DEST} ({size/1024/1024:.1f} MiB)')


if __name__=='__main__':main()
