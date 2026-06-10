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
uv run pyghx write-csharp-script-template --output my_script.cs
uv run pyghx generate-csharp-addition --output generated_csharp_addition.ghx
uv run pyghx compute tests/fixtures/csharp_addition.ghx --number X=2 --number Y=3 --json
uv run pyghx set-script-source generated_csharp_addition.ghx --source-file my_script.cs
uv run pyghx repair-contextual-inputs tests/fixtures/csharp_addition_raw.ghx --nickname 6ff49b4e-be51-4113-a28d-f99ca930859d=X --nickname 19e82177-c780-4c7e-995c-4da6b1579038=Y
uv run pyghx remove-context-bake tests/fixtures/csharp_addition_raw.ghx c5bbe4a9-4b2c-4253-9a8c-03da1002ae74
uv run pyghx add-csharp-number-input generated_csharp_addition.ghx --name Z --variable-name z
uv run pyghx rename-csharp-input generated_csharp_addition.ghx --name X --new-name Length --variable-name length
uv run pyghx remove-csharp-input generated_csharp_addition.ghx --variable-name z
```

`validate` reports duplicate contextual input/output names before RhinoCompute execution. `inspect --json` includes a `script_components` field with decoded source text and script parameter metadata.

AI agent edit loop for C# Script GHX:

```powershell
uv run pyghx write-csharp-script-template --output my_script.cs
# Edit only the RunScript body in my_script.cs
uv run pyghx generate-csharp-addition --output agent_graph.ghx
uv run pyghx set-script-source agent_graph.ghx --source-file my_script.cs
uv run pyghx add-csharp-number-input agent_graph.ghx --name Z --variable-name z
uv run pyghx inspect --json agent_graph.ghx
uv run pyghx validate agent_graph.ghx
uv run pyghx compute agent_graph.ghx --number X=2 --number Y=3 --number Z=4 --json
```

The default C# Script template starts with `a = null;`. Replace that line with your logic before `set-script-source`. `generate-csharp-addition` keeps the existing addition sample GHX; use `write-csharp-script-template` when you want a fresh editable `.cs` starting point.

`validate` checks GHX structure and RhinoCompute contracts only. It does not analyze or sandbox C# Script source code. Graph-edit diagnostics include `run_script_signature_mismatch`, `script_input_not_wired`, `script_input_missing_contextual_source`, and `script_parameter_duplicate_name`.

`validate` also reports GHX XML integrity issues such as `object_count_mismatch`, `object_index_mismatch`, `duplicate_instance_guid`, and `unresolved_source_guid`. Cosmetic count mismatches such as `library_count_mismatch` are warnings only. `compute` runs the same structural preflight and refuses to contact RhinoCompute when error-level integrity diagnostics are present.

Renaming or adding C# Script inputs updates `RunScript` signatures and GHX wiring automatically. C# source bodies are not rewritten; update them with `set-script-source` when variable names change inside the script body.

## Import 3DM / STEP

Import geometry from STEP or other supported files through RhinoCompute-ready fixtures. Do not commit private model paths; pass them via CLI args or environment variables.

Single model (`tests/fixtures/import_model.ghx`):

```powershell
uv run pyghx validate tests/fixtures/import_model.ghx
uv run pyghx compute tests/fixtures/import_model.ghx --text "Get File Path=C:\path\to\model.stp" --json
```

Two models (`tests/fixtures/import_two_models.ghx`):

```powershell
uv run pyghx validate tests/fixtures/import_two_models.ghx
uv run pyghx compute tests/fixtures/import_two_models.ghx `
  --text "Target=C:\path\to\target.stp" `
  --text "Obstacle=C:\path\to\obstacle.stp" `
  --json
```

Optional integration tests with local STEP files:

```powershell
$env:PYGHX_IMPORT_STEP_PATH = "C:\path\to\model.stp"
$env:PYGHX_IMPORT_TARGET_STEP_PATH = "C:\path\to\target.stp"
$env:PYGHX_IMPORT_OBSTACLE_STEP_PATH = "C:\path\to\obstacle.stp"
uv run pytest tests/test_compute.py -k "import_model" -m integration
```

Regenerate the two-model fixture after editing the generator script:

```powershell
uv run python scripts/create_import_two_models_fixture.py
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
