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

## C# Script components

Inspect decoded C# source, validate RhinoCompute contracts, edit script text, and generate a C# addition recipe:

```powershell
uv run pyghx inspect --json tests/fixtures/csharp_addition.ghx
uv run pyghx validate tests/fixtures/csharp_addition.ghx
uv run pyghx get-script-source tests/fixtures/csharp_addition.ghx
uv run pyghx generate-csharp-addition --output generated_csharp_addition.ghx
uv run pyghx compute tests/fixtures/csharp_addition.ghx --number X=2 --number Y=3 --json
uv run pyghx set-script-source generated_csharp_addition.ghx --source-file my_script.cs
uv run pyghx repair-contextual-inputs tests/fixtures/csharp_addition_raw.ghx --nickname 6ff49b4e-be51-4113-a28d-f99ca930859d=X --nickname 19e82177-c780-4c7e-995c-4da6b1579038=Y
uv run pyghx remove-context-bake tests/fixtures/csharp_addition_raw.ghx c5bbe4a9-4b2c-4253-9a8c-03da1002ae74
```

`validate` reports duplicate contextual input/output names before RhinoCompute execution. `inspect --json` includes a `script_components` field with decoded source text and script parameter metadata.

`validate` checks GHX structure and RhinoCompute contracts only. It does not analyze or sandbox C# Script source code.

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
