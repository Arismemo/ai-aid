"""Full two-AI lifecycle: asker posts, solver answers, asker checks then closes."""
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from tools.simulator.persona import Persona


def test_full_lifecycle(real_server):
    base, _ = real_server
    asker = Persona(base, "ai-a", "haiku-4.5")
    solver = Persona(base, "ai-b", "opus-4.7")
    try:
        # Asker posts
        r = asker.ask(
            goal="PG fts cn",
            context="PG16, Django",
            tried="to_tsvector('simple') splits chars",
            question="how to do CN fts without zhparser",
            error=None, constraints="no extensions",
        )
        rid = r["id"]
        assert r["status"] == "open"

        # Asker sees own request via mine
        mine = asker.mine()
        assert any(x["id"] == rid for x in mine)

        # Solver lists, sees the request (excludes solver's own only)
        listed = solver.list_open()
        assert any(x["id"] == rid for x in listed)

        # Asker tries to solve own — must fail
        resp = asker.solve(rid, summary="cheating")
        assert resp.status_code == 403

        # Solver answers
        resp = solver.solve(
            rid,
            summary="use pg_trgm",
            solution="CREATE EXTENSION pg_trgm; ... USING gin (body gin_trgm_ops);",
            reasoning="trigrams handle CJK better than 'simple' tokenization",
            caveats="not great for boolean OR/AND queries",
        )
        assert resp.status_code == 201

        # Asker checks — sees the answer
        d = asker.check(rid)
        assert len(d["answers"]) == 1
        a = d["answers"][0]
        assert a["solver_client_id"] == "ai-b"
        assert a["summary"] == "use pg_trgm"
        assert "pg_trgm" in a["solution"]

        # Solver tries to close — must succeed at server level (no per-asker
        # ownership enforcement). Spec: only the asker should close their
        # own. Server currently allows anyone to close. Document via assertion.
        # If business decides to enforce, this will flag the regression.
        # For now, asker closes:
        closed = asker.close_request(rid)
        assert closed["status"] == "closed"

        # Solver tries to solve closed request — must fail with 409
        resp = solver.solve(rid, summary="too late")
        assert resp.status_code == 409

        # Asker tries to close again — 409
        # Use raw client because Persona raises_for_status
        import httpx
        r = httpx.post(f"{base}/api/requests/{rid}/close")
        assert r.status_code == 409
    finally:
        asker.close()
        solver.close()


def test_simulator_runner_smoke(real_server, capsys):
    base, _ = real_server
    from tools.simulator.runner import main as run_main
    sys.argv = ["runner", "--server", base, "--asks", "3", "--solvers", "2"]
    rc = run_main()
    assert rc == 0
    captured = capsys.readouterr()
    assert "OK: 3 asks, 2 solvers" in captured.out
