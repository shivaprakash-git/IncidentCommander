import itertools
from datetime import datetime, timedelta

import numpy as np

from engine.correlation import (_qubo_to_ising, build_graph, correlate, louvain, run_qaoa)
from engine.models import Event


def ev(i, sec, job, task=None, session=None):
    return Event(event_id=f"E{i}", timestamp=datetime(2023, 8, 10, 12, 0, 0) + timedelta(seconds=sec),
                 job_id=job, task_id=task or job, session_id=session, major_type="1", minor_type="5",
                 raw_type_keyword="OPEN", line_no=i)


def two_jobs(n=6):
    a = [ev(i, i, "100", session="s1") for i in range(n)]
    b = [ev(100 + i, 3000 + i, "200", session="s2") for i in range(n)]   # 50 min later, other job
    return a + b


def test_edge_weights_combine_job_task_session_time():
    G = build_graph([ev(1, 0, "100", session="s"), ev(2, 60, "100", session="s")], window_min=10)
    w = G["E1"]["E2"]["weight"]
    assert abs(w - (3.0 + 2.0 + 1.5 + 0.9)) < 1e-9          # 60s into a 600s window -> 0.9


def test_far_apart_unrelated_events_have_no_edge():
    G = build_graph([ev(1, 0, "1"), ev(2, 5000, "2")])
    assert G.number_of_edges() == 0


def test_louvain_separates_the_two_jobs():
    lab = louvain(build_graph(two_jobs()))
    assert len({lab[f"E{i}"] for i in range(6)}) == 1
    assert lab["E0"] != lab["E100"]


def test_ising_minimum_matches_bruteforce_qubo():
    rng = np.random.default_rng(1)
    n = 6
    W = rng.random((n, n)); W = np.triu(W, 1); W = W + W.T
    J, lam = _qubo_to_ising(W)

    def qubo(x):
        cut = sum(W[i, j] for i in range(n) for j in range(i + 1, n) if x[i] != x[j])
        return cut + lam * (sum(x) - n / 2) ** 2

    def ising(x):
        z = [1 - 2 * b for b in x]
        return sum(J[i, j] * z[i] * z[j] for i in range(n) for j in range(i + 1, n))

    xs = list(itertools.product([0, 1], repeat=n))
    off = qubo(xs[0]) - ising(xs[0])
    assert all(abs(qubo(x) - ising(x) - off) < 1e-9 for x in xs)     # equal up to a constant


def test_qaoa_timeout_never_raises():
    out = run_qaoa(np.ones((4, 4)) - np.eye(4), timeout_s=0.01)
    assert out["status"] == "timeout"


def test_correlate_small_window_with_qaoa_and_ari():
    r = correlate(two_jobs(4), max_qubits=8, qaoa_timeout_s=120)
    assert r.qaoa["status"] == "ok"
    assert r.ari is not None and -1.0 <= r.ari <= 1.0
    assert r.qaoa["n_qubits"] == 8


def test_correlate_without_quantum_and_qubit_cap():
    r = correlate(two_jobs(30), run_quantum=False)
    assert r.qaoa["status"] == "skipped" and r.n_clusters >= 2
