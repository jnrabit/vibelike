"""
intelligence/retrieval.py
=========================
Thompson Sampling + Riemannscher Chaos-Warp + Resonanz-Rückkopplung.
Vollständig vektorisiert (numpy), kein Python-Loop über Dokumente.

Verwendet von: terminal.py
"""

import numpy as np
import time
from collections import defaultdict

from .resonance import ResonanceField


# ─────────────────────────────────────────────────────────────────────────────
# Thompson Sampler
# ─────────────────────────────────────────────────────────────────────────────

class ThompsonSampler:
    """
    Beta(α, β) pro Dokument.
    Neue Docs → Beta(1,1) = uniform → maximale Exploration.
    Nach Feedback → Peak verschiebt sich zur echten Relevanz.
    """
    def __init__(self):
        self.alpha = defaultdict(lambda: 1.0)
        self.beta  = defaultdict(lambda: 1.0)
        self.rng   = np.random.RandomState()

    def batch_sample(self, id_map: list) -> np.ndarray:
        a = np.array([self.alpha[d] for d in id_map], dtype=np.float32)
        b = np.array([self.beta[d]  for d in id_map], dtype=np.float32)
        return self.rng.beta(a, b).astype(np.float32)

    def exploration_scores(self, id_map: list) -> np.ndarray:
        a = np.array([self.alpha[d] for d in id_map], dtype=np.float32)
        b = np.array([self.beta[d]  for d in id_map], dtype=np.float32)
        return (1.0 / (1.0 + (a + b - 2.0) * 0.1)).astype(np.float32)

    def update(self, retrieved: list, relevant: set):
        for did in retrieved:
            if did in relevant:
                self.alpha[did] += 1.0
            else:
                self.beta[did]  += 0.3


# ─────────────────────────────────────────────────────────────────────────────
# Riemannscher Warp
# ─────────────────────────────────────────────────────────────────────────────

class RiemannianWarp:
    """
    Zeitabhängige Metrik: score(q, d, t) = (q⊙w(t)) · (d⊙w(t))
    w(t) wird aus den Lorenz-Koordinaten + Resonanz-Kraft projiziert.
    """
    def __init__(self, embed_dim: int = 384, lorenz_dims: int = 8):
        self.embed_dim   = embed_dim
        self.lorenz_dims = lorenz_dims
        # Johnson-Lindenstrauss Projektion (fixiert, orthogonalisiert)
        rng = np.random.RandomState(1337)
        P   = rng.randn(embed_dim, lorenz_dims).astype(np.float32)
        U, _, _ = np.linalg.svd(P, full_matrices=False)
        self._P              = U.astype(np.float32)
        self._warp           = np.ones(embed_dim, dtype=np.float32)
        self.warp_history: list = []

    def update(self, lorenz_state: dict, resonance_force: np.ndarray = None):
        sv = np.array([
            lorenz_state.get("x1", 0), lorenz_state.get("y1", 0),
            lorenz_state.get("z1", 0), lorenz_state.get("w1", 0),
            lorenz_state.get("x2", 0), lorenz_state.get("y2", 0),
            lorenz_state.get("z2", 0), lorenz_state.get("w2", 0),
        ], dtype=np.float32)[:self.lorenz_dims]

        raw = self._P @ sv
        if resonance_force is not None and len(resonance_force) == self.lorenz_dims:
            raw += self._P @ resonance_force.astype(np.float32) * 0.3

        wn = np.tanh(raw / 20.0).astype(np.float32)
        self._warp = (1.0 + wn * 0.3).astype(np.float32)
        self.warp_history.append(float(-np.sum(
            np.abs(wn) * np.log(np.abs(wn) + 1e-8)
        )))
        if len(self.warp_history) > 100:
            self.warp_history.pop(0)

    def score(self, q: np.ndarray, doc_matrix: np.ndarray) -> np.ndarray:
        qw = q * self._warp
        Dw = doc_matrix * self._warp[np.newaxis, :]
        # Optimiert: einsum + sqrt statt Matrix-Normalisierung
        # Kosinus-Ähnlichkeit: (q·d) / (||q|| * ||d||)
        qw_sq = np.sum(qw**2)
        Dw_sq = np.sum(Dw**2, axis=1)
        dot_products = np.einsum('d,nd->n', qw, Dw)
        return (dot_products / np.sqrt(qw_sq * Dw_sq + 1e-16)).astype(np.float32)

    @property
    def divergence(self) -> float:
        return float(np.std(self._warp))

    @property
    def sample(self) -> list:
        """8 repräsentative Werte aus dem 384D-Vektor für Visualisierung."""
        return self._warp[::48].tolist()


