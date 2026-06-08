"""Spike script for RhinoCompute grasshopper evaluation."""

from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

ADDITION_FIXTURE_PATH = Path("tests/fixtures/addition.ghx")
COMPUTE_URL = "http://localhost:5000/grasshopper"


def evaluate_definition_text(definition_text: str, values: list[dict]) -> None:
    request_body = {
        "algo": base64.b64encode(definition_text.encode("utf-8")).decode(),
        "values": values,
    }
    request = urllib.request.Request(
        COMPUTE_URL,
        data=json.dumps(request_body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            print("success", response.read()[:1000])
    except urllib.error.HTTPError as http_error:
        print("error", http_error.code, http_error.read()[:1000])


def main() -> None:
    original_text = ADDITION_FIXTURE_PATH.read_text(encoding="utf-8-sig")
    values = [
        {"ParamName": "X", "InnerTree": {"0": [{"data": "2"}]}},
        {"ParamName": "Y", "InnerTree": {"0": [{"data": "3"}]}},
    ]
    print("original")
    evaluate_definition_text(original_text, values)

    stripped_text = re.sub(
        r'            <chunk name="Object" index="0">.*?</chunk>\n',
        "",
        original_text,
        count=1,
        flags=re.DOTALL,
    )
    stripped_text = stripped_text.replace(
        '<item name="ObjectCount" type_name="gh_int32" type_code="3">5</item>',
        '<item name="ObjectCount" type_name="gh_int32" type_code="3">4</item>',
    )
    stripped_text = stripped_text.replace('<chunks count="5">', '<chunks count="4">', 1)
    print("without_logger")
    evaluate_definition_text(stripped_text, values)


if __name__ == "__main__":
    main()
