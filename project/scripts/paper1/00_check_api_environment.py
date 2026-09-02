#!/usr/bin/env python3
"""Report only whether Paper-1 API variables are non-empty, never their values."""

from __future__ import annotations

import json
import os


KEYS = {
    "DASHSCOPE_API_KEY": {
        "role": "Semantic Memory v9 DEV and semantic compiler",
        "requirement": "REQUIRED_NOW",
    },
    "NVIDIA_API_KEY": {
        "role": "frozen Llama generator and RS uptake qualification",
        "requirement": "REQUIRED_LATER",
    },
    "OPENAI_API_KEY": {
        "role": "official ES-MemEval GPT-4o evaluation",
        "requirement": "REQUIRED_LATER",
    },
    "GEMINI_API_KEY": {
        "role": "supplemental or legacy judge runs",
        "requirement": "OPTIONAL",
    },
    "ANTHROPIC_API_KEY": {
        "role": "supplemental or legacy judge runs",
        "requirement": "OPTIONAL",
    },
    "DEEPSEEK_API_KEY": {
        "role": "supplemental DeepSeek sensitivity judge",
        "requirement": "OPTIONAL",
    },
    "HF_TOKEN": {
        "role": "future authenticated Hugging Face downloads",
        "requirement": "OPTIONAL",
    },
}


def status() -> dict[str, object]:
    variables = {
        key: {**metadata, "status": "PRESENT" if os.environ.get(key, "").strip() else "ABSENT"}
        for key, metadata in KEYS.items()
    }
    return {
        "protocol": "metacom5-3-paper1-api-environment-presence-v1",
        "variables": variables,
        "v9_live_ready": variables["DASHSCOPE_API_KEY"]["status"] == "PRESENT",
        "secret_values_read_or_printed": False,
    }


if __name__ == "__main__":
    print(json.dumps(status(), indent=2))
