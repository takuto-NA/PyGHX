# PyGHX

Inspect, validate, summarize, and evaluate Grasshopper `.ghx` XML files for AI agents and RhinoCompute.

## Quick start

```powershell
uv sync
uv run pyghx inspect --json tests/fixtures/addition.ghx
uv run pyghx validate tests/fixtures/addition.ghx
uv run pyghx compute tests/fixtures/addition.ghx --number X=2 --number Y=3 --json
```

## RhinoCompute

Live integration tests expect RhinoCompute at `http://localhost:5000/`.

```powershell
uv run pytest -m integration
```
