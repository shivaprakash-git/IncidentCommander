import numpy as np

from engine import db, qsvm


def test_select_and_scale_range_and_topk():
    rng = np.random.default_rng(0)
    X = rng.integers(0, 50, size=(20, 8)).astype(float)
    X[:, 3] *= 100                                              # highest variance column
    Xs, feats = qsvm.select_and_scale(X, [f"f{i}" for i in range(8)], k=5)
    assert Xs.shape == (20, 5) and feats[0] == "f3"
    assert Xs.min() >= 0 and Xs.max() <= np.pi + 1e-9


def test_quantum_kernel_is_symmetric_unit_diagonal_in_unit_interval():
    Xs = np.random.default_rng(1).uniform(0, np.pi, size=(6, 3))
    K, _ = qsvm.quantum_kernel(Xs)
    assert np.allclose(K, K.T) and np.allclose(np.diag(K), 1.0) and K.min() >= -1e-9 and K.max() <= 1 + 1e-9
    # product-state kernel: prod cos^2((x-y)/2)
    expect = np.prod(np.cos((Xs[0] - Xs[1]) / 2) ** 2)
    assert abs(K[0, 1] - expect) < 1e-9


def test_kernel_budget_kill():
    import pytest
    with pytest.raises(qsvm.Killed):
        qsvm.quantum_kernel(np.random.default_rng(2).uniform(0, 3, size=(6, 3)), budget_s=-1)


def test_killed_when_too_few_labelled_windows(tmp_path):
    p = tmp_path / "e.db"
    conn = db.connect(p)
    from engine.precursor import _ensure_table
    _ensure_table(conn)
    out = qsvm.run(p, save=False)
    assert out["status"] == "killed" and "labelled windows" in out["reason"]
