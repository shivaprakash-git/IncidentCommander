"""Event correlation: classical Louvain (canonical) vs PennyLane QAOA (comparison only).

Graph: nodes = events; edge weight = shared job (3.0) + shared task (2.0) +
shared session (1.5) + time proximity (up to 1.0, linear decay over the window,
default 10 min). Big windows use a sparse builder (each event links to its next
few neighbours per group) so a 4k-event window stays tractable; the small QAOA
subsample uses the exact dense pairwise weights.

QAOA path (never blocks the pipeline): the graph is subsampled to <= MAX_QUBITS
nodes, turned into a QUBO (minimise cross-cluster weight + a balance penalty so
it cannot collapse into one cluster), rewritten as a ZZ-only Ising Hamiltonian,
and optimised with QAOA on `default.qubit` inside a killable child process with
a wall-clock timeout. It yields a 2-way partition. ARI compares it with Louvain
run on the SAME subsample. Any failure / timeout -> status recorded, Louvain
result unaffected.

CLI:  python -m engine.correlation --test [--incident INC-R01] [--qubits 14] [--timeout 90]
"""
from __future__ import annotations

import argparse
import multiprocessing as mp
import time
from dataclasses import dataclass, field
from itertools import combinations
from typing import Optional

import networkx as nx
import numpy as np
from sklearn.metrics import adjusted_rand_score

from . import db
from .config import DB_PATH

W_JOB, W_TASK, W_SESSION, W_TIME = 3.0, 2.0, 1.5, 1.0
DENSE_LIMIT = 200          # <= this many nodes: exact pairwise weights
GROUP_K = 3                # sparse mode: link each event to the next K in its group
TIME_K = 4
MAX_QUBITS = 16
DEFAULT_QUBITS = 14


# ---------------------------------------------------------------- graph
def pair_weight(a, b, window_s: float) -> float:
    w = 0.0
    if a.job_id and a.job_id == b.job_id:
        w += W_JOB
    if a.task_id and a.task_id == b.task_id:
        w += W_TASK
    if a.session_id and a.session_id == b.session_id:
        w += W_SESSION
    dt = abs((a.timestamp - b.timestamp).total_seconds())
    if dt <= window_s:
        w += W_TIME * (1.0 - dt / window_s)
    return w


def build_graph(events: list, window_min: float = 10.0, dense: Optional[bool] = None) -> nx.Graph:
    window_s = window_min * 60.0
    events = sorted(events, key=lambda e: (e.timestamp, e.line_no))
    G = nx.Graph()
    G.add_nodes_from(e.event_id for e in events)
    if dense is None:
        dense = len(events) <= DENSE_LIMIT
    if dense:
        for a, b in combinations(events, 2):
            w = pair_weight(a, b, window_s)
            if w > 0:
                G.add_edge(a.event_id, b.event_id, weight=w)
        return G

    def add(a, b, w):
        if G.has_edge(a.event_id, b.event_id):
            G[a.event_id][b.event_id]["weight"] += w
        else:
            G.add_edge(a.event_id, b.event_id, weight=w)

    for key, wt in (("job_id", W_JOB), ("task_id", W_TASK), ("session_id", W_SESSION)):
        groups: dict = {}
        for e in events:
            v = getattr(e, key)
            if v:
                groups.setdefault(v, []).append(e)
        for g in groups.values():
            for i, a in enumerate(g):
                for b in g[i + 1: i + 1 + GROUP_K]:
                    add(a, b, wt)
    for i, a in enumerate(events):
        for b in events[i + 1: i + 1 + TIME_K]:
            dt = (b.timestamp - a.timestamp).total_seconds()
            if dt > window_s:
                break
            add(a, b, W_TIME * (1.0 - dt / window_s))
    return G


