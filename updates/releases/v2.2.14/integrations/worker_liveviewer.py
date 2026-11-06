"""SHADOW LIVE VIEWER — ultra-quality, on-demand, read-only companion.

Location: integrations/worker_liveviewer.py

The Playwright worker owns its Firefox page. This module never clicks, navigates,
logs in, changes proxies, or stops the browser when the viewer is closed.

High-resolution on-demand preview (on the PAGE-OWNING WORKER THREAD):

    from integrations.worker_liveviewer import LiveViewerBridge

    bridge = LiveViewerBridge("Browser #1").start()
    # GUI Show button (on GUI thread): bridge.show()
    # Inside worker's existing session loop:
    while session_is_active:
        bridge.sync_screencast(page)  # calls Playwright only on owning thread
        page.wait_for_timeout(100)     # pumps the Playwright event loop
    bridge.stop_screencast(page)       # on owning thread at session end
    bridge.close()                    # closes only viewer/transport

A screencast runs ONLY while the viewer process is open. Closing the viewer
window leaves Firefox running. Playwright 1.59+ is required for screencast.
The stream is JPEG at quality 100 (the maximum supported by this API).

Offline test: python integrations/worker_liveviewer.py --demo
"""

from __future__ import annotations

import argparse
import hmac
import os
from pathlib import Path
import secrets
import socket
import struct
import subprocess
import sys
import threading
import time
from typing import Optional

MAX_FRAME_BYTES = 32 * 1024 * 1024  # 4K/large JPEG support
MAX_VIEW_FPS = 25  # maximum currently produced by Firefox screencast
CAPTURE_QUALITY = 100  # maximum JPEG quality supported by screencast
CAPTURE_SIZE = {"width": 3840, "height": 2160}  # 4K upper bound; actual detail depends on browser viewport
_KEEPALIVE_SECONDS = 1.5


def _read_exact(sock: socket.socket, size: int) -> bytes:
    parts = bytearray()
    while len(parts) < size:
        part = sock.recv(size - len(parts))
        if not part:
            raise ConnectionError('Stream ended')
        parts.extend(part)
    return bytes(parts)


def _send_packet(sock: socket.socket, payload: bytes) -> None:
    if len(payload) > MAX_FRAME_BYTES:
        return
    sock.sendall(struct.pack('!I', len(payload)) + payload)


