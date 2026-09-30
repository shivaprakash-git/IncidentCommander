"""Phase 5.5 (stretch): QSVM vs classical SVM / GBM on the Phase 3 labelled windows.

Deliberately minimal and honest:
  * data = the persisted precursor_vectors (pre-incident window = 1, normal = 0); no new features
  * keep the K highest-variance features (raw-count variance, K=5), min-max scale to [0, pi]
  * quantum kernel k(x,y) = |<phi(y)|phi(x)>|^2 from an AngleEmbedding circuit and its
    adjoint on `default.qubit` (one embedding layer, reps=1), fed to SVC(kernel="precomputed")
  * same features, same folds, same C for the classical SVM (RBF) and a small GBM
  * N is tiny, so metrics come from 10x repeated stratified 5-fold CV (pooled
    out-of-fold predictions per repeat, mean +/- std over repeats). No tuning.
Kill criteria: kernel > 10 min wall-clock, or fewer than 15 labelled windows -> status "killed".
Note: a single AngleEmbedding layer gives a product-state kernel, so it is classically
simulable; a quantum advantage is not expected or claimed.

CLI:  python -m engine.qsvm
"""
from __future__ import annotations

import argparse
import json
import time
from typing import Optional

import numpy as np

from . import db
from .config import CACHE_DIR, DB_PATH
from .precursor import load_labeled

RESULT_PATH = CACHE_DIR / "qsvm_result.json"
N_FEATURES = 5
MIN_LABELED = 15
KERNEL_BUDGET_S = 600
C = 1.0
SEED = 0


class Killed(Exception):
    pass


def select_and_scale(X: np.ndarray, names: list, k: int = N_FEATURES) -> tuple:
    idx = np.argsort(X.var(axis=0))[::-1][:k]
    Xs = X[:, idx].astype(float)
    lo, hi = Xs.min(axis=0), Xs.max(axis=0)
    span = np.where(hi > lo, hi - lo, 1.0)
    return (Xs - lo) / span * np.pi, [names[i] for i in idx]


def quantum_kernel(Xs: np.ndarray, budget_s: float = KERNEL_BUDGET_S) -> tuple:
    """Full symmetric Gram matrix via circuit overlap; returns (K, seconds)."""
    import pennylane as qml
    n_q = Xs.shape[1]
    dev = qml.device("default.qubit", wires=n_q)

    @qml.qnode(dev)
    def overlap(a, b):
        qml.AngleEmbedding(a, wires=range(n_q), rotation="Y")
        qml.adjoint(qml.AngleEmbedding)(b, wires=range(n_q), rotation="Y")
        return qml.probs(wires=range(n_q))

    n, K, t0 = len(Xs), np.eye(len(Xs)), time.perf_counter()
    for i in range(n):
        for j in range(i + 1, n):
            K[i, j] = K[j, i] = float(overlap(Xs[i], Xs[j])[0])
        if time.perf_counter() - t0 > budget_s:
            raise Killed(f"kernel computation exceeded {budget_s:.0f}s")
    return K, time.perf_counter() - t0


def _metrics(y, pred, score) -> dict:
    from sklearn.metrics import precision_score, recall_score, roc_auc_score
    return {"precision": precision_score(y, pred, zero_division=0), "recall": recall_score(y, pred, zero_division=0),
            "auc": roc_auc_score(y, score)}


def evaluate(Xs: np.ndarray, y: np.ndarray, K: np.ndarray, n_splits: int = 5, n_repeats: int = 10) -> dict:
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.model_selection import StratifiedKFold
    from sklearn.svm import SVC

    per_repeat = {m: [] for m in ("qsvm", "svm_rbf", "gbm")}
    for rep in range(n_repeats):
        oof = {m: (np.zeros(len(y), int), np.zeros(len(y))) for m in per_repeat}
        for tr, te in StratifiedKFold(n_splits, shuffle=True, random_state=SEED + rep).split(Xs, y):
            q = SVC(kernel="precomputed", C=C, class_weight="balanced").fit(K[np.ix_(tr, tr)], y[tr])
            r = SVC(kernel="rbf", C=C, gamma="scale", class_weight="balanced").fit(Xs[tr], y[tr])
            g = GradientBoostingClassifier(n_estimators=100, max_depth=2, random_state=SEED).fit(Xs[tr], y[tr])
            oof["qsvm"][0][te], oof["qsvm"][1][te] = q.predict(K[np.ix_(te, tr)]), q.decision_function(K[np.ix_(te, tr)])
            oof["svm_rbf"][0][te], oof["svm_rbf"][1][te] = r.predict(Xs[te]), r.decision_function(Xs[te])
            oof["gbm"][0][te], oof["gbm"][1][te] = g.predict(Xs[te]), g.predict_proba(Xs[te])[:, 1]
        for m, (pred, score) in oof.items():
            per_repeat[m].append(_metrics(y, pred, score))
    return {m: {k: {"mean": float(np.mean([r[k] for r in rs])), "std": float(np.std([r[k] for r in rs]))}
                for k in ("precision", "recall", "auc")} for m, rs in per_repeat.items()}


def run(db_path=DB_PATH, save: bool = True) -> dict:
    X, y, names, meta = load_labeled(db.connect(db_path))
    out: dict = {"n_labeled": int(len(y)), "n_positive": int(y.sum()), "n_negative": int((1 - y).sum())}
    t0 = time.perf_counter()
    try:
        if len(y) < MIN_LABELED or y.sum() < 2:
            raise Killed(f"only {len(y)} labelled windows ({int(y.sum())} positive); need >= {MIN_LABELED}")
        Xs, feats = select_and_scale(X, names)
        K, kt = quantum_kernel(Xs)
        out.update(status="ok", features=feats, kernel_seconds=round(kt, 2),
                   cv="10x repeated stratified 5-fold, pooled out-of-fold predictions",
                   results=evaluate(Xs, y, K),
                   note="one AngleEmbedding layer = product-state kernel (classically simulable); "
                        "N is small, so differences are within noise unless stated otherwise")
    except Killed as exc:
        out.update(status="killed", reason=str(exc))
    out["elapsed_seconds"] = round(time.perf_counter() - t0, 1)
    if save:
        RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
        RESULT_PATH.write_text(json.dumps(out, indent=2))
    return out


def load_result() -> Optional[dict]:
    """The stored comparison, or None (API route is only registered when status == ok)."""
    if RESULT_PATH.exists():
        r = json.loads(RESULT_PATH.read_text())
        return r if r.get("status") == "ok" else None
    return None


def print_result(o: dict) -> None:
    print(f"N labelled windows = {o['n_labeled']} ({o['n_positive']} pre-incident, {o['n_negative']} normal)")
    if o["status"] != "ok":
        print(f"KILLED: {o['reason']}")
        return
    print(f"features (top-{len(o['features'])} variance): {o['features']}   kernel time {o['kernel_seconds']}s")
    print(f"{o['cv']}")
    print(f"{'model':<9} {'precision':>16} {'recall':>16} {'AUC':>16}")
    for m, r in o["results"].items():
        f = lambda k: f"{r[k]['mean']:.3f}+/-{r[k]['std']:.3f}"
        print(f"{m:<9} {f('precision'):>16} {f('recall'):>16} {f('auc'):>16}")
    print("note:", o["note"])


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="QSVM vs classical on precursor labelled windows")
    p.add_argument("--db", default=str(DB_PATH))
    a = p.parse_args(argv)
    print_result(run(a.db))


if __name__ == "__main__":
    main()
