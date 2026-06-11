# RhinoCompute profiling and bottlenecks

PyGHX `compute` の所要時間を **フェーズ別** に分解して計測する。計測は Windows + ローカル RhinoCompute (`http://localhost:5000/`) を前提とする。

## Phase model

`evaluate_document` / `pyghx compute --profile` は次の順で計測する。

### PyGHX client (local)

| Phase | What happens |
|-------|----------------|
| `inspect_milliseconds` | GHX XML 解析、Compute 契約構築 |
| `preflight_milliseconds` | 構造・配線・C# Script 契約の事前検査 |
| `read_definition_milliseconds` | GHX ファイル読み込み |
| `base64_encode_milliseconds` | 定義本文の base64 化 |
| `build_input_trees_milliseconds` | 入力 `values` の InnerTree 構築 |
| `json_serialize_milliseconds` | リクエスト JSON のシリアライズ |
| `normalize_outputs_milliseconds` | レスポンスの正規化 |

### HTTP / RhinoCompute (network boundary)

| Phase | What happens |
|-------|----------------|
| `http_wait_until_headers_milliseconds` | POST 送信完了からレスポンスヘッダ到達まで（TTFB 相当） |
| `http_read_response_body_milliseconds` | レスポンス本文の読み込み |

`http_wait_until_headers_milliseconds` には **アップロード + サーバー処理** が含まれる。urllib では送信完了とサーバー処理開始を分離できないため、クライアント単体ではここまで。

### Grasshopper server (estimated with `--profile-solve`)

RhinoCompute はコンポーネント単位のプロファイルを返さない。代わりに **pointer フォローアップ** でサーバー側を推定する。

| Phase | How it is measured |
|-------|---------------------|
| `grasshopper_solve_estimate_milliseconds` | `pointer` + 入力を微小変更した再 POST の `http_wait_until_headers_milliseconds` |
| `result_cache_lookup_milliseconds` | `pointer` + 同一入力の再 POST（結果キャッシュヒット時は数 ms〜数十 ms） |
| `definition_transfer_estimate_milliseconds` | 初回 `http_wait_until_headers` − `grasshopper_solve_estimate`（定義 decode / 登録 / 送信の粗い推定） |

`--profile-solve` は **追加で HTTP 2 本** 送る。最適化ループの本番計測には `--profile` のみを使う。

## CLI

```powershell
uv run pyghx compute path\to\definition.ghx `
  --number X=0 --number Y=0 `
  --url http://localhost:5000/ `
  --json --profile

uv run pyghx compute path\to\definition.ghx `
  --number X=0 --number Y=0 `
  --url http://localhost:5000/ `
  --json --profile --profile-solve
```

`timing` キーにフェーズ別ミリ秒が入る。集計用の派生値:

- `client_total_milliseconds` — PyGHX 全体
- `rhino_compute_round_trip_milliseconds` — JSON 化 + HTTP 往復

## Reference measurements

### Simple graph (`tests/fixtures/addition.ghx`)

| Phase | Warm |
|-------|------|
| End-to-end (`uv run pyghx compute`) | 〜145 ms |

### Geometry-heavy graph (`path\to\definition.ghx`, 〜660 KB)

| Phase | Warm |
|-------|------|
| `inspect_milliseconds` | 〜12 ms |
| `preflight_milliseconds` | 〜34 ms |
| `read_definition_milliseconds` + `base64_encode_milliseconds` | 〜1 ms |
| `http_wait_until_headers_milliseconds` (full `algo` POST) | 〜580 ms |
| `http_read_response_body_milliseconds` | &lt;1 ms |
| `grasshopper_solve_estimate_milliseconds` (`--profile-solve`) | 〜120 ms |
| `result_cache_lookup_milliseconds` (`pointer` + same inputs) | 〜17 ms |
| `definition_transfer_estimate_milliseconds` | 〜460 ms |
| `request_payload_bytes` (full `algo`) | 〜874,000 |

解釈:

- **Grasshopper 求解そのもの** は warm 時 **〜120 ms** 程度（入力依存）
- **定義の毎回フル送信** が残り **〜460 ms** を占める（660 KB GHX の decode + 登録 + アップロード）
- レスポンス本文は小さいので `http_read_response_body` は無視できる

### Cold start vs warm

Rhino / Grasshopper / RhinoCompute 起動直後は上記の数倍かかることがある。2 回目以降を warm として記録する。

## Known bottlenecks

### 1. Full GHX upload on every `compute`

PyGHX は毎リクエスト `algo` に GHX 全文を載せる。`pointer` 再利用は未実装。

### 2. Grasshopper graph complexity

埋め込み Brep、`Point In Brep`、`Brep Closest Point`、C# Script は求解コストが大きい。`--profile-solve` の `grasshopper_solve_estimate_milliseconds` で直接見る。

### 3. No per-component server profiling

RhinoCompute 標準 API ではコンポーネント別の求解時間は取れない。必要なら Grasshopper 側に計測用 C# Script を入れるか、サーバーログを見る。

### 4. PyGHX duplicate GHX reads

1 回の `compute` で inspect と preflight がそれぞれ GHX を読む（合計でも通常 100 ms 未満）。

## Python API

```python
from pathlib import Path

from pyghx.compute import ComputeInputValue, evaluate_document

compute_result = evaluate_document(
    Path(r"path\to\definition.ghx"),
    input_values=[
        ComputeInputValue(nickname="X", value=0),
        ComputeInputValue(nickname="Y", value=0),
    ],
    compute_url="http://localhost:5000/",
    collect_timing=True,
    estimate_grasshopper_solve=True,
)
print(compute_result.timing.to_dict() if compute_result.timing else None)
```

## Optimization directions

| Idea | Affects |
|------|---------|
| `pointer` 再利用（定義は一度だけ `algo` で送る） | `definition_transfer_estimate_milliseconds` |
| GHX 軽量化（Brep 外部化） | 送信量 + 求解 |
| 入力だけ変える反復ループ | `grasshopper_solve_estimate_milliseconds` のみ繰り返す |

## Related code

- Timing dataclass and phases: `src/pyghx/compute.py` (`ComputeTimingBreakdown`, `evaluate_document`)
- CLI flags: `src/pyghx/cli.py` (`--profile`, `--profile-solve`)