class LiveViewerBridge:
    """Publish-only stream endpoint; owns NO browser or Playwright objects.

    - start(): allocate a local 127.0.0.1 listener, once per session.
    - publish(jpeg): very cheap; overwrites the latest frame, no frame queue.
    - show(): launch the independent viewer process, or raise existing one.
    - hide(): close the VIEWER only; the headless session is unaffected.
    - sync_screencast(page): called only on Playwright's owning worker thread.
      Starts capture when Show was pressed, stops when viewer is closed.
    - close(): close stream when the browser session ends; viewer exits.

    This class can be used from a QThread worker; only the viewer needs Qt.
    """

    def __init__(
        self,
        title: str,
        max_fps: int = MAX_VIEW_FPS,
        quality: int = CAPTURE_QUALITY,
        capture_size: Optional[dict] = None,
    ):
        self.title = str(title)
        self.max_fps = max(1, min(25, int(max_fps)))
        self.quality = max(0, min(100, int(quality)))
        self.capture_size = dict(capture_size or CAPTURE_SIZE)
        self._casting = False  # exclusively owned by the Playwright worker thread
        self._page_owner_thread_id: Optional[int] = None
        self._token = secrets.token_hex(24)
        self._listener: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._client: Optional[socket.socket] = None
        self._process: Optional[subprocess.Popen] = None
        self._closed = threading.Event()
        self._lock = threading.Condition()
        self._latest: Optional[bytes] = None
        self._seq = 0
        self.port: Optional[int] = None

    def start(self) -> 'LiveViewerBridge':
        if self._closed.is_set():
            raise RuntimeError('This bridge has already been closed')
        if self._listener is not None:
            return self
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(('127.0.0.1', 0))
        listener.listen(2)
        listener.settimeout(0.5)
        self.port = listener.getsockname()[1]
        self._listener = listener
        self._thread = threading.Thread(
            target=self._accept_loop,
            name=f'LiveViewerBridge-{self.port}',
            daemon=True,
        )
        self._thread.start()
        return self

    def publish(self, jpeg: bytes) -> None:
        """Thread-safe: discard older frames; don't block Playwright worker."""
        if self._closed.is_set() or not isinstance(jpeg, bytes):
            return
        if not jpeg.startswith(b'\xff\xd8') or len(jpeg) > MAX_FRAME_BYTES:
            return
        with self._lock:
            self._latest = jpeg
            self._seq += 1
            self._lock.notify_all()

    @property
    def viewer_open(self) -> bool:
        """Safe to read from worker thread; does not touch browser objects."""
        proc = self._process
        return (
            not self._closed.is_set()
            and proc is not None
            and proc.poll() is None
        )

    def _assert_page_thread(self) -> None:
        """Prevent accidental calls into Playwright from the Qt GUI thread."""
        current = threading.get_ident()
        if self._page_owner_thread_id is None:
            self._page_owner_thread_id = current
        elif self._page_owner_thread_id != current:
            raise RuntimeError("Screencast must be controlled from the page-owning thread")

    def sync_screencast(self, page) -> None:
        """On worker thread: start/stop high-quality cast based on viewer state.

        The caller must keep pumping the Playwright loop, e.g. by calling
        page.wait_for_timeout(100) during its existing hold loop.
        """
        self._assert_page_thread()
        should_stream = self.viewer_open
        if should_stream and not self._casting:
            # This is the only place where the Playwright page is accessed.
            page.screencast.start(
                on_frame=lambda frame: self.publish(frame["data"]),
                quality=self.quality,
                size=self.capture_size,
            )
            self._casting = True
        elif not should_stream and self._casting:
            try:
                page.screencast.stop()
            finally:
                self._casting = False

    def stop_screencast(self, page) -> None:
        """On worker thread at session end. No browser/page closing here."""
        self._assert_page_thread()
        if self._casting:
            try:
                page.screencast.stop()
            finally:
                self._casting = False

    def show(self) -> None:
        """Open viewer without touching the browser. May be called from Qt UI."""
        self.start()
        if self.viewer_open:
            # Already open. Repeated Show must not create duplicate viewers.
            return
        with self._lock:
            self._latest = None  # never show a frame from an older viewer session
            self._seq += 1
            self._lock.notify_all()
        args = [
            sys.executable,
            str(Path(__file__).resolve()),
            '--viewer',
            '--port', str(self.port),
            '--token', self._token,
            '--title', self.title,
        ]
        kwargs = {}
        if os.name == 'nt':
            kwargs['creationflags'] = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        self._process = subprocess.Popen(args, **kwargs)

    def hide(self) -> None:
        """Stop only the viewer process; no browser/context operations."""
        proc = self._process
        if proc is None:
            return
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
        self._process = None
        with self._lock:
            self._latest = None
            self._seq += 1
            self._lock.notify_all()

    def close(self) -> None:
        """Called only when the underlying worker/session has finished."""
        if self._closed.is_set():
            return
        self._closed.set()
        # Call stop_screencast(page) on the worker thread BEFORE close().
        # This method intentionally never touches Playwright from this thread.
        with self._lock:
            self._lock.notify_all()
        listener = self._listener
        self._listener = None
        if listener is not None:
            try:
                listener.close()
            except OSError:
                pass
        client = self._client
        if client is not None:
            try:
                client.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                client.close()
            except OSError:
                pass
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=1.0)
        self.hide()
        with self._lock:
            self._latest = None

    def _accept_loop(self) -> None:
        while not self._closed.is_set():
            listener = self._listener
            if listener is None:
                return
            try:
                client, _ = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            self._client = client
            try:
                self._serve(client)
            except (OSError, ConnectionError, TimeoutError):
                pass
            finally:
                try:
                    client.close()
                except OSError:
                    pass
                if self._client is client:
                    self._client = None

    def _serve(self, sock: socket.socket) -> None:
        sock.settimeout(3.0)
        line = bytearray()
        while len(line) <= 64 and not line.endswith(b'\n'):
            part = sock.recv(1)
            if not part:
                return
            line.extend(part)
        token = line.rstrip(b'\r\n').decode('ascii', errors='ignore')
        if not hmac.compare_digest(token, self._token):
            return
        # Every packet is one uint32 length + JPEG. Zero length = heartbeat.
        sock.settimeout(2.0)
        last_seq = -1
        last_frame_sent = 0.0
        last_packet_sent = 0.0
        while not self._closed.is_set():
            with self._lock:
                if self._seq == last_seq:
                    self._lock.wait(timeout=0.12)
                current_seq = self._seq
                jpeg = self._latest
            now = time.monotonic()
            if jpeg is not None and current_seq != last_seq:
                if now - last_frame_sent < 1.0 / self.max_fps:
                    time.sleep(min(0.03, 1.0 / self.max_fps - (now - last_frame_sent)))
                    continue
                _send_packet(sock, jpeg)
                last_seq = current_seq
                last_frame_sent = last_packet_sent = time.monotonic()
            elif now - last_packet_sent >= _KEEPALIVE_SECONDS:
                _send_packet(sock, b'')
                last_packet_sent = now

    def __enter__(self) -> 'LiveViewerBridge':
        return self.start()

    def __exit__(self, _exc_type, _exc_value, _traceback) -> None:
        self.close()