# ---------------------------------------------------------------- classical
def louvain(G: nx.Graph, seed: int = 0) -> dict:
    """node -> community id. python-louvain if present, else greedy modularity."""
    if G.number_of_edges() == 0:
        return {n: i for i, n in enumerate(G.nodes)}
    try:
        import community as community_louvain
        return community_louvain.best_partition(G, weight="weight", random_state=seed)
    except ImportError:
        comms = nx.community.greedy_modularity_communities(G, weight="weight")
        return {n: i for i, c in enumerate(comms) for n in c}


# ---------------------------------------------------------------- quantum
def _qubo_to_ising(weights: np.ndarray) -> tuple:
    """Cut + balance QUBO as ZZ couplings.

    x_i in {0,1}, z_i = 1-2x_i.  minimise  sum_{i<j} w_ij [x_i != x_j] + lam*(sum x - n/2)^2
    [x_i != x_j] = (1 - z_i z_j)/2 ;  (sum x - n/2)^2 = (sum z)^2 / 4
    => H = const + sum_{i<j} J_ij z_i z_j,   J_ij = (lam - w_ij) / 2.
    """
    n = len(weights)
    iu = np.triu_indices(n, 1)
    nz = weights[iu][weights[iu] > 0]
    lam = 0.5 * float(nz.mean()) if nz.size else 1.0
    J = (lam - weights) / 2.0
    return J, lam


def _qaoa_worker(weights, p, maxiter, seed, q):
    try:
        import pennylane as qml
        from scipy.optimize import minimize

        n = len(weights)
        J, _ = _qubo_to_ising(np.asarray(weights))
        pairs = [(i, j) for i in range(n) for j in range(i + 1, n)]
        H = qml.dot([J[i, j] for i, j in pairs], [qml.PauliZ(i) @ qml.PauliZ(j) for i, j in pairs])
        mixer = qml.qaoa.x_mixer(range(n))
        dev = qml.device("default.qubit", wires=n)

        def layer(g, a):
            qml.qaoa.cost_layer(g, H)
            qml.qaoa.mixer_layer(a, mixer)

        def circ(params):
            for w in range(n):
                qml.Hadamard(wires=w)
            qml.layer(layer, p, params[0], params[1])

        @qml.qnode(dev)
        def cost(params):
            circ(params)
            return qml.expval(H)

        @qml.qnode(dev)
        def probs(params):
            circ(params)
            return qml.probs(wires=range(n))

        t_start = time.perf_counter()
        x0 = np.random.default_rng(seed).uniform(0.1, 0.6, size=2 * p)
        res = minimize(lambda x: float(cost(x.reshape(2, p))), x0, method="COBYLA",
                       options={"maxiter": maxiter})
        pr = np.asarray(probs(res.x.reshape(2, p)))
        best, best_e = None, np.inf
        for idx in np.argsort(pr)[::-1][:64]:            # best-energy among the likeliest bitstrings
            bits = np.array([(int(idx) >> (n - 1 - k)) & 1 for k in range(n)])
            z = 1 - 2 * bits
            e = float(sum(J[i, j] * z[i] * z[j] for i, j in pairs))
            if e < best_e:
                best, best_e = bits, e
        q.put({"ok": True, "labels": best.tolist(), "energy": best_e, "nfev": int(res.nfev),
                 "compute_s": time.perf_counter() - t_start})
    except Exception as exc:                              # noqa: BLE001 - reported, never raised
        q.put({"ok": False, "error": f"{type(exc).__name__}: {exc}"})


