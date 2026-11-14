"""Keep the native window frame dark without changing the user's OS settings."""
from __future__ import annotations

import logging
import os
import threading
import ctypes
import time
from ctypes import wintypes
from dataclasses import dataclass


CANVAS_WIDTH = 1200
CANVAS_HEIGHT = 780


def enable_per_monitor_dpi():
    """Set per-monitor V2 awareness before WinForms creates any windows."""
    if os.name != 'nt':
        return
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    context = ctypes.c_void_p(-4)
    try:
        user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        user32.SetProcessDpiAwarenessContext.restype = wintypes.BOOL
        user32.SetProcessDpiAwarenessContext(context)
        user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
        user32.SetThreadDpiAwarenessContext(context)
    except AttributeError:
        logging.info('Per-monitor V2 DPI is unavailable on this Windows version')


@dataclass(frozen=True)
class WindowBounds:
    x: int
    y: int
    width: int
    height: int
    client_width: int
    client_height: int
    margin: int


def fit_window_bounds(work_area, dpi=96, frame_width=2, frame_height=31):
    """Size in DIPs, then constrain to the physical work area including chrome.

    1200 x 780 DIPs is the preferred client size (about a quarter of a QHD
    monitor at 100%). Do not enlarge it just because more desktop is available.
    Windows' per-monitor DPI controls the desired physical size; fitting is
    only a fallback when the current work area cannot accommodate that size.
    """
    left, top, width, height = work_area
    margin = max(round(16 * dpi / 96), round(min(width, height) * .035))
    available_width = width - margin * 2 - frame_width
    available_height = height - margin * 2 - frame_height
    if min(available_width, available_height) <= 0:
        raise ValueError('The monitor work area is too small.')
    scale = min(dpi / 96, available_width / CANVAS_WIDTH, available_height / CANVAS_HEIGHT)
    client_width = max(1, int(CANVAS_WIDTH * scale))
    client_height = max(1, int(CANVAS_HEIGHT * scale))
    outer_width, outer_height = client_width + frame_width, client_height + frame_height
    return WindowBounds(left + (width-outer_width)//2, top + (height-outer_height)//2,
                        outer_width, outer_height, client_width, client_height, margin)


