"""Launch the actual CMD/EXE against a disposable copy and inspect WebView2 pixels."""
import argparse
import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import socket
import sqlite3
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--launcher', choices=('cmd', 'exe'), default='cmd')
    parser.add_argument('--copy-journal', action='store_true')
    parser.add_argument('--duration', type=float, default=1)
    parser.add_argument('--exercise-window', action='store_true')
    parser.add_argument('--crash', choices=('renderer', 'browser'))
    args = parser.parse_args()
    output = ROOT/'test-results'/'startup'
    output.mkdir(exist_ok=True)
    output = output.resolve()
    assert output.is_relative_to(ROOT)
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowW.restype = wintypes.HWND
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    assert not user32.FindWindowW(None, 'Lean Plan'), 'Close the existing app before this isolated startup check.'
    debug_port = free_port()
    label = args.launcher+('-existing' if args.copy_journal else '-empty')+('-crash-'+args.crash if args.crash else '')
    with tempfile.TemporaryDirectory(prefix='journal-', dir=output) as folder:
        data = Path(folder)
        assert data.resolve().parent == output
        if args.copy_journal:
            source = sqlite3.connect((ROOT/'data'/'leanplan.sqlite3').as_uri()+'?mode=ro', uri=True)
            destination = sqlite3.connect(data/'leanplan.sqlite3')
            try:
                source.backup(destination)
            finally:
                source.close()
                destination.close()
        environment = dict(os.environ, LEANPLAN_DATA_DIR=str(data),
                           WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=f'--remote-debugging-port={debug_port}')
        if args.launcher == 'cmd':
            command = f'"{os.environ["COMSPEC"]}" /d /s /c ""{ROOT/"Start Lean Plan.cmd"}""'
        else:
            command = [str(ROOT/'Lean Plan.exe')]
        with (output/f'{label}-console.log').open('w', encoding='utf-8') as console:
            process = subprocess.Popen(command, cwd=ROOT, env=environment, stdout=console,
                                       stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                deadline = time.monotonic()+20
                while time.monotonic() < deadline:
                    try:
                        with urlopen(f'http://127.0.0.1:{debug_port}/json/version', timeout=.3) as response:
                            json.load(response)
                        break
                    except Exception:
                        if process.poll() is not None and process.returncode != 0:
                            raise AssertionError(f'Launcher exited with {process.returncode}')
                        time.sleep(.1)
                else:
                    raise AssertionError('WebView2 debugging endpoint did not start')
                with sync_playwright() as playwright:
                    browser = playwright.chromium.connect_over_cdp(f'http://127.0.0.1:{debug_port}', timeout=5000)
                    page = browser.contexts[0].pages[0]
                    crashes = []
                    page.on('crash', lambda: crashes.append('renderer crash'))
                    page.wait_for_selector('h1', timeout=10000)
                    page.wait_for_timeout(500)
                    if args.crash:
                        saved_state = page.evaluate('({settings:state.settings,summary:state.summary,today:state.today_stats})')
                        # This browser has an isolated profile and debug port;
                        # never terminate a system browser or another app's WebView.
                        processes = browser.new_browser_cdp_session().send('SystemInfo.getProcessInfo')['processInfo']
                        crashed_pid = next(item['id'] for item in processes if item['type'] == args.crash)
                        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
                        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
                        kernel32.OpenProcess.restype = wintypes.HANDLE
                        kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
                        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
                        target = kernel32.OpenProcess(1, False, crashed_pid)
                        assert target
                        try:
                            assert kernel32.TerminateProcess(target, 1)
                        finally:
                            kernel32.CloseHandle(target)
                        recovered = False
                        deadline = time.monotonic()+15
                        while time.monotonic() < deadline:
                            time.sleep(.2)
                            try:
                                browser = playwright.chromium.connect_over_cdp(f'http://127.0.0.1:{debug_port}', timeout=500)
                                page = browser.contexts[0].pages[0]
                                page.wait_for_selector('h1', timeout=500)
                                if page.evaluate('window.leanplanScale') > 0:
                                    recovered = True
                                    break
                            except Exception:
                                pass
                        assert recovered, 'The native host did not recover its display'
                        assert page.evaluate('({settings:state.settings,summary:state.summary,today:state.today_stats})') == saved_state
                        crashes.clear()
                    deadline = time.monotonic()+args.duration
                    cycles = 0
                    next_restore = time.monotonic()+2
                    while time.monotonic() < deadline:
                        if args.exercise_window and cycles < 3 and time.monotonic() >= next_restore:
                            handle = user32.FindWindowW(None, 'Lean Plan')
                            user32.ShowWindow(handle, 6)
                            page.wait_for_timeout(150)
                            user32.ShowWindow(handle, 9)
                            cycles += 1
                            next_restore = time.monotonic()+5
                        page.wait_for_timeout(500)
                        assert page.evaluate('window.leanplanScale') > 0
                        assert not crashes, crashes
                    report = page.evaluate('''() => ({url:location.href,title:document.title,
                      heading:document.querySelector('h1')?.textContent,viewport:[innerWidth,innerHeight],
                      scale:window.leanplanScale,frame:document.querySelector('#app-frame').getBoundingClientRect().toJSON(),
                      textLength:document.body.innerText.length})''')
                    report.update(duration=args.duration, restore_cycles=cycles, recovered_from=args.crash)
                    page.screenshot(path=str(output/f'{label}-webview.png'), timeout=5000)
                    assert report['scale'] > 0 and report['textLength'] > 100, report
                    native_path = str(output/f'{label}-native.png').replace("'", "''")
                    capture = r'''
Add-Type -AssemblyName System.Drawing
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class StartupCapture {
 [StructLayout(LayoutKind.Sequential)] public struct Rect { public int Left,Top,Right,Bottom; }
 [DllImport("user32.dll",CharSet=CharSet.Unicode)] public static extern IntPtr FindWindow(string c,string t);
 public static IntPtr FindLeanWindow() { return FindWindow(null,"Lean Plan"); }
 [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h,out Rect r);
 [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
 [DllImport("user32.dll")] public static extern IntPtr SetThreadDpiAwarenessContext(IntPtr c);
}
'@
[void][StartupCapture]::SetThreadDpiAwarenessContext([IntPtr](-4))
$handle = [StartupCapture]::FindLeanWindow()
if ($handle -eq [IntPtr]::Zero) { throw 'The app window was not found.' }
[void][StartupCapture]::SetForegroundWindow($handle)
Start-Sleep -Milliseconds 400
$bounds = New-Object StartupCapture+Rect
[void][StartupCapture]::GetWindowRect($handle,[ref]$bounds)
$bitmap = New-Object System.Drawing.Bitmap ($bounds.Right-$bounds.Left),($bounds.Bottom-$bounds.Top)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.CopyFromScreen($bounds.Left,$bounds.Top,0,0,$bitmap.Size)
$colors = New-Object 'System.Collections.Generic.HashSet[int]'
for ($sampleY=50; $sampleY -lt $bitmap.Height-12; $sampleY+=4) {
 for ($sampleX=12; $sampleX -lt $bitmap.Width-12; $sampleX+=4) {
  [void]$colors.Add($bitmap.GetPixel($sampleX,$sampleY).ToArgb())
 }
}
$bitmap.Save('__NATIVE_PATH__',[System.Drawing.Imaging.ImageFormat]::Png)
$graphics.Dispose()
$bitmap.Dispose()
@{uniqueColors=$colors.Count} | ConvertTo-Json -Compress
'''.replace('__NATIVE_PATH__', native_path)
                    encoded = base64.b64encode(capture.encode('utf-16le')).decode('ascii')
                    captured = subprocess.run(['powershell.exe', '-NoProfile', '-EncodedCommand', encoded],
                                              capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=15,
                                              creationflags=subprocess.CREATE_NO_WINDOW)
                    assert captured.returncode == 0, captured.stderr
                    report['native'] = json.loads(captured.stdout)
                    (output/f'{label}.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
                    assert report['native']['uniqueColors'] > 20, report
                    print(json.dumps({'result':'passed','launcher':args.launcher,'copied_journal':args.copy_journal,**report}), flush=True)
            finally:
                handle = user32.FindWindowW(None, 'Lean Plan')
                native_process = None
                if handle:
                    native_pid = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(handle, ctypes.byref(native_pid))
                    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
                    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
                    kernel32.OpenProcess.restype = wintypes.HANDLE
                    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
                    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
                    native_process = kernel32.OpenProcess(0x100000, False, native_pid.value)
                    user32.PostMessageW(handle, 0x0010, 0, 0)
                if native_process:
                    try:
                        assert kernel32.WaitForSingleObject(native_process, 8000) == 0, 'The app did not close normally'
                    finally:
                        kernel32.CloseHandle(native_process)
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    process.wait(timeout=3)
                if (data/'app.log').exists():
                    (output/f'{label}-app.log').write_bytes((data/'app.log').read_bytes())


if __name__ == '__main__':
    main()
