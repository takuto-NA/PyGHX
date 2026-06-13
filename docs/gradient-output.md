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

### L-BFGS-B optimization

Use `lbfgs-gradient` when the steepest descent line search takes many accepted steps. It uses the same evaluator contract as `descend-gradient`, but passes `penalty` and projected `Gradient` to SciPy's L-BFGS-B optimizer. Fixed variables are removed from the optimizer vector, so `--fixed Y=-1` keeps `Y` unchanged.

```powershell
uv run pyghx lbfgs-gradient path\to\definition_gradient.ghx `
  --source-ghx path\to\definition.ghx `
  --fixed Y=-1 `
  --finite-difference-step 0.01 `
  --max-iterations 40 `
  --gradient-tolerance 0.001 `
  --url http://localhost:5000/ `
  --json
```

Exact `--source-ghx` L-BFGS-B still costs eight RhinoCompute calls per function/gradient evaluation, but it can require far fewer optimizer iterations than steepest descent because it approximates curvature from recent gradients. Tune `--history-size` and `--maximum-line-search-steps` only after comparing recorded `evaluation_count` and `rhino_compute_call_count`.

The source penalty GHX may expose the scalar as `penalty`; if it has exactly one output, that single output is also accepted as the scalar penalty.

To prevent unconstrained L-BFGS from escaping to a far-away zero-penalty region, cap each movement in normalized units:

```powershell
uv run pyghx lbfgs-gradient path\to\definition_gradient.ghx `
  --source-ghx path\to\exact_penalty.ghx `
  --fixed Y=-10 `
  --maximum-movement-norm 0.25 `
  --finite-difference-step 0.01 `
  --max-iterations 40 `
  --url http://localhost:5000/ `
  --json
```

When `--maximum-movement-norm` is set, pyghx uses a capped L-BFGS loop: it builds an L-BFGS direction, caps `||delta / scale||`, runs penalty-only Armijo line search, and evaluates the full finite-difference gradient only after accepting a step. Default scales are `X/Y/Z/RS=1` and `RX/RY/RZ=10`; override them with `--movement-scale RX=5` if the units need different weighting.

Stop reasons:

- `converged`: projected Gradient norm reached `--gradient-tolerance`
- `penalty_tolerance_reached`: penalty reached `--tolerance`
- `max_iterations_reached`: iteration budget exhausted
- `step_size_too_small`: no acceptable Armijo step remained
- `zero_projected_gradient`: projected search direction became zero
- `optimizer_converged`: L-BFGS-B stopped successfully before local gradient classification matched this wrapper's thresholds
- `optimizer_stopped`: L-BFGS-B stopped without satisfying the wrapper thresholds

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

## Optimization lessons learned

The optimization path is sensitive to which penalty is being optimized. Use the original scalar penalty GHX with `--source-ghx` for production searches. The derived gradient GHX is useful for inspecting one-call vectorized behavior, but its in-graph `penalty` can differ from the original scalar objective because Grasshopper list/tree matching changes graph evaluation. Optimizing against a penalty that does not match the original objective invalidates the search.

Do not square a penalty that is already a residual sum or squared residual. Squaring it again makes the search gradient shrink in already-small penalty regions and can stall progress even when the projected `Gradient` norm remains meaningful. Treat `penalty` as the objective unless the source graph explicitly emits an unsquared residual.

For exact `--source-ghx` finite differences, full gradient evaluations are expensive (`base + 7` calls). Keep line-search trials penalty-only. This makes rejected trials cost one RhinoCompute call instead of recomputing all seven finite-difference perturbations, and it was the most direct improvement for rejected-step overhead.

L-BFGS can reduce the number of accepted optimizer iterations dramatically compared with steepest descent, but unconstrained L-BFGS may escape to a far-away zero-penalty region if the penalty becomes zero once geometry no longer intersects. If a local, physically meaningful solution is required, use `--maximum-movement-norm` and eventually box bounds or regularization. Movement limiting should cap the actual update `delta`, not the raw `Gradient`, because an L-BFGS step is `delta = -H_k * Gradient` and the inverse-Hessian approximation can amplify or rotate the gradient.

Use normalized movement units when applying a cap. Translation, rotation, and scale have different units, so cap `||delta / scale||` instead of the raw Euclidean norm. The current defaults use `X/Y/Z/RS=1` and `RX/RY/RZ=10`; these are only starting scales and should be tuned to the model's physical units.

`SolidIntersection`-based penalties are often nonsmooth. Small input changes can change topology, null/non-null branches, intersection volume, or component output structure. This makes finite-difference gradients noisy or very large near contact transitions. In the observed runs, removing an extra `Square` from an already-large geometric penalty reduced both penalty and gradient scale. For the unsquared exact penalty, `h=0.001` performed better than `h=0.01` and `h=0.0001`: `0.01` was too coarse for some contact transitions, while `0.0001` appeared too close to geometric tolerance/noise and caused many rejected line-search trials.

Recommended starting point for nonsmooth exact geometry penalties:

```powershell
uv run pyghx lbfgs-gradient path\to\definition_gradient.ghx `
  --source-ghx path\to\exact_penalty.ghx `
  --fixed Y=-10 `
  --finite-difference-step 0.001 `
  --maximum-movement-norm 0.25 `
  --max-iterations 80 `
  --url http://localhost:5000/ `
  --json
