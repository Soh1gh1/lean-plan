"""Test the real hidden-to-visible Windows startup with a disposable journal."""
from pathlib import Path
import sys
import tempfile
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

import webview
from leanplan.server import create_server
from leanplan.store import Store
from leanplan.desktop import force_dark_window, install_autosave_close_guard, install_fixed_window_geometry, enable_per_monitor_dpi, install_renderer_recovery


def main():
    enable_per_monitor_dpi()
    errors=[]
    with tempfile.TemporaryDirectory() as directory:
        store=Store(Path(directory))
        server=create_server(store,ROOT/'static')
        threading.Thread(target=server.serve_forever,daemon=True).start()
        window=webview.create_window('Lean Plan desktop check',f'http://127.0.0.1:{server.server_port}',hidden=True,width=1200,height=780,resizable=False,fullscreen=False,min_size=(320,240),background_color='#101116')
        def loaded():
            force_dark_window(window)
            install_renderer_recovery(window)
            install_fixed_window_geometry(window)
            window.show()
        window.events.loaded += loaded
        install_autosave_close_guard(window)

        def check():
            try:
                for _ in range(150):
                    if window.evaluate_js("document.querySelector('#modal-title')?.textContent || ''")== 'Your profile':
                        break
                    time.sleep(.1)
                else:raise AssertionError('Desktop onboarding did not load')
                assert window.evaluate_js("getComputedStyle(document.documentElement).colorScheme") == 'dark'
                assert window.native.is_dark_theme()
                from System import Action
                from System.Windows.Forms import Screen, FormWindowState, FormBorderStyle
                assert not window.native.MaximizeBox
                assert window.native.FormBorderStyle==FormBorderStyle.FixedSingle
                for _ in range(100):
                    if hasattr(window,'_display_bounds') and window.native.Visible:break
                    time.sleep(.02)
                assert hasattr(window,'_display_bounds')
                native=window.native
                assert native.Visible
                viewport=window.evaluate_js("({width:innerWidth,height:innerHeight,scale:window.leanplanScale,frame:document.querySelector('#app-frame').getBoundingClientRect().toJSON()})")
                assert viewport['scale']>0
                assert viewport['frame']['width']>0 and viewport['frame']['right']<=viewport['width']+1
                assert viewport['frame']['height']>0 and viewport['frame']['bottom']<=viewport['height']+1
                work=Screen.FromControl(native).WorkingArea
                assert native.Left>=work.Left and native.Top>=work.Top
                assert native.Right<=work.Right and native.Bottom<=work.Bottom
                original=(native.Width,native.Height)
                assert native.ClientSize.Width<=1200*native.DeviceDpi/96+1
                assert native.ClientSize.Height<=780*native.DeviceDpi/96+1
                assert window.evaluate_js("document.querySelectorAll('.skip-link').length")==0
                native.Invoke(Action(lambda:setattr(native,'Width',native.Width+150)))
                assert (native.Width,native.Height)==original
                import ctypes
                from ctypes import wintypes
                user32=ctypes.WinDLL('user32')
                user32.SendMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
                user32.SendMessageW.restype=ctypes.c_ssize_t
                user32.GetWindowDpiAwarenessContext.argtypes=[wintypes.HWND]
                user32.GetWindowDpiAwarenessContext.restype=ctypes.c_void_p
                user32.GetAwarenessFromDpiAwarenessContext.argtypes=[ctypes.c_void_p]
                user32.GetAwarenessFromDpiAwarenessContext.restype=ctypes.c_int
                assert user32.GetAwarenessFromDpiAwarenessContext(user32.GetWindowDpiAwarenessContext(int(native.Handle.ToInt64())))==2
                user32.SendMessageW(int(native.Handle.ToInt64()),0x0112,0xf030,0)
                user32.SendMessageW(int(native.Handle.ToInt64()),0x00a3,2,0)
                assert native.WindowState==FormWindowState.Normal
                window.toggle_fullscreen()
                assert not native.is_fullscreen
                window.evaluate_js("document.querySelector('[data-action=setup-done]').click()")
                for _ in range(100):
                    if store.settings()['onboarding_done']:break
                    time.sleep(.05)
                assert store.settings()['onboarding_done']
                assert store.entries()==[]
                window.evaluate_js("[['weight','80'],['protein','150'],['fat','60'],['carbs','200']].forEach(([key,value])=>{const input=document.getElementById(key==='weight'?'latest-weight-input':'today-'+key);input.value=value;input.dispatchEvent(new Event('input',{bubbles:true}));}); true")
                # Closing immediately must flush the debounce queue first.
                window.destroy()
            except Exception as error:
                errors.append(error)
                window.destroy()

        try:
            webview.start(check,gui='edgechromium')
        finally:
            server.shutdown()
            server.server_close()
        if errors:raise errors[0]
        assert store.entries()[0]['calories']==1940
        print('Native WebView2: fitted work area, fixed size, maximize/fullscreen blocked, dark frame and autosave on immediate close passed.',flush=True)


if __name__=='__main__':main()
