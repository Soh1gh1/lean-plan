"""Lean Plan: a private, local weight and energy journal."""
from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
import threading
import webbrowser

from leanplan.server import create_server
from leanplan.store import Store
from leanplan.desktop import (force_dark_window, install_autosave_close_guard,
                             install_fixed_window_geometry, enable_per_monitor_dpi,
                             install_renderer_recovery,
                             CANVAS_WIDTH, CANVAS_HEIGHT)


def main() -> None:
    parser = argparse.ArgumentParser(description="Lean Plan — your local daily journal")
    parser.add_argument("--browser", action="store_true", help="Open in a browser")
    parser.add_argument("--no-open", action="store_true", help="Run only the local server")
    parser.add_argument("--port", type=int, default=0, help="Local port (0 = automatic)")
    parser.add_argument("--data-dir", type=Path, default=None)
    args = parser.parse_args()
    enable_per_monitor_dpi()
    root = Path(__file__).resolve().parent
    data_dir = args.data_dir or Path(os.environ.get("LEANPLAN_DATA_DIR", str(root / "data")))
    data_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=data_dir / "app.log", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8")
    store = Store(data_dir)
    server = create_server(store, root / "static", args.port)
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"Lean Plan: {url}", flush=True)
    logging.info("Workspace available at %s", url)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        if args.no_open:
            thread.join()
        elif args.browser:
            webbrowser.open(url)
            thread.join()
        else:
            try:
                import webview
            except ImportError:
                webbrowser.open(url)
                thread.join()
            else:
                webview.settings["ALLOW_DOWNLOADS"] = True
                try:
                    window = webview.create_window("Lean Plan", url,
                                                   width=CANVAS_WIDTH, height=CANVAS_HEIGHT,
                                                   min_size=(320, 240), resizable=False,
                                                   fullscreen=False, maximized=False,
                                                   zoomable=False, hidden=True,
                                                   background_color="#101116")
                    def on_loaded():
                        force_dark_window(window)
                        install_renderer_recovery(window)
                        try:
                            install_fixed_window_geometry(window)
                        finally:
                            window.show()
                        logging.info("Desktop window loaded")
                    window.events.loaded += on_loaded
                    install_autosave_close_guard(window)
                    icon = root / "tools" / "leanplan.ico"
                    webview.start(gui='edgechromium', icon=str(icon) if icon.exists() else None)
                except Exception:
                    logging.exception("Desktop renderer unavailable; opening the browser")
                    webbrowser.open(url)
                    thread.join()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