# ─────────────────────────────────────────────────────────────────────────────
# Chaos Retrieval — Hauptklasse
# ─────────────────────────────────────────────────────────────────────────────

class ChaosRetrieval:
    """
    Scoring:
        score(d) = α·warp(d) + β·thompson(d) + γ·resonanz(d) + δ·exploration(d)

    α,β,γ,δ werden durch Hardware-Entropie moduliert:
        hohe Entropie  → mehr Exploration (β,δ hoch)
        niedrige Entropie → mehr Exploitation (α,γ hoch)
    """

    def __init__(self, protocol=None, field: ResonanceField = None,
                 embed_dim: int = 384, lorenz_dims: int = 8):
        self.protocol     = protocol
        self.field        = field
        self.warp         = RiemannianWarp(embed_dim, lorenz_dims)
        self.thompson     = ThompsonSampler()
        # Gewichte (per Slider aus Terminal überschreibbar)
        self.alpha = 0.5
        self.beta  = 0.2
        self.gamma = 0.2
        self.delta = 0.1
        self._last_retrieved: list = []
        self._search_count: int   = 0
        print("⚡ CHAOS RETRIEVAL online")

    def _matrix(self):
        p = self.protocol
        if p and hasattr(p, "_matrix") and p._matrix is not None:
            return p._matrix, p._id_map
        return None, []

    def search(self, query_vec: np.ndarray, top_k: int = 30) -> list:
        self._search_count += 1

        # Adaptive Lorenz-Parameter alle 50 Searches — siehe AUDIT_REPORT.md F001.
        # Counter-Inkrement steht VOR allen frühen Returns, damit das Adaption-
        # Intervall sich an search-Aufrufe (nicht nur erfolgreiche Searches)
        # bindet — Konsistenz mit selfaware.adapt_lag-Regel.
        if self._search_count % 50 == 0:
            self._adapt_lorenz()

        t0 = time.perf_counter()

        doc_matrix, id_map = self._matrix()
        if doc_matrix is None:
            return []
        n = len(id_map)

        # Hardware-State
        lorenz_state, entropy = {}, 0.5
        if self.protocol and self.protocol.active:
            s         = self.protocol.get_hardware_state()
            lorenz_state = s
            entropy   = min(1.0, s.get("entropy", 4.0) / 8.0)

        # Resonanz-Kraft → Warp.
        # 8-D Lorenz-Position konsistent mit RiemannianWarp.update (8 Dims)
        # und ResonanceField default n_lorenz_dims=8 — siehe AUDIT_REPORT.md F004.
        # z2/w2 fehlen im Hardware-State (engine.cpp exportiert nur 6 echte
        # Lorenz-Komponenten + entropy/temperature/cortex_bias) → Default 0.
        r_force = None
        if self.field:
            lp = np.array([
                lorenz_state.get("x1", 0), lorenz_state.get("y1", 0),
                lorenz_state.get("z1", 0), lorenz_state.get("w1", 0),
                lorenz_state.get("x2", 0), lorenz_state.get("y2", 0),
                lorenz_state.get("z2", 0), lorenz_state.get("w2", 0),
            ], dtype=np.float32)
            r_force = self.field.get_lorenz_force(lp)

        self.warp.update(lorenz_state, r_force)

        # Vektorisiertes Scoring
        warp_arr   = self.warp.score(query_vec.astype(np.float32), doc_matrix)
        thomp_arr  = self.thompson.batch_sample(id_map)
        explor_arr = self.thompson.exploration_scores(id_map)

        # Resonanz (nur Top-20 als Anker) — argpartition für O(n) statt O(n log n)
        top20_indices = np.argpartition(warp_arr, -20)[-20:]
        top20_indices = top20_indices[np.argsort(warp_arr[top20_indices])[::-1]]
        top20_ids = [id_map[i] for i in top20_indices]
        res_arr   = np.zeros(n, dtype=np.float32)
        if self.field:
            boosts = self.field.get_resonance_boost(id_map, top20_ids)
            if boosts:
                res_arr = np.array([boosts.get(d, 0.0) for d in id_map], dtype=np.float32)
                rmax = res_arr.max()
                if rmax > 0:
                    res_arr /= rmax

        # Entropie-modulierte Koeffizienten
        exp_mode  = entropy
        expl_mode = 1.0 - entropy
        a = self.alpha * expl_mode + 0.3 * exp_mode
        b = self.beta  * exp_mode  + 0.1 * expl_mode
        g = self.gamma * expl_mode + 0.1 * exp_mode
        d = self.delta * exp_mode  + 0.05 * expl_mode

        scores     = a*warp_arr + b*thomp_arr + g*res_arr + d*explor_arr
        # argpartition für Top-k: O(n) statt O(n log n)
        top_k_indices = np.argpartition(scores, -top_k)[-top_k:]
        top_k_indices = top_k_indices[np.argsort(scores[top_k_indices])[::-1]]

        results, retrieved = [], []
        for idx in top_k_indices:
            did  = id_map[idx]
            dist = max(0.0, (1.0 - float(scores[idx])) * 100.0)
            results.append((did, dist))
            retrieved.append(did)

        if self.field:
            self.field.record_activation(retrieved[:15], query_vec)

        self._last_retrieved = retrieved
        ms = (time.perf_counter() - t0) * 1000
        print(f"   ⚡ {n:,} docs → top {len(results)} | {ms:.1f}ms | "
              f"warp={self.warp.divergence:.4f} | H={entropy:.3f}")
        return results

    def _adapt_lorenz(self):
        """
        Schaltet die Lorenz-Parameter der C++ Engine basierend auf dem
        Resonanzfeld-Zustand. Alle 50 Searches aus search() aufgerufen.

        reason ∈ [0,1] = tracked_pairs / queries (geclippt):
          niedrig → wenig Resonanz aufgebaut → EXPLORE (höheres rho)
          hoch    → dichtes Resonanzfeld     → EXPLOIT (niedrigeres rho)

        rho_target = 28.0 + (reason - 0.5) * 20.0  →  Range [18, 38]
        sigma, beta bleiben vorerst statisch (klassische Lorenz-Werte).
        Die C++-Seite clamped rho zusätzlich auf [RHO_MIN, RHO_MAX].

        Fehler werden geprintet, nicht propagiert — search() darf nicht
        wegen einer Adaption crashen (Konsistenz mit F003-Philosophie).
        """
        if not (self.protocol and self.protocol.active and self.field):
            return
        try:
            fs         = self.field.get_stats()
            n_pairs    = fs.get("tracked_pairs", 0)
            n_queries  = max(fs.get("queries", 1), 1)
            reason     = float(np.clip(n_pairs / n_queries, 0.0, 1.0))
            rho_target = 28.0 + (reason - 0.5) * 20.0
            self.protocol.set_lorenz_params(rho_target, 10.0, 8.0/3.0, reason)
            cycle = self.protocol.get_lorenz_params().get("cycle", 0)
            print(f"   🌀 Lorenz adapt #{cycle}: "
                  f"reason={reason:.3f} → ρ={rho_target:.2f}")
        except Exception as e:
            print(f"   ⚠ Lorenz-Adaption fehlgeschlagen: "
                  f"{type(e).__name__}: {e}")
            return

    def feedback(self, relevant_ids: list):
        self.thompson.update(self._last_retrieved, set(relevant_ids))
        if self.protocol:
            self.protocol.apply_cortex_feedback(False)  # Positives Feedback
        print(f"   📡 Feedback: {len(relevant_ids)} relevante Docs")

    def diagnostics(self) -> dict:
        return {
            "search_count":   self._search_count,
            "warp_divergence": self.warp.divergence,
            "warp_history":   self.warp.warp_history[-50:],
            "warp_sample":    self.warp.sample,
            "thompson": {
                "tracked":        len(self.thompson.alpha),
                "high_confidence": sum(
                    1 for d in self.thompson.alpha
                    if self.thompson.alpha[d] + self.thompson.beta[d] > 5
                )
            }
        }
