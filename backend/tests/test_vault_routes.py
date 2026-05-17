"""Tests for /api/vault/best-match — focuses on the `top_n` slicing parameter (issue #38)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# --- Fixtures ---------------------------------------------------------


def _make_fake_ranker(n):
    """Build a deterministic ``find_best_resume_for_job`` stub returning ``n`` rows."""
    def fake_find_best(job_description, db_path=None):
        return [
            {
                "version_key": f"v{i}",
                "display_name": f"Resume {i}",
                "combined_score": round(1.0 - i * 0.05, 4),
                "tfidf_similarity": 0.5,
                "skill_match_pct": 80 - i,
                "matched_skills": ["python", "sql"],
                "missing_skills": [],
            }
            for i in range(n)
        ]
    return fake_find_best


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Flask test client backed by a hermetic DB; 10-resume ranker by default."""
    db_path = str(tmp_path / "test.db")
    from storage.db import init_db
    init_db(db_path)

    monkeypatch.setenv("DB_PATH", db_path)
    monkeypatch.delenv("API_SECRET", raising=False)

    for mod in ["routes.vault_routes", "server"]:
        if mod in sys.modules:
            del sys.modules[mod]

    import server
    server.DB_PATH = db_path
    server.app.config["TESTING"] = True

    import storage.resume_vault as rv
    monkeypatch.setattr(rv, "find_best_resume_for_job", _make_fake_ranker(10))

    with server.app.test_client() as c:
        yield c


@pytest.fixture
def empty_client(tmp_path, monkeypatch):
    """Variant of ``client`` whose ranker returns ``[]`` (empty vault)."""
    db_path = str(tmp_path / "empty.db")
    from storage.db import init_db
    init_db(db_path)

    monkeypatch.setenv("DB_PATH", db_path)
    monkeypatch.delenv("API_SECRET", raising=False)

    for mod in ["routes.vault_routes", "server"]:
        if mod in sys.modules:
            del sys.modules[mod]

    import server
    server.DB_PATH = db_path
    server.app.config["TESTING"] = True

    import storage.resume_vault as rv
    monkeypatch.setattr(rv, "find_best_resume_for_job", _make_fake_ranker(0))

    with server.app.test_client() as c:
        yield c


# --- No top_n / absent -> returns all ---------------------------------


def test_best_match_no_top_n_returns_all(client):
    """No `top_n` in body → return full ranking (current behavior preserved)."""
    resp = client.post("/api/vault/best-match", json={"job_description": "Python SQL Spark Kafka"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["count"] == 10
    assert len(data["rankings"]) == 10


def test_best_match_null_top_n_returns_all(client):
    """top_n: null → treated as absent."""
    resp = client.post(
        "/api/vault/best-match",
        json={"job_description": "Python", "top_n": None},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["count"] == 10
    assert len(data["rankings"]) == 10


# --- Valid top_n -> slices --------------------------------------------


def test_best_match_top_n_3_returns_3(client):
    """top_n=3 → exactly 3 rankings returned; count still reflects total scanned."""
    resp = client.post(
        "/api/vault/best-match",
        json={"job_description": "Python", "top_n": 3},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["count"] == 10  # total scanned, NOT the slice length
    assert len(data["rankings"]) == 3
    # Slicing preserves order (best fit first).
    assert data["rankings"][0]["version_key"] == "v0"
    assert data["rankings"][2]["version_key"] == "v2"


def test_best_match_top_n_1_returns_1(client):
    """top_n=1 → only the top match."""
    resp = client.post(
        "/api/vault/best-match",
        json={"job_description": "Python", "top_n": 1},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["count"] == 10
    assert len(data["rankings"]) == 1
    assert data["rankings"][0]["version_key"] == "v0"


def test_best_match_top_n_larger_than_total_returns_all(client):
    """top_n=50 but only 10 resumes exist → returns all 10 (no padding/error)."""
    resp = client.post(
        "/api/vault/best-match",
        json={"job_description": "Python", "top_n": 50},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["count"] == 10
    assert len(data["rankings"]) == 10


def test_best_match_top_n_integral_float_slices(client):
    """top_n=5.0 → coerced to int(5), slices to 5 (new in round 2)."""
    resp = client.post(
        "/api/vault/best-match",
        json={"job_description": "Python", "top_n": 5.0},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["count"] == 10
    assert len(data["rankings"]) == 5


# --- Lenient inputs -> treated as absent ------------------------------


@pytest.mark.parametrize(
    "bad_top_n",
    [
        0,             # zero
        -1,            # negative int
        "foo",         # string
        "5",           # numeric string — still a string
        True,          # bool True (Python treats as int 1, but we reject bools)
        False,         # bool False — the OTHER bool, round 1 only tested True
        5.7,           # non-integral float
        0.5,           # non-integral fractional float
        [],            # list
        [5],           # non-empty list
        {},            # empty dict
        {"n": 5},      # dict
    ],
    ids=[
        "zero",
        "negative",
        "string_alpha",
        "string_numeric",
        "bool_true",
        "bool_false",
        "float_non_integral",
        "float_fractional",
        "list_empty",
        "list_nonempty",
        "dict_empty",
        "dict_nonempty",
    ],
)
def test_best_match_lenient_garbage_types_return_all(client, bad_top_n):
    """Garbage / out-of-domain top_n values → lenient: ignore and return all."""
    resp = client.post(
        "/api/vault/best-match",
        json={"job_description": "Python", "top_n": bad_top_n},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["count"] == 10
    assert len(data["rankings"]) == 10


# --- Over-cap -> 400 --------------------------------------------------


def test_best_match_top_n_over_cap_returns_400(client):
    """top_n=999 → 400 (abuse-prevention cap); error names cap and received value."""
    resp = client.post(
        "/api/vault/best-match",
        json={"job_description": "Python", "top_n": 999},
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["error"] == "top_n must be <= 50 (got 999)"


def test_best_match_top_n_51_returns_400(client):
    """top_n=51 → just over the cap, 400; error includes received value."""
    resp = client.post(
        "/api/vault/best-match",
        json={"job_description": "Python", "top_n": 51},
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["error"] == "top_n must be <= 50 (got 51)"


def test_best_match_top_n_50_accepted(client):
    """top_n=50 → exactly at the cap, accepted."""
    resp = client.post(
        "/api/vault/best-match",
        json={"job_description": "Python", "top_n": 50},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["count"] == 10
    assert len(data["rankings"]) == 10  # only 10 exist, so all returned


# --- Empty vault ------------------------------------------------------


def test_best_match_empty_vault_returns_empty_rankings(empty_client):
    """Vault returns no rankings → count=0, rankings=[] even with top_n set."""
    resp = empty_client.post(
        "/api/vault/best-match",
        json={"job_description": "Python", "top_n": 5},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["count"] == 0
    assert data["rankings"] == []


# --- Missing job_description still rejected ---------------------------


def test_best_match_missing_jd_still_400(client):
    """No `job_description` → 400, regardless of top_n."""
    resp = client.post("/api/vault/best-match", json={"top_n": 5})
    assert resp.status_code == 400
    assert "job_description" in resp.get_json()["error"]
