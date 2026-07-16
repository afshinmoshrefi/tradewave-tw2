"""Bounded, connection-reusing HTTP facade for appserver outbound calls."""

import os
import threading

import requests as _requests
from requests.adapters import HTTPAdapter


class PooledHttp:
    """Requests-compatible subset with one Session per thread and a process cap."""

    exceptions = _requests.exceptions
    RequestException = _requests.RequestException

    def __init__(self):
        limit = max(1, int(os.environ.get("TW2_OUTBOUND_MAX_INFLIGHT", "16")))
        self._slots = threading.BoundedSemaphore(limit)
        self._local = threading.local()

    def _session(self):
        session = getattr(self._local, "session", None)
        if session is None:
            session = _requests.Session()
            adapter = HTTPAdapter(pool_connections=4, pool_maxsize=4, pool_block=True)
            session.mount("http://", adapter)
            session.mount("https://", adapter)
            self._local.session = session
        return session

    def request(self, method, url, **kwargs):
        kwargs.setdefault("timeout", (5, 60))
        with self._slots:
            return self._session().request(method, url, **kwargs)

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)

    def put(self, url, **kwargs):
        return self.request("PUT", url, **kwargs)

    def delete(self, url, **kwargs):
        return self.request("DELETE", url, **kwargs)


http = PooledHttp()