```

Treat the recorded `run_metrics` as part of the result, not just profiling. Compare `evaluation_count`, `penalty_only_evaluation_count`, rejected trial count, final penalty, and projected gradient norm together. A lower final penalty with many rejected trials may indicate noisy gradients; a smaller movement cap may be stable but too slow; a very small finite-difference step may make the optimizer chase geometry tolerance instead of the objective.

### Y path continuation

Use `trace-y-path` to move `Y` in fixed steps while optimizing the other six variables at each station. Each station reuses the previous station's solution as a warm start, optionally applies a secant prediction, caps normalized movement, and runs capped L-BFGS with the exact `--source-ghx` penalty.

```powershell
uv run pyghx trace-y-path path\to\definition_gradient.ghx `
  --source-ghx path\to\exact_penalty.ghx `
  --start-y 0 `
  --end-y -50 `
  --y-step -1 `
  --finite-difference-step 0.001 `
  --maximum-movement-norm 0.25 `
  --max-iterations-per-y 80 `
  --url http://localhost:5000/ `
  --json
```

Outputs:

- `.pyghx/y_path_trace.jsonl`: header config plus one station record per completed `Y`
- `.pyghx/y_path_trace.csv`: quick summary for plotting and review

Resume after interruption:

```powershell
uv run pyghx trace-y-path path\to\definition_gradient.ghx `
  --source-ghx path\to\exact_penalty.ghx `
  --resume `
  --json
```

Runtime guidance:

- Start with a short smoke run such as `Y=0 -> -2` before attempting `Y=0 -> -50`.
- With the Square-removed exact penalty and `h=0.001`, one station near `Y=-10` took about 250 seconds and roughly 374 RhinoCompute calls.
- A full `Y=0 -> -50` trace is therefore on the order of several hours unless stations converge faster with warm starts.
- Use `--resume` and per-station JSONL checkpoints so a long run can continue after interruption.

Observed continuation result for the exact solid-intersection penalty:

- The all-zero pose can be a poor starting branch even when `Y=0` has zero penalty.
- A better initial branch was found with `RZ=10.569` and `RS=17.6`, leaving the other variables at zero.
- With `--finite-difference-step 0.001`, `--maximum-movement-norm 0.25`, `--max-iterations-per-y 80`, and `--continue-on-station-failure`, a full `Y=0 -> -50` trace completed 51 stations in about 25.8 minutes and 1239 RhinoCompute calls.
- The run produced 35 zero-penalty stations, 12 stations below the `0.001` penalty tolerance, and 4 optimizer-stopped stations.
- The only notable high-penalty range was early in the path: `Y=-2` to `Y=-5`, with maximum penalty about `0.0143` at `Y=-4`.
- The final `Y=-50` station reached penalty `0.0` at approximately `X=-4.657`, `Z=-1.049`, `RX=-4.281`, `RY=33.233`, `RZ=0.369`, `RS=14.648`.

Example command for that branch:

```powershell
uv run pyghx trace-y-path path\to\exact_penalty.ghx `
  --source-ghx path\to\exact_penalty.ghx `
  --start-y 0 `
  --end-y -50 `
  --y-step -1 `
  --initial RZ=10.569 `
  --initial RS=17.6 `
  --finite-difference-step 0.001 `
  --maximum-movement-norm 0.25 `
  --max-iterations-per-y 80 `
  --continue-on-station-failure `
  --record-jsonl .pyghx\y_path_trace_exact_initial_rz_rs.jsonl `
  --record-csv .pyghx\y_path_trace_exact_initial_rz_rs.csv `
  --url http://localhost:5000/ `
  --json
```

## Privacy

Do not commit private absolute paths, customer directory names, or private GHX basenames. Keep generated customer GHX files outside the repository or under a gitignored working directory.
