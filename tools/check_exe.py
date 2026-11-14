"""Exercise the distributed EXE without Python on PATH or an external runtime.

Uses an isolated Windows profile/data folder and process-specific window close;
never reads, closes or edits the user's running journal.
"""
import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
from urllib.request import urlopen

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        return listener.getsockname()[1]


def close_own_window(process, executable):
    command = f"Get-CimInstance Win32_Process -Filter \"Name='{executable.name}'\" | Select-Object ProcessId,ParentProcessId | ConvertTo-Json -Compress"
    result = subprocess.run(['powershell.exe', '-NoProfile', '-Command', command],
                            capture_output=True, text=True, check=True,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    rows = json.loads(result.stdout)
    rows = rows if isinstance(rows, list) else [rows]
    own = {process.pid}
    for _ in range(len(rows)):
        own.update(row['ProcessId'] for row in rows if row['ParentProcessId'] in own)
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    handles = []

    @callback_type
    def visit(handle, _):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(handle, ctypes.byref(pid))
        if pid.value in own and user32.IsWindowVisible(handle):
            handles.append(handle)
        return True

    user32.EnumWindows(visit, 0)
    assert handles, 'The packaged app has no visible native window'
    for handle in handles:
        user32.PostMessageW(handle, 0x0010, 0, 0)
    process.wait(timeout=15)
    assert process.returncode == 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('exe', type=Path)
    args = parser.parse_args()
    executable = args.exe.resolve()
    output = ROOT/'test-results/exe'
    output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='lean-plan-exe-') as folder, sync_playwright() as playwright:
        profile = Path(folder)
        # Copy only the EXE, proving it does not read a neighboring .runtime.
        import shutil
        standalone = profile/executable.name
        shutil.copy2(executable, standalone)
        environment = dict(os.environ)
        for name in ('PYTHONPATH', 'PYTHONHOME', 'LEANPLAN_DATA_DIR'):
            environment.pop(name, None)
        environment['PATH'] = str(Path(os.environ['WINDIR'])/'System32')
        environment['LOCALAPPDATA'] = str(profile/'local-profile')
        errors = []
        for run in range(2):
            port = free_port()
            environment['WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS'] = f'--remote-debugging-port={port}'
            process = subprocess.Popen([str(standalone)], cwd=profile, env=environment,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                deadline = time.monotonic()+35
                while time.monotonic() < deadline:
                    try:
                        with urlopen(f'http://127.0.0.1:{port}/json/version', timeout=.3) as response:
                            json.load(response)
                        break
                    except Exception:
                        assert process.poll() is None, f'EXE exited with {process.returncode}'
                        time.sleep(.1)
                else:
                    raise AssertionError('Packaged WebView2 did not start')
                browser = playwright.chromium.connect_over_cdp(f'http://127.0.0.1:{port}')
                page = browser.contexts[0].pages[0]
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.get_by_role('heading', name='Overview', exact=True).wait_for()
                if run == 0:
                    page.get_by_role('heading', name='Your profile', exact=True).wait_for()
                    assert page.evaluate('state.entries.length') == 0
                    page.get_by_label('Age', exact=True).fill('35')
                    page.get_by_label('Height', exact=True).fill('180')
                    page.locator('[name=sex]').select_option('male')
                    page.get_by_role('button', name='Continue', exact=True).click()
                    page.locator('#setup-weight').fill('80')
                    page.get_by_role('button', name='Done', exact=True).click()
                    page.wait_for_selector('[role=dialog]', state='detached')
                    page.locator('#today-protein').fill('150')
                    assert page.evaluate('state.today_stats.bmr') == 1755
                    assert page.evaluate('state.today_stats.calories') == 600
                    # Close with the last autosave still pending.
                    page.locator('#today-calories').fill('1020')
                else:
                    assert page.locator('[role=dialog]').count() == 0
                    assert page.locator('#today-calories').input_value() == '1020'
                    assert page.evaluate('state.today_stats.bmr') == 1755
                    assert page.evaluate('state.today_stats.calories_source') == 'manual'
                    page.screenshot(path=str(output/'standalone-overview.png'))
                close_own_window(process, standalone)
                browser.close()
            finally:
                if process.poll() is None:
                    # Only the disposable EXE's own process tree.
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                                   capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        assert (profile/'local-profile/Lean Plan/data/leanplan.sqlite3').is_file()
        assert not errors, errors
    print(json.dumps({'result':'passed', 'sha256':hashlib.sha256(executable.read_bytes()).hexdigest(),
                      'checks':['EXE alone', 'Python absent from PATH', 'native desktop onboarding',
                                'Mifflin and manual calories', 'autosave on close',
                                'journal survives restart', 'isolated persistent data']}))


if __name__ == '__main__':
    main()
