
# integrations/proxy_pool.py
# SHADOW SUITE PRO — Verified Proxy Pool

from collections import deque
from dataclasses import dataclass
from threading import Condition
from typing import Any
import time


@dataclass(frozen=True)
class ProxyLease:
    key: tuple
    proxy: Any
    protocol: str
    exit_ip: str
    owner: str


class ProxyPool:
    def __init__(self):
        self._condition = Condition()
        self._available = deque()
        self._registered = {}
        self._leased = {}
        self._waiting = deque()
        self._closed = False

    @staticmethod
    def _key(proxy, protocol):
        return (
            proxy.host.lower(),
            proxy.port,
            proxy.username,
            proxy.password,
            protocol,
        )

    def add_verified(self, proxy, protocol, exit_ip):
        """Add a verified proxy only once."""
        key = self._key(proxy, protocol)

        with self._condition:
            if self._closed or key in self._registered:
                return False

            self._registered[key] = (
                proxy, protocol, exit_ip
            )
            self._available.append(key)
            self._condition.notify_all()
            return True

    def acquire(self, owner, timeout=None):
        """Reserve one proxy, respecting FIFO waiting order."""
        deadline = (
            None if timeout is None
            else time.monotonic() + timeout
        )

        ticket = object()

        with self._condition:
            if self._closed:
                return None

            if any(
                lease.owner == owner
                for lease in self._leased.values()
            ):
                raise ValueError("Owner already has a lease")

            self._waiting.append(ticket)

            try:
                while not self._closed:
                    first = self._waiting[0] is ticket

                    if first and self._available:
                        key = self._available.popleft()
                        self._waiting.popleft()

                        proxy, protocol, exit_ip = (
                            self._registered[key]
                        )

                        lease = ProxyLease(
                            key=key,
                            proxy=proxy,
                            protocol=protocol,
                            exit_ip=exit_ip,
                            owner=owner,
                        )

                        self._leased[key] = lease
                        self._condition.notify_all()
                        return lease

                    remaining = (
                        None if deadline is None
                        else deadline - time.monotonic()
                    )

                    if remaining is not None and remaining <= 0:
                        return None

                    self._condition.wait(remaining)

                return None

            finally:
                if ticket in self._waiting:
                    self._waiting.remove(ticket)
                    self._condition.notify_all()

    def release(self, lease):
        """Return a reserved proxy to the available pool."""
        with self._condition:
            current = self._leased.get(lease.key)

            if current is not lease:
                return False

            del self._leased[lease.key]

            if not self._closed:
                self._available.append(lease.key)

            self._condition.notify_all()
            return True

    def stats(self):
        with self._condition:
            return {
                "total": len(self._registered),
                "available": len(self._available),
                "in_use": len(self._leased),
                "waiting": len(self._waiting),
                "closed": self._closed,
            }

    def close(self):
        with self._condition:
            self._closed = True
            self._condition.notify_all()