def install_fixed_window_geometry(window):
    """Lock native sizing and re-fit only when the hosting display changes."""
    if os.name != 'nt':
        return
    if getattr(window, '_geometry_callbacks', None):
        return
    from System import Action
    from System.Drawing import Size, Point
    from System.Windows.Forms import Screen, Cursor, FormBorderStyle, FormWindowState, Timer
    from Microsoft.Win32 import SystemEvents

    def setup():
        native = window.native
        native.FormBorderStyle = FormBorderStyle.FixedSingle
        native.MaximizeBox = False
        native.MinimizeBox = True
        native.toggle_fullscreen = lambda: None
        window.toggle_fullscreen = lambda: None
        window.maximize = lambda: None
        timer = Timer()
        timer.Interval = 180
        last_display = None
        applying = False

        def fit(initial=False):
            nonlocal last_display, applying
            if applying or native.IsDisposed:
                return
            screen = Screen.FromPoint(Cursor.Position) if initial else Screen.FromControl(native)
            work = screen.WorkingArea
            dpi = max(96, int(native.DeviceDpi))
            frame_width = native.Width - native.ClientSize.Width
            frame_height = native.Height - native.ClientSize.Height
            display = (screen.DeviceName, work.X, work.Y, work.Width, work.Height, dpi,
                       frame_width, frame_height)
            if not initial and display == last_display:
                return
            applying = True
            try:
                bounds = fit_window_bounds((work.X, work.Y, work.Width, work.Height),
                                           dpi, frame_width, frame_height)
                native.MinimumSize = Size.Empty
                native.MaximumSize = Size.Empty
                if native.WindowState != FormWindowState.Minimized:
                    native.WindowState = FormWindowState.Normal
                native.Size = Size(bounds.width, bounds.height)
                native.MinimumSize = Size(bounds.width, bounds.height)
                native.MaximumSize = Size(bounds.width, bounds.height)
                x, y = bounds.x, bounds.y
                if not initial:
                    x = min(max(native.Left, work.Left+bounds.margin), work.Right-bounds.margin-bounds.width)
                    y = min(max(native.Top, work.Top+bounds.margin), work.Bottom-bounds.margin-bounds.height)
                native.Location = Point(x, y)
                last_display = display
                window._display_bounds = bounds
                logging.info('Fixed window: work=%sx%s dpi=%s outer=%sx%s client=%sx%s',
                             work.Width, work.Height, dpi, bounds.width, bounds.height,
                             bounds.client_width, bounds.client_height)
            finally:
                applying = False

        def schedule(*_):
            if not applying and not native.IsDisposed:
                timer.Stop()
                timer.Start()

        def apply_pending(*_):
            timer.Stop()
            fit()

        def enforce_normal(*_):
            if not applying and native.WindowState == FormWindowState.Maximized:
                native.WindowState = FormWindowState.Normal
                schedule()

        def display_changed(*_):
            if not native.IsDisposed:
                native.BeginInvoke(Action(schedule))

        def cleanup(*_):
            timer.Stop()
            timer.Dispose()
            SystemEvents.DisplaySettingsChanged -= display_changed
            SystemEvents.UserPreferenceChanged -= display_changed

        # Block Windows' maximize/size commands and title-bar double click,
        # in addition to removing the resize/maximize styles from the form.
        subclass_type = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND,
                                           wintypes.UINT, wintypes.WPARAM,
                                           wintypes.LPARAM, ctypes.c_size_t,
                                           ctypes.c_size_t)
        comctl = ctypes.WinDLL('comctl32', use_last_error=True)
        comctl.DefSubclassProc.argtypes = [wintypes.HWND, wintypes.UINT,
                                          wintypes.WPARAM, wintypes.LPARAM]
        comctl.DefSubclassProc.restype = ctypes.c_ssize_t
        comctl.SetWindowSubclass.argtypes = [wintypes.HWND, subclass_type,
                                            ctypes.c_size_t, ctypes.c_size_t]
        comctl.SetWindowSubclass.restype = wintypes.BOOL
        comctl.RemoveWindowSubclass.argtypes = [wintypes.HWND, subclass_type, ctypes.c_size_t]
        comctl.RemoveWindowSubclass.restype = wintypes.BOOL

        @subclass_type
        def window_messages(hwnd, message, wparam, lparam, subclass_id, reference):
            if message == 0x0112 and (wparam & 0xfff0) in (0xf030, 0xf000):
                return 0
            if message == 0x00a3 and wparam == 2:
                return 0
            result = comctl.DefSubclassProc(hwnd, message, wparam, lparam)
            if message == 0x0005 and wparam == 2 and not native.IsDisposed:
                native.BeginInvoke(Action(enforce_normal))
            if message == 0x0082:
                comctl.RemoveWindowSubclass(hwnd, window_messages, 1)
            return result

        if not comctl.SetWindowSubclass(int(native.Handle.ToInt64()), window_messages, 1, 0):
            raise ctypes.WinError(ctypes.get_last_error())

        timer.Tick += apply_pending
        native.LocationChanged += schedule
        native.ResizeEnd += schedule
        native.Resize += enforce_normal
        if hasattr(native, 'DpiChanged'):
            native.DpiChanged += schedule
        native.FormClosed += cleanup
        SystemEvents.DisplaySettingsChanged += display_changed
        SystemEvents.UserPreferenceChanged += display_changed
        window._geometry_callbacks = (timer, fit, schedule, display_changed, cleanup, window_messages, comctl)
        fit(initial=True)

    window.native.Invoke(Action(setup))


def force_dark_window(window) -> None:
    if os.name != 'nt':
        return
    try:
        native = window.native
        # pywebview normally follows AppsUseLightTheme. Keep this window dark,
        # including when Windows broadcasts a system theme change later.
        native.is_dark_theme = lambda: True
        from System import Action
        native.Invoke(Action(native.update_title_bar_theme))
    except Exception:
        logging.exception('Could not apply the dark native window frame')


