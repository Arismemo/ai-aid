"""CLI: simulate N personas hitting a server.

Usage:
  python -m tools.simulator.runner --server http://127.0.0.1:8000 \\
    --asks 10 --solvers 3
"""
import argparse
import random
import time

from .persona import Persona


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--server", required=True)
    p.add_argument("--asks", type=int, default=5)
    p.add_argument("--solvers", type=int, default=2)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()
    random.seed(args.seed)

    asker = Persona(args.server, "sim-asker", "sim-haiku")
    solvers = [
        Persona(args.server, f"sim-solver-{i}", "sim-opus")
        for i in range(args.solvers)
    ]
    try:
        rids = []
        for i in range(args.asks):
            r = asker.ask(
                goal=f"sim goal {i}",
                context="simulator harness",
                tried=f"attempt {i}-a; attempt {i}-b",
                question=f"how do {i}",
            )
            rids.append(r["id"])
            print(f"[ask] {r['id']}")

        for solver in solvers:
            for rid in rids:
                resp = solver.solve(rid, summary=f"answer from {solver.client_id}")
                print(f"[solve] {solver.client_id} -> {rid} : {resp.status_code}")

        for rid in rids:
            d = asker.check(rid)
            assert len(d["answers"]) == args.solvers, \
                f"expected {args.solvers} answers, got {len(d['answers'])}"

        for rid in rids:
            asker.close_request(rid)
            print(f"[close] {rid}")

        print(f"OK: {args.asks} asks, {args.solvers} solvers, all answers landed, all closed")
        return 0
    finally:
        asker.close()
        for s in solvers:
            s.close()


if __name__ == "__main__":
    raise SystemExit(main())
