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

## RhinoCompute

GHX定義を外部プロセスとして評価するHTTPサービス。MVPでは `http://localhost:5000/` を統合テスト対象にする。

## Get Number

RhinoComputeやGrasshopper Playerから渡す数値入力を表すGrasshopperの文脈入力。

## Contextual input

RhinoComputeやGrasshopper Playerから実行時に渡される入力。MVPでは `Get Number` を実行対応の最初の対象とし、`Get Line`、`Get Boolean`、`Get Point`、`Get String`、`Get File Path` は `variation.ghx` で検出と契約化を進める。

## Context Bake

RhinoComputeやGrasshopper Playerで評価結果を取り出すための文脈出力。
