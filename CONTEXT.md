# PyGHX Glossary

## GHX

Grasshopper の `.ghx` XML形式ファイル。

## PyGHX

AIエージェントやPythonコードがGHXを読み取り、確認し、最小生成するためのライブラリ。

## JSON summary

AIエージェントがGHXの概要を安定して取得するための機械向けJSON出力。

## validation

XMLとして読めること、PyGHXが理解する既知構造を確認すること、未知要素と診断を報告すること。

## minimal generation

空または最小構成のGHXと、サンプルから根拠を持って作れる小型定義を生成すること。

## recipe generation

検証済みの固定テンプレートから、RhinoCompute で実行可能な GHX を生成すること。最初のレシピは `addition` 相当（`Get Number` X/Y、`Addition`、`Context Bake`）。

## reference pattern

参照 GHX からサブグラフ（部品）を抽出し、ローカル catalog に保存した再利用単位。`pattern_id` で識別する。

## pattern catalog

`extract-patterns` が生成する `catalog.json` と pattern GHX 群。`source_basename` のみを記録し、絶対パスは保存しない。デフォルト出力先は `.pyghx/patterns/`（gitignore）。

## RhinoCompute

GHX定義を外部プロセスとして評価するHTTPサービス。MVPでは `http://localhost:5000/` を統合テスト対象にする。

## Get Number

RhinoComputeやGrasshopper Playerから渡す数値入力を表すGrasshopperの文脈入力。

## Contextual input

RhinoComputeやGrasshopper Playerから実行時に渡される入力。MVPでは `Get Number` を実行対応の最初の対象とし、`Get Line`、`Get Boolean`、`Get Point`、`Get String`、`Get File Path` は `variation.ghx` で検出と契約化を進める。

## Context Bake

RhinoComputeやGrasshopper Playerで評価結果を取り出すための文脈出力。

## compute boundary

`extract-patterns` / `generate-from-pattern` が、Get Number など Compute 対応入力を持つパターンに Context Bake を自動付与する処理。RhinoCompute 実行には Context Bake が必須。

## RhinoCompute input encoding

`number` / `point` / `string` / `file_path` は Compute 対応。Point は `{"X":1,"Y":2,"Z":0}` の JSON 文字列、Text は `json.dumps` 済み文字列を `InnerTree["0"]` に載せる（`simple_compression_gh` と同形式）。

## C# Script component

Grasshopper の C# Script コンポーネント。ソースは GHX 内の `Container > Script > Text` に base64 エンコードされた C# として保存される。RhinoCompute 実行時は通常コンポーネントと同様にグラフの一部としてコンパイル・実行される。

## script source

C# Script コンポーネント内の C# ソース本文。PyGHX は `inspect --json` の `script_components[].source_text` でデコード済みテキストを返し、`set-script-source` / `get-script-source` で編集・取得できる。

## script parameter

C# Script の入出力パラメータ（例: `x`, `y`, `a`, `out`）。`inspect --json` の `script_components[].inputs` / `outputs` に名前、GUID、配線、標準出力かどうかを含める。

## csharp addition recipe

`Get Number` X/Y → `C# Script`（加算）→ `Context Bake` の RhinoCompute 対応レシピ。`generate-csharp-addition` で `csharp_addition_compute.ghx` テンプレートから生成する。

## script validation scope

`validate` は GHX 構造と RhinoCompute 契約（同名パラメータ、base64、Context Bake 欠落など）を検査する。C# Script のコード安全性や任意コード実行の可否は保証しない。
