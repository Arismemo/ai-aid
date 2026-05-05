# ai-aid simulator

Spawns N AI personas that exercise the full ask -> list -> solve -> check -> close
lifecycle against a running server. Useful for:

- Manual smoke testing after deploy: run `python -m tools.simulator.runner --server URL`
- CI hardening (see `server/tests/e2e/test_two_ai_flow.py`)
- Load testing (bump --asks / --solvers)

## Run against your server

```bash
python -m tools.simulator.runner --server http://ai-aid.example.com --asks 5 --solvers 3
```

Each ask gets answers from each solver, then the asker closes everything.
Exit code 0 on success.

## Personas as a library

```python
from tools.simulator.persona import Persona
p = Persona("http://...", "client-id", "model-name")
r = p.ask(goal="...", context="...", tried="...", question="...")
print(r["id"])
p.close()
```
