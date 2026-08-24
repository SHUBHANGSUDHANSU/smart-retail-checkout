"""Background Uvicorn ownership for the local OpenCV desktop process."""

from __future__ import annotations

import ipaddress
import logging
import threading
import time

import uvicorn
from fastapi import FastAPI

from smart_retail.infrastructure.logging_config import log_event

LOGGER = logging.getLogger(__name__)


class APIServerError(RuntimeError):
    """Raised when the local HTTP server cannot start."""


class BackgroundAPIServer:
    """Run Uvicorn beside the blocking OpenCV loop and stop it cleanly."""

    def __init__(
        self,
        application: FastAPI,
        host: str,
        port: int,
        startup_timeout_seconds: float = 5.0,
    ) -> None:
        if startup_timeout_seconds <= 0:
            raise ValueError("API startup timeout must be positive.")
        self.host = host
        self.port = port
        self.startup_timeout_seconds = startup_timeout_seconds
        if not _is_loopback_host(host):
            log_event(
                LOGGER,
                logging.WARNING,
                "api_externally_reachable",
                "API is bound beyond loopback without authentication",
                host=host,
                port=port,
            )
        configuration = uvicorn.Config(
            application,
            host=host,
            port=port,
            log_config=None,
            access_log=False,
        )
        self._server = uvicorn.Server(configuration)
        self._thread: threading.Thread | None = None
        self._failure: BaseException | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._run,
            name="smart-retail-api",
            daemon=True,
        )
        self._thread.start()
        deadline = time.monotonic() + self.startup_timeout_seconds
        while time.monotonic() < deadline:
            if self._server.started:
                log_event(
                    LOGGER,
                    logging.INFO,
                    "api_server_started",
                    "FastAPI server started",
                    host=self.host,
                    port=self.port,
                )
                return
            if not self._thread.is_alive():
                reason = str(self._failure) if self._failure else "server stopped"
                raise APIServerError(f"FastAPI server failed to start: {reason}")
            time.sleep(0.05)
        self.stop()
        raise APIServerError("FastAPI server startup timed out.")

    def stop(self) -> None:
        thread = self._thread
        if thread is None:
            return
        self._server.should_exit = True
        thread.join(timeout=5.0)
        if thread.is_alive():
            log_event(
                LOGGER,
                logging.WARNING,
                "api_server_stop_timed_out",
                "FastAPI server did not stop within the timeout",
                host=self.host,
                port=self.port,
            )
            # Retain ownership so a later idempotent shutdown call can retry.
            raise APIServerError("FastAPI server did not stop within the timeout.")
        log_event(
            LOGGER,
            logging.INFO,
            "api_server_stopped",
            "FastAPI server stopped",
            host=self.host,
            port=self.port,
        )
        self._thread = None

    def _run(self) -> None:
        try:
            self._server.run()
        except BaseException as error:
            self._failure = error


def _is_loopback_host(host: str) -> bool:
    normalized = host.strip().strip("[]")
    if normalized.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False