def run_qaoa(weights: np.ndarray, p: int = 2, maxiter: int = 80, timeout_s: float = 90.0,
             seed: int = 0) -> dict:
    """Run QAOA in a child process; returns {status, labels?, energy?, runtime_s, reason?}."""
    ctx = mp.get_context("spawn")
    q = ctx.Queue()
    t0 = time.perf_counter()
    proc = ctx.Process(target=_qaoa_worker, args=(weights.tolist(), p, maxiter, seed, q), daemon=True)
    proc.start()
    proc.join(timeout_s)
    if proc.is_alive():
        proc.terminate(); proc.join(5)
        return {"status": "timeout", "reason": f"exceeded {timeout_s:.0f}s", "runtime_s": time.perf_counter() - t0}
    try:
        out = q.get(timeout=2)
    except Exception:                                     # noqa: BLE001
        return {"status": "failed", "reason": "worker exited without result", "runtime_s": time.perf_counter() - t0}
    dt = time.perf_counter() - t0
    if not out["ok"]:
        return {"status": "failed", "reason": out["error"], "runtime_s": dt}
    return {"status": "ok", "labels": out["labels"], "energy": out["energy"], "nfev": out["nfev"],
            "compute_s": out["compute_s"], "runtime_s": dt}


# ---------------------------------------------------------------- orchestration
@dataclass
class CorrelationResult:
    n_events: int
    n_edges: int
    louvain: dict                      # event_id -> cluster id (canonical, full window)
    louvain_runtime_s: float
    qaoa: dict = field(default_factory=dict)          # status, labels(event_id->0/1), runtime_s, n_qubits, ...
    subsample_louvain: dict = field(default_factory=dict)
    ari: Optional[float] = None
    notes: list = field(default_factory=list)

    @property
    def n_clusters(self) -> int:
        return len(set(self.louvain.values()))

    def to_dict(self) -> dict:
        return {"n_events": self.n_events, "n_edges": self.n_edges, "n_clusters": self.n_clusters,
                "louvain": self.louvain, "louvain_runtime_s": self.louvain_runtime_s,
                "qaoa": self.qaoa, "subsample_louvain": self.subsample_louvain,
                "ari": self.ari, "notes": self.notes}

    def cluster_members(self, event_id: str) -> list:
        cid = self.louvain.get(event_id)
        return [e for e, c in self.louvain.items() if c == cid]


def _subsample(events: list, labels: dict, cap: int, focus_id: Optional[str]) -> list:
    """<= cap events, stratified by Louvain community, evenly spread in time, focus event kept."""
    by_c: dict = {}
    for e in sorted(events, key=lambda e: (e.timestamp, e.line_no)):
        by_c.setdefault(labels[e.event_id], []).append(e)
    comms = sorted(by_c.values(), key=len, reverse=True)
    total = len(events)
    quota = [max(1, round(cap * len(c) / total)) for c in comms]
    while sum(quota) > cap:                               # trim from the largest quotas
        quota[quota.index(max(quota))] -= 1
    chosen = []
    for c, k in zip(comms, quota):
        if k <= 0:
            continue
        idx = np.linspace(0, len(c) - 1, min(k, len(c))).round().astype(int)
        chosen += [c[i] for i in sorted(set(idx))]
    if focus_id and all(e.event_id != focus_id for e in chosen):
        focus = next((e for e in events if e.event_id == focus_id), None)
        if focus:
            chosen = chosen[:-1] + [focus] if len(chosen) >= cap else chosen + [focus]
    return chosen[:cap]


