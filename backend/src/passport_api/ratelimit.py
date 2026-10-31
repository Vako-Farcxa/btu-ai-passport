"""Light, free rate limiting that lives in this process's memory.

Render's free plan runs one process, so a plain in-memory counter is enough. A restart
forgets the counts, which is fine: this protects the API from a flood, it is not a billing
meter. Real users never come near the limits.

Each bucket keeps the times of the last `limit` accepted requests per key. A request is
refused when that many already happened in the last `WINDOW_SECONDS`; refused requests are
not recorded, so waiting out `Retry-After` always works.
"""

import ipaddress
import math
import threading
import time
from collections import OrderedDict, deque

from fastapi import Request

from passport_api.errors import RateLimitedError
from passport_api.settings import settings

WINDOW_SECONDS = 60.0
# One entry per active key. Past this many keys the oldest are dropped, so a flood of
# made-up addresses cannot grow memory without bound.
MAX_KEYS = 10_000


class RateLimits:
    def __init__(self, *, max_keys: int = MAX_KEYS) -> None:
        self._max_keys = max_keys
        self._lock = threading.Lock()
        self._hits: OrderedDict[tuple[str, str], deque[float]] = OrderedDict()

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()

    def check(self, bucket: str, key: str, limit: int, *, now: float | None = None) -> int | None:
        """Record one request. Returns None when allowed, else whole seconds to wait.

        A limit of 0 or less turns that bucket off.
        """
        if limit <= 0:
            return None
        moment = time.monotonic() if now is None else now
        cutoff = moment - WINDOW_SECONDS
        slot = (bucket, key)
        with self._lock:
            times = self._hits.get(slot)
            if times is None:
                times = deque()
                self._hits[slot] = times
                self._trim()
            else:
                self._hits.move_to_end(slot)
            while times and times[0] <= cutoff:
                times.popleft()
            if len(times) >= limit:
                return max(1, math.ceil(times[0] + WINDOW_SECONDS - moment))
            times.append(moment)
            return None

    def _trim(self) -> None:
        # Called with the lock held, after a new key was added.
        while len(self._hits) > self._max_keys:
            self._hits.popitem(last=False)


limits = RateLimits()


def enforce(bucket: str, key: str, limit: int) -> None:
    """Raise a 429 with Retry-After when `key` is over the limit for `bucket`."""
    if not settings.rate_limit_enabled:
        return
    wait = limits.check(bucket, key, limit)
    if wait is not None:
        raise RateLimitedError(wait)


def _normalize(value: str) -> str | None:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            return str(address.ipv4_mapped)
        # One household or phone gets a whole /64, so rotating inside it gains nothing.
        return str(ipaddress.ip_network(f"{address}/64", strict=False).network_address)
    return str(address)


# Headers Cloudflare sets itself from the connection it accepted. Cloudflare overwrites any
# value a visitor sends, and every Render service sits behind Cloudflare, so these cannot be
# forged by a visitor. Render's own docs and support point at them for the visitor address.
CLIENT_IP_HEADERS = ("cf-connecting-ip", "true-client-ip")


def client_ip(request: Request, hops: int | None = None) -> str:
    """The caller's address, taking only what our own proxies vouch for.

    With 0 trusted `hops` (local runs and tests) every forwarding header is ignored and the
    socket peer is used. Behind Render (hops > 0) the visitor address comes from the header
    Cloudflare sets (`CF-Connecting-IP`, then `True-Client-IP`). Counting entries in
    X-Forwarded-For is only the fallback, because Render's chain length is not something we
    control: every proxy appends the address it saw, so the left side is whatever the visitor
    chose, and counting `hops` entries from the RIGHT lands on a rotating Cloudflare edge
    address as soon as the chain is longer than we guessed.
    """
    count = settings.trusted_proxy_hops if hops is None else hops
    peer = request.client.host if request.client is not None else "unknown"
    if count <= 0:
        return _normalize(peer) or peer
    for name in CLIENT_IP_HEADERS:
        value = request.headers.get(name, "").strip()
        if value and (address := _normalize(value)) is not None:
            return address
    parts = [
        part.strip()
        for line in request.headers.getlist("x-forwarded-for")
        for part in line.split(",")
        if part.strip()
    ]
    if not parts:
        return _normalize(peer) or peer
    # If the chain is shorter than expected (a direct hit on the origin, say), the best
    # information left is its first entry.
    chosen = parts[-count] if len(parts) >= count else parts[0]
    return _normalize(chosen) or _normalize(peer) or peer
