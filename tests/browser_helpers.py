"""Headless Chromium automation over the DevTools protocol, for browser fixture tests.

Uses a throw-away browser profile (no account, no cookies). Requests to
``https://www.youtube.com/*`` can be intercepted and answered with local fixture content, so the
real extension's content script runs against a controlled page at a real Shorts URL without any
network access.
"""

from __future__ import annotations

import base64
import contextlib
import itertools
import json
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from websockets.sync.client import ClientConnection, connect

EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
EXTENSION_DIR = Path(__file__).resolve().parents[1] / "browser_extension"
EXTENSION_ID = "phcdgkmcjbgdligepbkfkceejlbbmlio"


def find_browser(prefer_extension_support: bool) -> Path | None:
    """Edge loads unpacked extensions from the command line; branded Chrome no longer does."""
    order = [EDGE] if prefer_extension_support else [EDGE, CHROME]
    return next((p for p in order if p.is_file()), None)


class Session:
    """One DevTools target (page or service worker) with an event-reading thread."""

    def __init__(self, ws_url: str, target_id: str = "") -> None:
        self.target_id = target_id
        self._ws: ClientConnection = connect(ws_url, max_size=None, open_timeout=10)
        self._ids = itertools.count(1)
        self._lock = threading.Lock()
        self._waiters: dict[int, tuple[threading.Event, dict]] = {}
        self._handlers: dict[str, Callable[[dict], None]] = {}
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()

    def _read(self) -> None:
        with contextlib.suppress(Exception):
            for raw in self._ws:
                message = json.loads(raw)
                if "id" in message:
                    with self._lock:
                        waiter = self._waiters.pop(message["id"], None)
                    if waiter:
                        waiter[1].update(message)
                        waiter[0].set()
                elif message.get("method") in self._handlers:
                    handler = self._handlers[message["method"]]
                    threading.Thread(target=handler, args=(message["params"],), daemon=True).start()

    def on(self, method: str, handler: Callable[[dict], None]) -> None:
        self._handlers[method] = handler

    def call(self, method: str, timeout: float = 30.0, **params: Any) -> dict:
        request_id = next(self._ids)
        event = threading.Event()
        box: dict = {}
        with self._lock:
            self._waiters[request_id] = (event, box)
        self._ws.send(json.dumps({"id": request_id, "method": method, "params": params}))
        if not event.wait(timeout):
            raise TimeoutError(method)
        if "error" in box:
            raise RuntimeError(f"{method}: {box['error']}")
        return box.get("result", {})

    def eval(self, expression: str, timeout: float = 30.0) -> Any:
        result = self.call(
            "Runtime.evaluate",
            timeout=timeout,
            expression=expression,
            returnByValue=True,
            awaitPromise=True,
        )
        if "exceptionDetails" in result:
            raise RuntimeError(result["exceptionDetails"])
        return result["result"].get("value")

    def wait_for(self, expression: str, timeout: float = 15.0) -> Any:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with contextlib.suppress(RuntimeError):
                value = self.eval(expression)
                if value:
                    return value
            time.sleep(0.1)
        raise TimeoutError(expression)

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self._ws.close()


class Browser:
    def __init__(
        self, executable: Path, port: int, extension: bool = False, headless: bool = True
    ) -> None:
        self.profile = tempfile.mkdtemp(prefix="is-test-browser-")
        args = [
            str(executable),
            "--headless=new" if headless else "--window-position=-3000,0",
            f"--remote-debugging-port={port}",
            f"--user-data-dir={self.profile}",
            "--no-first-run",
            "--no-default-browser-check",
            "--window-size=1280,900",
            "--autoplay-policy=no-user-gesture-required",
            "--lang=en-US",
        ]
        if extension:
            args.append(f"--load-extension={EXTENSION_DIR}")
        self.port = port
        self.process = subprocess.Popen(
            [*args, "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            with contextlib.suppress(OSError):
                urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1)
                return
            time.sleep(0.1)
        self.close()
        raise RuntimeError("browser did not start")

    def targets(self) -> list[dict]:
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json/list") as response:
            return json.load(response)

    def new_tab(self) -> Session:
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/json/new?about:blank", method="PUT"
        )
        with urllib.request.urlopen(request) as response:
            target = json.load(response)
        session = Session(target["webSocketDebuggerUrl"], target["id"])
        self.activate(session)
        return session

    def activate(self, session: Session) -> None:
        """Bring the tab to the front (visible browsers may open other tabs at startup)."""
        url = f"http://127.0.0.1:{self.port}/json/activate/{session.target_id}"
        with urllib.request.urlopen(url):
            pass

    def extension_worker(self, timeout: float = 10.0) -> Session:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for target in self.targets():
                if target["type"] == "service_worker" and EXTENSION_ID in target["url"]:
                    session = Session(target["webSocketDebuggerUrl"])
                    # The worker target can appear before its extension APIs are bound.
                    session.wait_for(
                        "typeof chrome !== 'undefined' && !!chrome.storage && "
                        "typeof connect === 'function'",
                        timeout=max(1.0, deadline - time.monotonic()),
                    )
                    return session
            time.sleep(0.2)
        raise TimeoutError("extension service worker not found")

    def close(self) -> None:
        self.process.terminate()
        try:
            self.process.wait(10)
        except subprocess.TimeoutExpired:
            self.process.kill()
        shutil.rmtree(self.profile, ignore_errors=True)


def serve_youtube_fixture(page: Session, files: dict[str, tuple[bytes, str]]) -> None:
    """Answer all www.youtube.com requests from ``files`` (path -> (body, content type)).

    Any ``/shorts/...`` path returns the fixture page; unknown paths return 404.
    """

    def on_paused(params: dict) -> None:
        url = params["request"]["url"]
        path = url.split("www.youtube.com", 1)[1].split("?", 1)[0]
        key = "/shorts/" if path.startswith("/shorts/") else path
        body, content_type = files.get(key, (b"not found", "text/plain"))
        status = 200 if key in files else 404
        with contextlib.suppress(Exception):
            page.call(
                "Fetch.fulfillRequest",
                requestId=params["requestId"],
                responseCode=status,
                responseHeaders=[{"name": "Content-Type", "value": content_type}],
                body=base64.b64encode(body).decode(),
            )

    page.on("Fetch.requestPaused", on_paused)
    page.call("Fetch.enable", patterns=[{"urlPattern": "https://www.youtube.com/*"}])