def _run_viewer(port: int, token: str, title: str) -> None:
    """Standalone, read-only viewer. It never owns or controls Firefox.

    The receiver keeps only the newest decoded frame. The Qt GUI polls that
    single frame at a bounded rate; this avoids an unbounded queued-signal
    backlog and avoids repeatedly constructing QGraphicsScene/QPixmap objects.
    """
    # Keep imports lazy so the page-owning worker does not load Qt Web/UI.
    from PySide6.QtCore import QPointF, QRectF, QThread, Qt, QTimer
    from PySide6.QtGui import QColor, QImage, QPainter, QPen
    from PySide6.QtWidgets import (
        QApplication, QHBoxLayout, QLabel, QPushButton,
        QVBoxLayout, QWidget,
    )

    class SocketReceiver(QThread):
        def __init__(self, parent=None):
            super().__init__(parent)
            self._sock: Optional[socket.socket] = None
            self._sock_lock = threading.Lock()
            self._frame_lock = threading.Lock()
            self._latest_frame: Optional[QImage] = None
            self._ended = False

        def take_latest(self) -> Optional[QImage]:
            """Atomically take the last image, discarding superseded frames."""
            with self._frame_lock:
                image = self._latest_frame
                self._latest_frame = None
            return image

        @property
        def ended(self) -> bool:
            with self._frame_lock:
                return self._ended

        def stop(self) -> None:
            self.requestInterruption()
            with self._sock_lock:
                sock = self._sock
            if sock is not None:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

        def run(self) -> None:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            with self._sock_lock:
                self._sock = sock
            try:
                deadline = time.monotonic() + 5.0
                while not self.isInterruptionRequested():
                    try:
                        sock.connect(('127.0.0.1', port))
                        break
                    except (ConnectionRefusedError, TimeoutError):
                        if time.monotonic() > deadline:
                            return
                        self.msleep(150)
                if self.isInterruptionRequested():
                    return
                sock.sendall(token.encode('ascii') + b'\n')
                sock.settimeout(3.0)
                while not self.isInterruptionRequested():
                    header = _read_exact(sock, 4)
                    length = struct.unpack('!I', header)[0]
                    if length == 0:
                        continue  # heartbeat
                    if length > MAX_FRAME_BYTES:
                        return
                    jpeg = _read_exact(sock, length)
                    image = QImage.fromData(jpeg, 'JPEG')
                    if not image.isNull():
                        with self._frame_lock:
                            # No Qt signal carrying every frame; only the latest survives.
                            self._latest_frame = image
            except (OSError, ConnectionError, TimeoutError):
                pass
            finally:
                with self._sock_lock:
                    self._sock = None
                try:
                    sock.close()
                except OSError:
                    pass
                with self._frame_lock:
                    self._ended = True

    class ImageCanvas(QWidget):
        """Small, low-overhead image canvas; no scene graph or video engine.

        FIT shows the *entire* desktop source without changing Firefox zoom.
        75% / 100% / 150% allow panning to read text in a compact window.
        The Sharp switch selects nearest-pixel vs smooth scaling.
        """
        def __init__(self, parent=None):
            super().__init__(parent)
            self._frame: Optional[QImage] = None
            self._mode = 'FIT'
            self._sharp = True
            self._pan = QPointF(0.0, 0.0)
            self._drag_at: Optional[QPointF] = None
            self.setMinimumSize(320, 240)
            self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
            self.setCursor(Qt.CursorShape.ArrowCursor)

        def set_frame(self, image: QImage) -> None:
            self._frame = image
            self.update()  # coalesced by Qt, no extra image/scene allocations

        def clear_frame(self) -> None:
            self._frame = None
            self._pan = QPointF()
            self.update()

        def set_mode(self, mode: str) -> None:
            if mode not in ('FIT', '75%', '100%', '150%'):
                return
            self._mode = mode
            self._pan = QPointF()
            self._set_cursor()
            self.update()

        def set_sharp(self, enabled: bool) -> None:
            self._sharp = bool(enabled)
            self.update()

        def _set_cursor(self) -> None:
            self.setCursor(
                Qt.CursorShape.ArrowCursor if self._mode == 'FIT'
                else Qt.CursorShape.OpenHandCursor
            )

        def _image_rect(self) -> Optional[QRectF]:
            image = self._frame
            if image is None or image.isNull():
                return None
            # One logical-pixel margin prevents image edges overlapping the border.
            vw = max(1.0, float(self.width() - 2))
            vh = max(1.0, float(self.height() - 2))
            sw, sh = float(image.width()), float(image.height())
            if self._mode == 'FIT':
                factor = min(vw / sw, vh / sh, 1.0)
            else:
                # Express percentage in physical screen pixels, not Qt logical
                # pixels, so 100% means an actual 1:1 source-to-display pixel.
                percentages = {'75%': 0.75, '100%': 1.0, '150%': 1.5}
                factor = percentages[self._mode] / max(1.0, self.devicePixelRatioF())
            dw, dh = sw * factor, sh * factor
            limit_x = max(0.0, (dw - vw) / 2.0)
            limit_y = max(0.0, (dh - vh) / 2.0)
            if self._mode == 'FIT':
                self._pan = QPointF()
            else:
                self._pan.setX(min(limit_x, max(-limit_x, self._pan.x())))
                self._pan.setY(min(limit_y, max(-limit_y, self._pan.y())))
            x = (self.width() - dw) * 0.5 + self._pan.x()
            y = (self.height() - dh) * 0.5 + self._pan.y()
            return QRectF(x, y, dw, dh)

        def paintEvent(self, _event) -> None:
            painter = QPainter(self)
            painter.fillRect(self.rect(), QColor('#20282c'))
            image = self._frame
            if image is not None and not image.isNull():
                target = self._image_rect()
                if target is not None:
                    painter.setClipRect(self.rect().adjusted(1, 1, -1, -1))
                    # No opacity changes, image darkening, or double resampling.
                    # Sharp mode favors crisp pixels; Smooth remains optional.
                    painter.setRenderHint(
                        QPainter.RenderHint.SmoothPixmapTransform,
                        not self._sharp,
                    )
                    painter.drawImage(target, image)
                    painter.setClipping(False)
            else:
                painter.setPen(QColor('#9eaaaf'))
                painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                                 'Waiting for live frame…')
            painter.setPen(QPen(QColor('#526168'), 1))
            painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
            painter.end()

        def mousePressEvent(self, event) -> None:
            if (self._mode != 'FIT'
                    and event.button() == Qt.MouseButton.LeftButton):
                self._drag_at = event.position()
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                event.accept()
                return
            super().mousePressEvent(event)

        def mouseMoveEvent(self, event) -> None:
            if self._drag_at is not None:
                delta = event.position() - self._drag_at
                self._pan += delta
                self._drag_at = event.position()
                self.update()
                event.accept()
                return
            super().mouseMoveEvent(event)

        def mouseReleaseEvent(self, event) -> None:
            if event.button() == Qt.MouseButton.LeftButton and self._drag_at is not None:
                self._drag_at = None
                self._set_cursor()
                event.accept()
                return
            super().mouseReleaseEvent(event)

    class LiveWindow(QWidget):
        def __init__(self):
            super().__init__()
            self.setWindowTitle(f'{title} — SHADOW LIVE VIEWER')
            self.resize(770, 560)  # compact; not larger than the previous 810x625
            self.setMinimumSize(510, 355)
            self.setStyleSheet("""
                QWidget { background: #30393f; color: #f2f4f5;
                    font-family: Segoe UI; font-size: 11px; }
                QLabel { background: transparent; }
                QPushButton { background: #424d54; color: #f2f4f5;
                    border-radius: 5px; border: 1px solid #617078;
                    padding: 5px 9px; min-height: 22px; }
                QPushButton:hover { background: #53636a; }
                QPushButton:checked { background: #586b72;
                    border: 1px solid #a4b3ba; }
            """)
            self._closing = False
            self._canvas = ImageCanvas(self)
            self._frames = 0
            self._current_fps = 0
            self._img_size = (0, 0)
            self._mode = '75%'
            self._canvas.set_mode('75%')

            heading = QLabel(f'●  LIVE   {title}')
            heading.setStyleSheet('color: #dce8e5; font-weight: 600;')
            detail = QLabel('FIREFOX · READ ONLY')
            detail.setStyleSheet('color: #a9b7bd;')
            top = QHBoxLayout()
            top.setSpacing(6)
            top.addWidget(heading)
            top.addWidget(detail)
            top.addStretch(1)

            self._mode_buttons = {}
            for label in ('Fit', '75%', '100%', '150%'):
                button = QPushButton(label)
                button.setCheckable(True)
                button.clicked.connect(lambda checked=False, mode=label: self.set_mode(mode))
                self._mode_buttons[label.upper()] = button
                top.addWidget(button)
            self.btn_sharp = QPushButton('Sharp')
            self.btn_sharp.setCheckable(True)
            self.btn_sharp.setChecked(True)
            self.btn_sharp.setToolTip('Sharp pixels (off = smooth scaling)')
            self.btn_sharp.toggled.connect(self._canvas.set_sharp)
            top.addWidget(self.btn_sharp)
            self._mode_buttons['75%'].setChecked(True)

            self.status = QLabel('Connecting to live session…')
            self.status.setStyleSheet('color: #aebcc2; padding: 0px 3px;')
            layout = QVBoxLayout(self)
            layout.setContentsMargins(9, 9, 9, 8)
            layout.setSpacing(7)
            layout.addLayout(top)
            layout.addWidget(self._canvas, 1)
            layout.addWidget(self.status)

            self._receiver = SocketReceiver(self)
            self._receiver.start()
            self._draw_timer = QTimer(self)
            self._draw_timer.setInterval(33)  # GUI paints only the latest image
            self._draw_timer.timeout.connect(self._poll_frame)
            self._draw_timer.start()
            self._fps_timer = QTimer(self)
            self._fps_timer.setInterval(1000)
            self._fps_timer.timeout.connect(self._update_fps)
            self._fps_timer.start()

        def _poll_frame(self) -> None:
            if self._closing:
                return
            image = self._receiver.take_latest()
            if image is not None and not image.isNull():
                self._frames += 1
                self._img_size = (image.width(), image.height())
                self._canvas.set_frame(image)
            if self._receiver.ended:
                self.close()  # source session is gone; avoid stale image

        def _update_text(self) -> None:
            w, h = self._img_size
            self.status.setText(
                f'LIVE  •  {w}×{h}  •  {self._mode}  •  '
                f'{self._current_fps} FPS  •  JPEG Q100  •  '
                f'{"SHARP" if self.btn_sharp.isChecked() else "SMOOTH"}  •  READ ONLY'
            )

        def _update_fps(self) -> None:
            self._current_fps = self._frames
            self._frames = 0
            if self._img_size != (0, 0):
                self._update_text()

        def set_mode(self, mode: str) -> None:
            mode = mode.upper()
            self._mode = mode
            for key, button in self._mode_buttons.items():
                button.setChecked(key == mode)
            self._canvas.set_mode(mode)
            if self._img_size != (0, 0):
                self._update_text()

        def closeEvent(self, event) -> None:
            if self._closing:
                event.accept()
                return
            self._closing = True
            self._fps_timer.stop()
            self._draw_timer.stop()
            self._receiver.stop()
            self._receiver.wait(2500)
            self._canvas.clear_frame()
            event.accept()

    app = QApplication(sys.argv[:1])
    win = LiveWindow()
    win.show()
    sys.exit(app.exec())


