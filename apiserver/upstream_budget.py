"""Carry one upstream time budget through a request's sequential and parallel work."""
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar

from flask import g, has_request_context

_deadline = ContextVar('tradewave_upstream_deadline', default=None)


def current_deadline():
    inherited = _deadline.get()
    if inherited is not None:
        return inherited
    return getattr(g, 'upstream_deadline', None) if has_request_context() else None


def parallel_map(function, values, *, max_workers):
    """Workers inherit only the deadline, never Flask customer/authentication state."""
    deadline = current_deadline()

    def bounded(value):
        token = _deadline.set(deadline)
        try:
            return function(value)
        finally:
            _deadline.reset(token)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        return list(executor.map(bounded, values))
