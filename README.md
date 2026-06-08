# PyGHX

Inspect, validate, summarize, and evaluate Grasshopper `.ghx` XML files for AI agents and RhinoCompute.

## Quick start

```powershell
uv sync
uv run pyghx inspect --json tests/fixtures/addition.ghx
uv run pyghx inspect --json --full tests/fixtures/addition.ghx
uv run pyghx validate tests/fixtures/addition.ghx
uv run pyghx compute tests/fixtures/addition.ghx --number X=2 --number Y=3 --json
uv run pyghx generate-addition --output generated_addition.ghx
uv run pyghx inspect --json generated_addition.ghx
uv run pyghx validate generated_addition.ghx
uv run pyghx compute generated_addition.ghx --number X=2 --number Y=3 --json
```

## Reference patterns (local, private)

Extract reusable subgraph patterns from a reference GHX into a local catalog. Output stays under `.pyghx/` (gitignored). Do not commit proprietary GHX files.

```powershell
uv run pyghx extract-patterns tests/fixtures/addition.ghx --output-dir .pyghx/patterns
uv run pyghx list-patterns --catalog .pyghx/patterns/catalog.json --json
uv run pyghx inspect-pattern addition_binary --catalog .pyghx/patterns/catalog.json --json
uv run pyghx generate-from-pattern addition_binary --catalog .pyghx/patterns/catalog.json --output generated_from_pattern.ghx
```

For private reference files (not in the repo), set `PYGHX_REFERENCE_GHX` and run optional tests:

```powershell
$env:PYGHX_REFERENCE_GHX = "C:\path\to\private.ghx"
uv run pytest -m private_reference
```

## RhinoCompute

Live integration tests expect RhinoCompute at `http://localhost:5000/`.

```powershell
uv run pytest -m integration
```