def _demo(duration: float) -> None:
    """Offline example — completely unrelated to user accounts or proxies."""
    from playwright.sync_api import sync_playwright

    html = '''<!doctype html><html><head><meta charset="utf-8">
    <style>body{background:#f6f6f6;font:28px Segoe UI,Arial;margin:5%}
    .box{padding:60px;border-radius:14px;background:white;box-shadow:0 2px 20px #ddd}
    h1{color:#3d6d78}code{color:#28a078}</style></head><body>
    <div class="box"><h1>SHADOW LIVE VIEWER</h1>
    <p>Offline Playwright Firefox screencast demo</p>
    <p>Elapsed time: <code id="s">0</code> seconds</p>
    <p>Close the viewer: Firefox continues in the background.</p>
    </div><script>let n=0;setInterval(()=>{document.querySelector('#s').textContent=++n},1000)</script>
    </body></html>'''
    with LiveViewerBridge('Demo Browser #1') as bridge, sync_playwright() as playwright:
        browser = playwright.firefox.launch(headless=True)
        try:
            context = browser.new_context(viewport={'width': 1920, 'height': 1080})
            page = context.new_page()
            page.goto('data:text/html;charset=utf-8,' + __import__('urllib.parse', fromlist=['quote']).quote(html))
            bridge.show()
            print('Viewer started at JPEG quality 100, up to 4K max frame / 25 FPS.')
            print('Closing only the viewer window will NOT stop Firefox.')
            print(f'Demo session ends automatically in {duration:g} seconds.')
            deadline = time.monotonic() + duration
            try:
                while time.monotonic() < deadline:
                    bridge.sync_screencast(page)
                    page.wait_for_timeout(100)
            finally:
                bridge.stop_screencast(page)
                context.close()
        finally:
            browser.close()


def main() -> None:
    p = argparse.ArgumentParser(description='Read-only Firefox Playwright screencast viewer')
    p.add_argument('--viewer', action='store_true')
    p.add_argument('--demo', action='store_true')
    p.add_argument('--port', type=int, default=0)
    p.add_argument('--token', default='')
    p.add_argument('--title', default='Browser')
    p.add_argument('--duration', type=float, default=25)
    args = p.parse_args()
    if args.viewer:
        if not (1 <= args.port <= 65535 and len(args.token) == 48):
            p.error('Viewer requires a valid port and token')
        _run_viewer(args.port, args.token, args.title)
    elif args.demo:
        _demo(args.duration)
    else:
        p.print_help()


if __name__ == '__main__':
    main()
