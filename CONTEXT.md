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