def correlate(events: list, window_min: float = 10.0, max_qubits: int = DEFAULT_QUBITS,
              qaoa_timeout_s: float = 90.0, focus_event_id: Optional[str] = None,
              run_quantum: bool = True, seed: int = 0) -> CorrelationResult:
    max_qubits = min(max_qubits, MAX_QUBITS)
    G = build_graph(events, window_min)
    t0 = time.perf_counter()
    lab = louvain(G, seed)
    lt = time.perf_counter() - t0
    res = CorrelationResult(len(events), G.number_of_edges(), lab, lt)
    if len(events) < 4:
        res.qaoa = {"status": "skipped", "reason": "fewer than 4 events"}
        return res
    if not run_quantum:
        res.qaoa = {"status": "skipped", "reason": "disabled by caller"}
        return res

    sub = events
    if len(events) > max_qubits:
        sub = _subsample(events, lab, max_qubits, focus_event_id)
        res.notes.append(f"QAOA capped at {max_qubits} qubits: subsampled {len(sub)} of {len(events)} events")
    sub = sorted(sub, key=lambda e: (e.timestamp, e.line_no))
    ids = [e.event_id for e in sub]
    Gs = build_graph(sub, window_min, dense=True)
    res.subsample_louvain = louvain(Gs, seed)
    n = len(sub)
    W = np.zeros((n, n))
    for i, j in combinations(range(n), 2):
        W[i, j] = W[j, i] = pair_weight(sub[i], sub[j], window_min * 60.0)
    out = run_qaoa(W, timeout_s=qaoa_timeout_s, seed=seed)
    out["n_qubits"] = n
    out["subsample_ids"] = ids
    if out["status"] == "ok":
        out["labels"] = dict(zip(ids, out["labels"]))
        res.ari = float(adjusted_rand_score([res.subsample_louvain[i] for i in ids],
                                            [out["labels"][i] for i in ids]))
    else:
        res.notes.append(f"QAOA {out['status']}: {out.get('reason')} - Louvain result used alone")
    res.qaoa = out
    return res


# ---------------------------------------------------------------- CLI
def _load_incident(conn, incident_id: Optional[str]):
    q = "SELECT * FROM incidents " + ("WHERE incident_id=?" if incident_id else "WHERE demo=1 ORDER BY trigger_ts") + " LIMIT 1"
    row = conn.execute(q, (incident_id,) if incident_id else ()).fetchone()
    if not row:
        raise SystemExit("no incident in DB - run: python -m engine.pipeline ingest")
    from datetime import datetime
    ev = db.load_events(conn, datetime.fromisoformat(row["window_start"]), datetime.fromisoformat(row["window_end"]))
    return row, ev


def print_result(r: CorrelationResult, focus: Optional[str] = None) -> None:
    sizes = sorted((sum(1 for c in r.louvain.values() if c == k) for k in set(r.louvain.values())), reverse=True)
    print(f"events={r.n_events} edges={r.n_edges}")
    print(f"LOUVAIN  clusters={r.n_clusters} sizes(top10)={sizes[:10]} runtime={r.louvain_runtime_s*1000:.1f} ms")
    if focus:
        print(f"         cluster of trigger {focus}: {len(r.cluster_members(focus))} events")
    q = r.qaoa
    print(f"QAOA     status={q.get('status')} qubits={q.get('n_qubits')} runtime={q.get('runtime_s', 0):.2f} s "
          f"(optimise+sample {q.get('compute_s', 0):.2f} s; rest is process spawn + PennyLane import) "
          f"{q.get('reason', '')}")
    if q.get("status") == "ok":
        ids = q["subsample_ids"]
        print("         event_id      louvain(sub)  qaoa")
        for i in ids:
            print(f"         {i:<13} {r.subsample_louvain[i]:>6}        {q['labels'][i]}")
        print(f"ARI(louvain vs qaoa, same {len(ids)}-node subsample) = {r.ari:.3f}")
    for n in r.notes:
        print("note:", n)


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="Louvain vs QAOA correlation on an incident window")
    p.add_argument("--test", action="store_true", help="run on a demo incident from events.db and print metrics")
    p.add_argument("--incident")
    p.add_argument("--db", default=str(DB_PATH))
    p.add_argument("--qubits", type=int, default=DEFAULT_QUBITS)
    p.add_argument("--timeout", type=float, default=90.0)
    a = p.parse_args(argv)
    conn = db.connect(a.db)
    row, ev = _load_incident(conn, a.incident)
    print(f"incident {row['incident_id']} [{row['source']}] {row['type']}  window "
          f"{row['window_start']} -> {row['window_end']}  ({len(ev)} events)")
    r = correlate(ev, max_qubits=a.qubits, qaoa_timeout_s=a.timeout, focus_event_id=row["trigger_event_id"])
    print_result(r, row["trigger_event_id"])


if __name__ == "__main__":
    main()
