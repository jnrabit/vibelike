"""
core/protocol.py
================
Brücke zur C++ Engine (libquelibrium.so) für Code-Vault.
Verantwortlich für:
  - Hardware-State (Lorenz-Koordinaten, Entropie, Temperatur)
  - Vektor-Cache & Dokumenten-Matrix
  - C++ Beschleunigung

Verwendet von: intelligence/retrieval.py
"""

import ctypes
import os
import numpy as np
import pickle
import time
import hashlib

from .vault import Vault
from .paths import CODE_VAULT_FILE, CODE_CACHE_FILE, LIB_FILE as LIB_PATH

# Fallback-State wenn Engine offline
_SHADOW_STATE = {
    "x1": 0.0, "y1": 0.0, "z1": 0.0, "w1": 0.0,
    "entropy": 0.0, "temperature": 45.0,
    "x2": 0.0, "y2": 0.0, "cortex_bias": 0.5
}


class Protocol:
    """Hardware-Protokoll + Dokument-Matrix für Code-Vault."""

    def __init__(self, buffer_mb: int = 64, vault_file: str = None, cache_file: str = None):
        """
        Protocol-Instance für Code-Vault.
        """
        # Pfade — Override-fähig für Code-Vault
        self._vault_file = vault_file or CODE_VAULT_FILE
        self._cache_file = cache_file or CODE_CACHE_FILE

        self.lib    = None
        self.ctx    = None
        self.active = False
        self._doc_cache: dict = {}
        self._id_map:   list  = []
        self._matrix:   np.ndarray | None = None

        print(f"💎 QUELIBRIUM PROTOCOL [CODE] initializing...")

        # 1. C++ Engine laden
        if os.path.exists(LIB_PATH):
            try:
                lib = ctypes.CDLL(LIB_PATH)
                self._bind_signatures(lib)
                ctx = lib.init_quelibrium(buffer_mb)
                if ctx:
                    self.lib    = lib
                    self.ctx    = ctx
                    self.active = True
                    print("   ✅ Engine ONLINE (8D-Chaos | Cortex | Thermal)")
            except Exception as e:
                print(f"   ❌ Engine error: {e}")
        else:
            print(f"   ⚠️  libquelibrium.so not found at {LIB_PATH} — Shadow Mode")

        # 2. Vektor-Cache
        if os.path.exists(self._cache_file):
            try:
                with open(self._cache_file, "rb") as f:
                    self._doc_cache = pickle.load(f)
                self._rebuild_matrix()
                print(f"   📦 Cache: {len(self._doc_cache):,} vectors")
            except Exception as e:
                print(f"   ⚠️  Cache error: {e}")

        # 3. Vault
        self.vault   = Vault(self._vault_file)
        self.archive = []
        try:
            self.archive = self.vault.load()
            print(f"   🔓 Vault: {len(self.archive):,} documents")
        except Exception as e:
            print(f"   ⚠️  Vault empty: {e}")

    # ── C-Signaturen ──────────────────────────────────────────────────────────

    def _bind_signatures(self, lib):
        c_vp  = ctypes.c_void_p
        c_int = ctypes.c_int
        c_f   = ctypes.c_float
        c_d   = ctypes.c_double
        c_uint64 = ctypes.c_uint64
        pf    = ctypes.POINTER(ctypes.c_float)
        pi    = ctypes.POINTER(ctypes.c_int)
        p_uc  = ctypes.POINTER(ctypes.c_ubyte)

        lib.init_quelibrium.argtypes  = [c_int];  lib.init_quelibrium.restype = c_vp
        lib.pulse_system.argtypes     = [c_vp, c_f]
        lib.get_system_state.argtypes = [c_vp, pf]
        lib.apply_cortex_feedback.argtypes = [c_vp, c_int]
        lib.get_cortex_bias.argtypes       = [c_vp, c_int]; lib.get_cortex_bias.restype = c_f
        lib.spectral_block_search.argtypes = [
            c_vp, pf, pf, c_int, c_int, pi, pf, c_f
        ]
        lib.set_lorenz_params.argtypes = [c_vp, c_d, c_d, c_d, c_d]
        lib.set_lorenz_params.restype  = None
        lib.free_quelibrium.argtypes = [c_vp]
        lib.get_fold_state.argtypes = [c_vp]; lib.get_fold_state.restype = c_uint64
        lib.get_current_entropy.argtypes = [c_vp]; lib.get_current_entropy.restype = c_f
        lib.get_lorenz_params.argtypes = [c_vp, ctypes.POINTER(ctypes.c_double)]
        lib.get_lorenz_params.restype = None
        lib.get_lorenz_state_bytes.argtypes = [c_vp, p_uc, c_int]; lib.get_lorenz_state_bytes.restype = None

    # ── Interne Helpers ───────────────────────────────────────────────────────

    def _safe_id(self, raw_id) -> int:
        if isinstance(raw_id, int):
            return abs(raw_id) & 0x7FFFFFFFFFFFFFFF
        return int(hashlib.sha256(str(raw_id).encode()).hexdigest()[:16], 16) & 0x7FFFFFFFFFFFFFFF

    def _rebuild_matrix(self):
        if not self._doc_cache:
            return
        self._id_map = list(self._doc_cache.keys())
        self._matrix = np.stack(
            [self._doc_cache[i] for i in self._id_map]
        ).astype(np.float32)

    # ── Hardware-State ────────────────────────────────────────────────────────

    def get_hardware_state(self) -> dict:
        if not self.active:
            return _SHADOW_STATE.copy()
        data = (ctypes.c_float * 9)()
        self.lib.get_system_state(self.ctx, data)
        return {
            "x1": float(data[0]), "y1": float(data[1]),
            "z1": float(data[2]), "w1": float(data[3]),
            "entropy":      float(data[4]),
            "temperature":  float(data[5]),
            "x2": float(data[6]), "y2": float(data[7]),
            "cortex_bias":  float(data[8]),
        }

    # ── 4-Phasen Validierung ─────────────────────────────────────────────────

    def validate(self, semantic_density: float) -> dict:
        if not self.active:
            return {
                "valid": False, "gap": 1.0,
                "omega": 0.0, "delta_v": 0.0,
                "phases": {}, "state": _SHADOW_STATE.copy()
            }

        s0 = self.get_hardware_state()
        kaltstart = s0["entropy"] == 0.0

        self.lib.pulse_system(self.ctx, ctypes.c_float(semantic_density * 0.3))
        s1 = self.get_hardware_state()
        self.lib.pulse_system(self.ctx, ctypes.c_float(semantic_density * 5.0))
        s2 = self.get_hardware_state()
        time.sleep(0.05)
        self.lib.pulse_system(self.ctx, ctypes.c_float(0.01))
        s3 = self.get_hardware_state()

        if kaltstart:
            return {
                "valid": False, "gap": 1.0,
                "omega": 0.0, "delta_v": 0.0,
                "phases": {"T0_Pre": s0, "T1_Enc": s1, "T2_Peak": s2, "T3_Post": s3},
                "state": s2
            }

        delta_v  = min(1.0, abs(s2["entropy"] - s0["entropy"]) / 2.0)
        gap      = max(0.001, semantic_density * (1.0 - delta_v))
        omega    = min(1.0, s2["entropy"] / 8.0)
        valid    = gap < 0.97

        self.apply_cortex_feedback(not valid)

        return {
            "valid":   valid,
            "gap":     float(gap),
            "omega":   float(omega),
            "delta_v": float(delta_v),
            "state":   s2,
            "phases":  {"T0_Pre": s0, "T1_Enc": s1, "T2_Peak": s2, "T3_Post": s3}
        }

    # ── Cortex ───────────────────────────────────────────────────────────────

    def apply_cortex_feedback(self, error: bool):
        if self.active:
            self.lib.apply_cortex_feedback(self.ctx, int(error))

    def get_cortex_bias(self, doc_index: int) -> float:
        if not self.active:
            return 0.5
        return float(self.lib.get_cortex_bias(self.ctx, doc_index))

    # ── Adaptive Lorenz-Parameter ────────────────────────────────────────────

    def set_lorenz_params(self, rho: float, sigma: float, beta: float, reason: float):
        if not self.active:
            return
        self.lib.set_lorenz_params(
            self.ctx,
            ctypes.c_double(rho),
            ctypes.c_double(sigma),
            ctypes.c_double(beta),
            ctypes.c_double(reason),
        )

    def get_lorenz_params(self) -> dict:
        if not self.active:
            return {
                "rho": 28.0, "sigma": 10.0, "beta": 8.0/3.0,
                "reason": 0.5, "cycle": 0, "rho_delta": 0.0
            }
        out_array = (ctypes.c_double * 6)()
        self.lib.get_lorenz_params(self.ctx, out_array)
        return {
            "rho":       out_array[0],
            "sigma":     out_array[1],
            "beta":      out_array[2],
            "reason":    out_array[3],
            "cycle":     int(out_array[4]),
            "rho_delta": out_array[5]
        }

    # ── Suche (C++ beschleunigt) ────────────────────────────────────────────

    def raw_search(self, query_vec: np.ndarray, density: float = 1.0) -> list:
        """Direkter C++ Search."""
        if not self.active or self._matrix is None:
            return []

        q_ptr = query_vec.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
        m_ptr = self._matrix.ctypes.data_as(ctypes.POINTER(ctypes.c_float))

        idx_out  = np.zeros(30, dtype=np.int32)
        dist_out = np.zeros(30, dtype=np.float32)

        self.lib.spectral_block_search(
            self.ctx, q_ptr, m_ptr,
            len(self._id_map), 384,
            idx_out.ctypes.data_as(ctypes.POINTER(ctypes.c_int)),
            dist_out.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
            ctypes.c_float(density)
        )

        results = []
        for i in range(30):
            idx = idx_out[i]
            if 0 <= idx < len(self._id_map):
                results.append((self._id_map[idx], float(dist_out[i])))
        return results

    # ── Dokument-Zugriff ─────────────────────────────────────────────────────

    def get_documents(self) -> list:
        return self.archive

    def reload_vault(self) -> int:
        self.archive = self.vault.load()
        return len(self.archive)

    def close(self):
        if self.active and self.lib:
            self.lib.free_quelibrium(self.ctx)
            self.active = False
