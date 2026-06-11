# In-graph penalty and Gradient outputs

Seven-degree-of-freedom forward finite difference can run inside one Grasshopper definition so RhinoCompute returns both `penalty` and `Gradient` in a single `compute` call.

## What the derived GHX does

1. `FiniteDifferenceCases` builds eight scalar cases from the base inputs and seven `+1.0` perturbations.
2. The existing penalty graph evaluates all eight cases in one solve.
3. `PenaltyGradientAggregator` collects the eight penalty values and emits:
   - `penalty`: base-case penalty
   - `Gradient`: seven forward-difference components `[dP/dX, dP/dY, dP/dZ, dP/dRX, dP/dRY, dP/dRZ, dP/dRS]`

Forward-difference step size is `h = 1.0` for every degree of freedom.

## CLI

```powershell
uv run pyghx add-gradient-outputs `
  --input path\to\definition.ghx `
  --output path\to\definition_gradient.ghx
```

Validate and inspect the derived file:

```powershell
uv run pyghx validate path\to\definition_gradient.ghx
uv run pyghx inspect --json path\to\definition_gradient.ghx
```

Compute once:

```powershell
uv run pyghx compute path\to\definition_gradient.ghx `
  --number X=100 --number Y=50 --number Z=30 `
  --number RX=10 --number RY=5 --number RZ=15 --number RS=45 `
  --url http://localhost:5000/ `
  --json
```

## Python API

```python
from pathlib import Path

from pyghx.gradient_transform import transform_penalty_graph_for_gradient

transform_penalty_graph_for_gradient(
    Path(r"path\to\definition.ghx"),
    Path(r"path\to\definition_gradient.ghx"),
)
```

## Profiling benefit

The old external workflow calls RhinoCompute eight times for one gradient:

- one base penalty
- seven perturbed penalties

Each call repeats the full GHX upload. With `--profile`, compare:

```powershell
# Old workflow: eight separate compute calls on the original GHX
uv run pyghx compute path\to\definition.ghx --number X=100 --number Y=50 --profile

# New workflow: one compute call on the derived GHX
uv run pyghx compute path\to\definition_gradient.ghx --number X=100 --number Y=50 --profile
```

The derived GHX keeps the same Grasshopper solve cost for the eight cases but reduces RhinoCompute round trips from eight to one. See [compute-profiling.md](compute-profiling.md) for the phase model.

## Integration test

Set a local source GHX path, then run:

```powershell
$env:PYGHX_GRADIENT_SOURCE_GHX = "path\to\definition.ghx"
uv run pytest tests/test_gradient_integration.py -q
```

The tests check the derived compute contract, verify that `Gradient` matches the forward difference of the eight vectorized `Stream Filter` penalties for two input samples, and assert that one derived-GHX call has a lower total `rhino_compute_round_trip_milliseconds` than eight isolated original-GHX calls.

In-graph gradients are forward differences of the eight penalties produced inside that single vectorized evaluation. They can differ from an external finite-difference loop on the original GHX because list vectorization changes how the graph evaluates each case.

## Lessons learned

The main implementation risk was assuming a Grasshopper wire's data shape from the visible graph. RhinoCompute evaluation showed that a value which looked like a list at the graph level could reach a C# Script as repeated item-level calls, depending on the upstream component, access mode, and data matching rules.

Avoid treating these as interchangeable contracts:

- eight isolated RhinoCompute calls to the original GHX
- one vectorized RhinoCompute call that carries base plus seven perturbed cases through the graph
- the access mode seen by an inserted C# Script component (`Item`, `List`, or `Tree`)

For this feature, the correct acceptance target is the vectorized one-call graph. The `Gradient` output is therefore tested against the eight penalty values observed inside that same graph, immediately after the `Stream Filter`, not against an external finite-difference loop on the original GHX.

## Prevention checklist

Use this sequence before adding future C# Script components to a private or customer GHX:

1. Identify the exact upstream wire that should become the script input.
2. Generate a probe GHX that bakes the candidate wire directly.
3. Run `validate`, `inspect --json`, and `compute` against the probe.
4. Record the observed value count, branch shape, and scalar type before choosing `ScriptParamAccess` or `TypeHintID`.
5. Prefer wiring from native Grasshopper component outputs when crossing into a new C# Script component.
6. Write the integration test against the observed in-graph data shape first, then add performance assertions separately.
7. Keep generated GHX files and private source paths out of tracked repository content.

If the probe shows item-level evaluation for a vectorized sequence, aggregate explicitly and keep the case count named in code. Do not rely on magic indices or hidden Grasshopper ordering assumptions without a regression test that computes the same intermediate values.

## Privacy

Do not commit private absolute paths, customer directory names, or private GHX basenames. Keep generated customer GHX files outside the repository or under a gitignored working directory.
