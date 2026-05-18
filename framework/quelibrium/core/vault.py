"""
core/vault.py
=============
Verschlüsselter Datenspeicher (LZMA + Chaos-XOR).

Verwendet von: protocol.py, harvester/collectors.py, sync.py
"""

import os
import json
import lzma
import hashlib
import numpy as np
from numba import jit, prange

COMPRESSION_FILTER = [{"id": lzma.FILTER_LZMA2, "preset": 9 | lzma.PRESET_EXTREME}]


@jit(nopython=True, fastmath=True, parallel=True)
def _chaos_cipher(data: np.ndarray, seed: float) -> np.ndarray:
    """JIT-kompilierter XOR-Cipher via logistische Map."""
    n   = len(data)
    out = np.zeros(n, dtype=np.uint8)
    r   = 3.999
    for i in prange(n):
        x = ((i * 0.0000001) + seed) % 1.0
        if x <= 0:
            x = 0.12345
        x = r * x * (1.0 - x)
        x = r * x * (1.0 - x)
        x = r * x * (1.0 - x)
        out[i] = data[i] ^ int(x * 255)
    return out


def _password_seed(password: str) -> float:
    h = hashlib.sha256(password.encode()).hexdigest()
    return (int(h[:12], 16) / 1e15) % 1.0


class Vault:
    """
    Speichert und lädt beliebige JSON-serialisierbare Daten
    in einer verschlüsselten, komprimierten Binärdatei.
    """

    DEFAULT_KEY = "MONOLITH_V7_ROOT_KEY"

    def __init__(self, filepath: str, password: str = DEFAULT_KEY):
        self.filepath = filepath
        self.seed     = _password_seed(password)

    # ── Schreiben ──────────────────────────────────────────────────────────────

    def save(self, data: list) -> None:
        raw       = json.dumps(data, separators=(',', ':')).encode()
        compressed = lzma.compress(raw, format=lzma.FORMAT_RAW,
                                   filters=COMPRESSION_FILTER)
        arr       = np.frombuffer(compressed, dtype=np.uint8)
        encrypted = _chaos_cipher(arr, self.seed)
        with open(self.filepath, "wb") as f:
            f.write(encrypted.tobytes())

    # ── Lesen ──────────────────────────────────────────────────────────────────

    def load(self) -> list:
        if not os.path.exists(self.filepath):
            return []
        try:
            with open(self.filepath, "rb") as f:
                raw = f.read()
            if not raw:
                return []
            arr       = np.frombuffer(raw, dtype=np.uint8)
            decrypted = _chaos_cipher(arr, self.seed)
            decompressed = lzma.decompress(decrypted.tobytes(),
                                           format=lzma.FORMAT_RAW,
                                           filters=COMPRESSION_FILTER)
            return json.loads(decompressed.decode())
        except Exception as e:
            print(f"❌ Vault load error ({self.filepath}): {e}")
            return []


# Rückwärts-Kompatibilität: alter Name funktioniert weiterhin
MonolithVault = Vault
