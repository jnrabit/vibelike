"""
intelligence/resonance.py
=========================
Emergente Ko-Aktivierungsmatrix als funktionale Kraft.

Muster die durch wiederholtes gemeinsames Retrieval entstehen,
erzeugen Gravitationszentren im Lorenz-Phasenraum und verbiegen
damit zukünftige Suchanfragen ohne explizite Programmierung.

Verwendet von: intelligence/retrieval.py, terminal.py
"""

import numpy as np
import pickle
import os
import time
import shutil
from collections import defaultdict

from framework.quelibrium.core.paths import CODE_FIELD_FILE as FIELD_FILE


class ResonanceField:
    def __init__(self, n_lorenz_dims: int = 8, decay: float = 0.995, protocol=None):
        self.protocol = protocol
        self.n_lorenz_dims   = n_lorenz_dims
        self.decay           = decay
        self.R               = defaultdict(lambda: defaultdict(float))
        self.doc_positions   = {}
        self.gravity_centers = []
        self.emergent_clusters: list = []
        self.query_count         = 0
        self.last_pattern_update = 0
        self._projection = None
        self._load()

    # ── Dokument-Registration ─────────────────────────────────────────────────

    def register_documents(self, doc_embeddings: dict):
        embed_dim = next(iter(doc_embeddings.values())).shape[0]
        # Re-Projection bei: keine Projektion vorhanden, embed-Dim-Mismatch
        # ODER Lorenz-Dim-Mismatch (z.B. nach 3D→8D-Migration aus _load).
        # Siehe AUDIT_REPORT.md F004.
        if (self._projection is None
                or self._projection.shape[1] != embed_dim
                or self._projection.shape[0] != self.n_lorenz_dims):
            rng = np.random.RandomState(42)
            P   = rng.randn(self.n_lorenz_dims, embed_dim).astype(np.float32)
            norms = np.linalg.norm(P, axis=1, keepdims=True)
            self._projection = P / norms

        new = 0
        for doc_id, vec in doc_embeddings.items():
            if doc_id not in self.doc_positions:
                pos = self._projection @ vec.astype(np.float32)
                pos = pos / (np.linalg.norm(pos) + 1e-8) * 20.0
                self.doc_positions[doc_id] = pos
                new += 1
        if new:
            print(f"   🗺️  Resonanzfeld: {new} neue Docs kartiert ({len(self.doc_positions):,} gesamt)")

    # ── Ko-Aktivierung aufzeichnen ────────────────────────────────────────────

    def record_activation(self, retrieved_ids: list, query_vec: np.ndarray = None):
        self.query_count += 1
        if self.query_count % 10 == 0:
            self._decay()

        n = len(retrieved_ids)
        for i in range(n):
            for j in range(i + 1, n):
                ia, ib = retrieved_ids[i], retrieved_ids[j]
                pos_bonus = 1.0
                if ia in self.doc_positions and ib in self.doc_positions:
                    d = np.linalg.norm(self.doc_positions[ia] - self.doc_positions[ib])
                    pos_bonus = 1.0 / (1.0 + d * 0.1)
                boost = (1.0/(i+1)) * (1.0/(j+1)) * pos_bonus
                self.R[ia][ib] += boost
                self.R[ib][ia] += boost

        if self.query_count - self.last_pattern_update >= 50:
            self._detect_clusters()
            self._rebuild_gravity()
            self.last_pattern_update = self.query_count
            self._save()

    # ── Resonanz-Boost für Kandidaten ─────────────────────────────────────────

    def get_resonance_boost(self, candidate_ids: list, anchor_ids: list) -> dict:
        # Optimiert: iteriert über sparse R[aid] Einträge statt über alle candidates
        boosts = defaultdict(float)
        id_set = set(candidate_ids)
        for aid in anchor_ids:
            if aid in self.R:
                for cid, val in self.R[aid].items():
                    if cid in id_set:
                        boosts[cid] += val
        return dict(boosts)

    # ── Lorenz-Gravitationskraft ──────────────────────────────────────────────

    def get_lorenz_force(self, lorenz_pos: np.ndarray) -> np.ndarray:
        if not self.gravity_centers:
            return np.zeros(self.n_lorenz_dims)
        force = np.zeros(self.n_lorenz_dims)
        for center, strength, _ in self.gravity_centers:
            delta = center - lorenz_pos
            dist  = np.linalg.norm(delta) + 1e-8
            force += (delta / dist) * (strength / (dist**1.5 + 2.0))
        norm = np.linalg.norm(force)
        if norm > 2.0:
            force = force / norm * 2.0
        return force

    # ── Cluster-Erkennung (Flood-Fill) ────────────────────────────────────────

    def _detect_clusters(self):
        threshold = self._adaptive_threshold()
        adjacency = defaultdict(set)
        for ia, neighbors in self.R.items():
            for ib, w in neighbors.items():
                if w > threshold:
                    adjacency[ia].add(ib)
                    adjacency[ib].add(ia)

        visited, clusters = set(), []
        for start in adjacency:
            if start in visited:
                continue
            cluster, queue = [], [start]
            while queue:
                node = queue.pop(0)
                if node in visited:
                    continue
                visited.add(node)
                cluster.append(node)
                queue.extend(adjacency[node] - visited)
            if len(cluster) >= 3:
                clusters.append(cluster)

        self.emergent_clusters = clusters
        if clusters:
            print(f"\n   🔮 {len(clusters)} Cluster erkannt "
                  f"(Größen: {sorted([len(c) for c in clusters], reverse=True)[:5]})")

    def _adaptive_threshold(self) -> float:
        weights = [w for nbrs in self.R.values() for w in nbrs.values()]
        return float(np.percentile(weights, 85)) if weights else 0.1

    def _rebuild_gravity(self):
        self.gravity_centers = []
        for cluster in self.emergent_clusters:
            positions = [self.doc_positions[d] for d in cluster if d in self.doc_positions]
            if not positions:
                continue
            center  = np.mean(positions, axis=0)
            weights = [self.R[i][j] for i in cluster for j in cluster
                       if i != j and j in self.R.get(i, {})]
            strength = np.mean(weights) * np.log1p(len(cluster)) if weights else 0.0
            self.gravity_centers.append((center, float(strength), cluster))
        print(f"   🌌 {len(self.gravity_centers)} Gravitationszentren aktiv")

    def _decay(self):
        for ia in list(self.R):
            for ib in list(self.R[ia]):
                self.R[ia][ib] *= self.decay
                if self.R[ia][ib] < 0.001:
                    del self.R[ia][ib]
            if not self.R[ia]:
                del self.R[ia]

    # ── Export für Visualisierung ─────────────────────────────────────────────

    def export_graph(self) -> dict:
        threshold = self._adaptive_threshold()
        nodes, edges, seen = [], [], set()
        for ia, nbrs in self.R.items():
            for ib, w in nbrs.items():
                if w > threshold and ia < ib:
                    edges.append({"source": str(ia), "target": str(ib), "weight": float(w)})
                    seen.update([ia, ib])

        for nid in seen:
            pos = self.doc_positions.get(nid, np.zeros(self.n_lorenz_dims))
            cluster_id = next((ci for ci, c in enumerate(self.emergent_clusters) if nid in c), -1)
            nodes.append({
                "id": str(nid),
                "x": float(pos[0]), "y": float(pos[1]),
                "z": float(pos[2]) if len(pos) > 2 else 0.0,
                "cluster":  cluster_id,
                "strength": float(sum(self.R[nid].values()))
            })

        return {
            "nodes": nodes, "edges": edges,
            "clusters": len(self.emergent_clusters),
            "gravity_centers": [
                {"x": float(c[0][0]), "y": float(c[0][1]),
                 "z": float(c[0][2]) if len(c[0]) > 2 else 0.0,
                 "strength": float(c[1]), "size": len(c[2])}
                for c in self.gravity_centers
            ]
        }

    def get_stats(self) -> dict:
        return {
            "queries":          self.query_count,
            "tracked_pairs":    sum(len(v) for v in self.R.values()) // 2,
            "emergent_clusters": len(self.emergent_clusters),
            "gravity_centers":  len(self.gravity_centers),
            "cluster_sizes":    sorted([len(c) for c in self.emergent_clusters], reverse=True)[:10]
        }

    # ── Persistenz ────────────────────────────────────────────────────────────

    def _save(self):
        state = {
            "R":               {k: dict(v) for k, v in self.R.items()},
            "doc_positions":   self.doc_positions,
            "gravity_centers": self.gravity_centers,
            "emergent_clusters": self.emergent_clusters,
            "query_count":     self.query_count,
            "last_pattern_update": self.last_pattern_update,
            "_projection":     self._projection,
        }
        with open(FIELD_FILE, "wb") as f:
            pickle.dump(state, f)

    def _load(self):
        if not os.path.exists(FIELD_FILE):
            return
        try:
            with open(FIELD_FILE, "rb") as f:
                s = pickle.load(f)
            self.R = defaultdict(lambda: defaultdict(float))
            for k, v in s.get("R", {}).items():
                self.R[k] = defaultdict(float, v)
            self.doc_positions       = s.get("doc_positions", {})
            self.gravity_centers     = s.get("gravity_centers", [])
            self.emergent_clusters   = s.get("emergent_clusters", [])
            self.query_count         = s.get("query_count", 0)
            self.last_pattern_update = s.get("last_pattern_update", 0)
            self._projection         = s.get("_projection")

            # Schema-Drift-Detection (Lorenz-Dim).
            # Migration 3D→8D (oder umgekehrt): Ko-Aktivierungen R sind
            # dimension-agnostisch und bleiben erhalten — die Geometrie
            # (_projection, doc_positions, gravity_centers, emergent_clusters)
            # wird verworfen und beim nächsten register_documents() in der
            # neuen Dimension neu aufgebaut. Siehe AUDIT_REPORT.md F004.
            if (self._projection is not None
                    and self._projection.shape[0] != self.n_lorenz_dims):
                old_dim = self._projection.shape[0]
                new_dim = self.n_lorenz_dims
                n_pairs = sum(len(v) for v in self.R.values()) // 2

                # Defensive Backup vor Schema-Wechsel (F015-Philosophie).
                ts = int(time.time())
                backup_path = f"{FIELD_FILE}.broken-{ts}"
                try:
                    shutil.copy(FIELD_FILE, backup_path)
                except OSError as bu_err:
                    print(f"   ⚠ Backup nach {backup_path} fehlgeschlagen: {bu_err}")

                # Geometrie verwerfen — explizit, nicht als Nebeneffekt:
                self._projection       = None  # Re-Projection beim nächsten register_documents
                self.doc_positions     = {}    # alte n-D-Positionen sind in m-D ungültig
                self.gravity_centers   = []    # waren mit alten Positionen berechnet
                self.emergent_clusters = []    # Cluster waren in alter Geometrie verankert

                print(f"   ⚠ resonance_field.pkl: {old_dim}D→{new_dim}D Migration — "
                      f"_projection/doc_positions/gravity_centers verworfen, "
                      f"R (n_pairs={n_pairs}) und query_count={self.query_count} behalten. "
                      f"Backup: {backup_path}")

                # Migrierten Stand sofort persistieren — sonst würde jeder
                # Restart erneut migrieren und ein weiteres Backup erzeugen.
                self._save()
            else:
                print(f"   📡 Resonanzfeld: {self.query_count} Queries, "
                      f"{len(self.emergent_clusters)} Cluster")
        except Exception as e:
            print(f"   ⚠️  Resonanzfeld reset: {e}")
