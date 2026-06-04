"""Minimal ULID shim — generates a time-sortable random ID."""
import time, os, base64

_B32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

def _encode(n, length):
    result = []
    for _ in range(length):
        result.append(_B32[n & 0x1F])
        n >>= 5
    return ''.join(reversed(result))

class ULID:
    def __init__(self):
        ts = int(time.time() * 1000)
        rand = int.from_bytes(os.urandom(10), 'big')
        self._str = _encode(ts, 10) + _encode(rand, 16)

    def __str__(self):
        return self._str
