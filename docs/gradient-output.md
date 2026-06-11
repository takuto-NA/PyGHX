# In-graph penalty and Gradient outputs

Seven-degree-of-freedom forward finite difference can run inside one Grasshopper definition so RhinoCompute returns both `penalty` and `Gradient` in a single `compute` call.

## What the derived GHX does

1. `FiniteDifferenceCases` builds eight scalar cases from the base inputs and seven `+0.01` perturbations.
2. The existing penalty graph evaluates all eight cases in one solve.
3. `PenaltyGradientAggregator` collects the eight penalty values and emits:
   - `penalty`: base-case penalty
   - `Gradient`: seven forward-difference components `[dP/dX, dP/dY, dP/dZ, dP/dRX, dP/dRY, dP/dRZ, dP/dRS]`

Forward-difference step size is `h = 0.01` for every degree of freedom. Regenerate an existing gradient GHX after changing this step; embedded C# Script constants are fixed at transform time.

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

## Projected gradient descent

After deriving a gradient GHX, search for inputs that drive `penalty` toward zero while keeping selected variables fixed. The default start is `(0.0, -0.04, 0.0, 0.0, 0.0, 0.0, 0.0)` with `Y=-0.04` fixed.

```powershell
uv run pyghx descend-gradient path\to\definition_gradient.ghx `
  --url http://localhost:5000/ `
  --json
```

Override the start or fixed values when needed:

```powershell
uv run pyghx descend-gradient path\to\definition_gradient.ghx `
  --fixed Y=-0.04 `
  --initial X=0 --initial Z=0 --initial RX=0 --initial RY=0 --initial RZ=0 --initial RS=0 `
  --tolerance 0.001 `
  --gradient-tolerance 0.001 `
  --max-iterations 100 `
  --initial-step-size 0.25 `
  --maximum-step-size 0.25 `
  --minimum-step-size 0.001 `
  --step-growth-factor 2.0 `
  --url http://localhost:5000/ `
  --json
```

The command optimizes `penalty` directly using projected steepest descent. `penalty` is already a squared-sum objective, so it is not squared again. Fixed variables are excluded from the search direction. Each accepted step must pass projected Armijo backtracking line search, so rejected trial steps that increase `penalty` are not committed.

Default line search is tuned from the `Y=-0.1` exact descent run: `--initial-step-size 0.25`, `--maximum-step-size 0.25`, and `--minimum-step-size 0.001`. After an accepted step, the next trial step grows by `--step-growth-factor 2.0` up to the maximum, so repeated successful `0.125` steps can retry `0.25` without allowing numerically meaningless tiny steps.

In exact `--source-ghx` mode, full gradient evaluations use eight RhinoCompute calls (`base + 7` perturbations). Line-search trial steps evaluate only scalar `penalty`, so rejected trials use one RhinoCompute call each instead of recomputing the full finite-difference gradient.

For optimization, pass the original scalar penalty GHX with `--source-ghx`. This exact mode evaluates `penalty` and finite-difference gradients from the same original objective, avoiding the vectorized in-graph penalty mismatch:

```powershell
uv run pyghx descend-gradient path\to\definition_gradient.ghx `
  --source-ghx path\to\definition.ghx `
  --finite-difference-step 0.01 `
  --url http://localhost:5000/ `
  --json
```

The gradient GHX still exists for inspecting in-graph vectorized behavior, but its `penalty` can differ from the original scalar GHX because Grasshopper list/tree data matching changes the graph evaluation. Do not use the derived GHX `penalty` as the objective for optimization unless a separate identity check confirms it matches the original scalar penalty for the target graph.

Stop reasons:

- `converged`: projected Gradient norm reached `--gradient-tolerance`
- `max_iterations_reached`: iteration budget exhausted
- `step_size_too_small`: no acceptable Armijo step remained
- `zero_projected_gradient`: projected search direction became zero

Each run records metrics in the JSON output under `run_metrics`:

- `evaluation_count`: RhinoCompute evaluations used by the search
- `rhino_compute_call_count`: actual RhinoCompute calls; exact `--source-ghx` finite difference uses eight calls per evaluation
- `penalty_only_evaluation_count`: scalar penalty-only line-search trials
- `penalty_only_rhino_compute_call_count`: actual RhinoCompute calls used by penalty-only trials
- `accepted_iteration_count`: accepted gradient descent steps
- `rejected_line_search_trial_count`: rejected Armijo trial steps
- `total_wall_clock_milliseconds`: end-to-end search time
- `total_evaluate_milliseconds`: time spent inside evaluations
- `initial_penalty`: penalty at the starting inputs
- `final_projected_gradient_norm`: fixed variables excluded from the norm

By default, the full run record is also written to `.pyghx/descent_latest.json` (gitignored). Override the path with `--record-json path\to\record.json`, or disable disk output with `--no-record`.

Integration test:

```powershell
$env:PYGHX_DESCENT_GRADIENT_GHX = "path\to\definition_gradient.ghx"
uv run pytest tests/test_gradient_descent_integration.py -q
```

If only the source penalty GHX is available, set `PYGHX_GRADIENT_SOURCE_GHX` instead. The test will derive a temporary gradient GHX under `.pyghx/`.

## Privacy

Do not commit private absolute paths, customer directory names, or private GHX basenames. Keep generated customer GHX files outside the repository or under a gitignored working directory.