def install_renderer_recovery(window) -> None:
    """Recover WebView2 renderer/browser exits without leaving an empty host window."""
    if os.name != 'nt':
        return
    from System import Action
    from System.Windows.Forms import Timer, Label, DockStyle
    from System.Drawing import Color, ContentAlignment, Font

    existing = getattr(window, '_renderer_recovery', None)
    if existing:
        window.native.Invoke(Action(existing))
        return
    native = window.native
    state = {'core': None, 'environment': None, 'pending': None, 'attempts': [], 'fallback': None}
    timer = Timer()
    timer.Interval = 200

    def attach():
        core = native.browser.webview.CoreWebView2
        if core is not None and core != state['core']:
            if state['core'] is not None:
                try:
                    state['core'].ProcessFailed -= process_failed
                    state['environment'].BrowserProcessExited -= browser_exited
                except Exception:
                    pass
            state['core'], state['environment'] = core, core.Environment
            core.ProcessFailed += process_failed
            core.Environment.BrowserProcessExited += browser_exited
        window._renderer_failed = False
        if state['fallback'] is not None:
            state['fallback'].Dispose()
            state['fallback'] = None
        logging.info('Desktop renderer ready: %s', core.Environment.BrowserVersionString)

    def schedule(kind):
        if native.IsDisposed or native.Disposing or state['pending'] == 'recreate' and kind == 'reload':
            return
        window._renderer_failed = True
        state['pending'] = kind
        timer.Stop()
        timer.Start()

    def process_failed(sender, args):
        kind = str(args.ProcessFailedKind)
        logging.error('WebView2 process failed: kind=%s reason=%s exit=%s', kind,
                      getattr(args, 'Reason', ''), getattr(args, 'ExitCode', ''))
        if kind in ('RenderProcessExited', 'FrameRenderProcessExited'):
            schedule('reload')
        elif kind == 'BrowserProcessExited':
            window._renderer_failed = True
            # Recreate after BrowserProcessExited confirms the old environment
            # has released its browser process and profile directory.

    def browser_exited(sender, args):
        if native.IsDisposed or native.Disposing:
            return
        log = logging.error if str(args.BrowserProcessExitKind) == 'Failed' else logging.info
        log('WebView2 browser exited: kind=%s', args.BrowserProcessExitKind)
        if not native.IsDisposed:
            native.BeginInvoke(Action(lambda: schedule('recreate')))

    def fallback():
        if state['fallback'] is None:
            label = Label()
            label.Dock = DockStyle.Fill
            label.BackColor = Color.FromArgb(16, 17, 22)
            label.ForeColor = Color.FromArgb(232, 227, 242)
            label.Font = Font('Segoe UI', 12)
            label.TextAlign = ContentAlignment.MiddleCenter
            label.Text = 'The display stopped.\nClose and reopen Lean Plan.'
            native.Controls.Add(label)
            label.BringToFront()
            state['fallback'] = label

    def recover(*_):
        timer.Stop()
        kind, state['pending'] = state['pending'], None
        if native.IsDisposed or kind is None:
            return
        now = time.monotonic()
        state['attempts'] = [stamp for stamp in state['attempts'] if now-stamp < 60]
        if len(state['attempts']) >= 3:
            logging.error('Desktop renderer recovery stopped after repeated failures')
            fallback()
            return
        state['attempts'].append(now)
        try:
            logging.info('Recovering desktop renderer: %s', kind)
            if kind == 'reload':
                native.browser.webview.CoreWebView2.Reload()
            else:
                old = native.browser
                current_url = old.url or window.real_url
                window.real_url = current_url
                old.webview.Dispose()
                native.browser = type(old)(native, window, old.user_data_folder)
        except Exception:
            logging.exception('Desktop renderer recovery failed')
            if kind == 'reload':
                schedule('recreate')
            else:
                fallback()

    def cleanup(*_):
        timer.Stop()
        timer.Dispose()
        if state['core'] is not None:
            try:
                state['core'].ProcessFailed -= process_failed
                state['environment'].BrowserProcessExited -= browser_exited
            except Exception:
                pass

    timer.Tick += recover
    native.FormClosed += cleanup
    window._renderer_recovery = attach
    window._renderer_callbacks = (state, timer, attach, recover, process_failed, browser_exited, cleanup)
    native.Invoke(Action(attach))


def install_autosave_close_guard(window) -> None:
    """Let the last local write finish before destroying the desktop window."""
    waiting = False
    allow_close = False

    def completed(result):
        nonlocal waiting, allow_close
        waiting = False
        if isinstance(result, dict) and result.get('ok'):
            allow_close = True
            window.destroy()

    def flush_before_close():
        nonlocal waiting, allow_close
        try:
            if window.evaluate_js('Boolean(window.leanplanPending)'):
                window.evaluate_js(
                    "window.flushAll().then(() => ({ok:true})).catch(() => ({ok:false}))",
                    callback=completed,
                )
            else:
                allow_close = True
                window.destroy()
        except Exception:
            logging.exception('Could not inspect pending autosave on close')
            waiting = False
            allow_close = True
            window.destroy()

    def closing():
        nonlocal waiting, allow_close
        if allow_close or getattr(window, '_renderer_failed', False):
            allow_close = True
            return
        if not waiting:
            waiting = True
            # Closing events run on the UI thread; JS must be evaluated from
            # a worker after the event returns, otherwise WebView2 deadlocks.
            threading.Thread(target=flush_before_close, daemon=True).start()
        return False

    window.events.closing += closing
