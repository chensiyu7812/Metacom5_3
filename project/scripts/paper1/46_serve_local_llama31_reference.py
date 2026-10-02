#!/usr/bin/env python3
"""Single-GPU streaming reference server for the frozen Llama-3.1-8B model.

This intentionally small aiohttp/Transformers stack is a versioned Paper-1
deployment candidate after NVIDIA retired the hosted model endpoint.  It is
not presented as an optimized serving system.  The server accepts only the
frozen model identity, deterministic generation, one request at a time, and
OpenAI-compatible streaming chat completions needed by the reference client.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import torch
import transformers
from aiohttp import web
from transformers import AutoModelForCausalLM, AutoTokenizer, TextIteratorStreamer

MODEL_ID = "meta/llama-3.1-8b-instruct"
MODEL_REVISION = "d10aef7999a2b5ba950ab3974312feeedbfe0b77"
SERVER_PROTOCOL = "paper1-local-llama31-transformers-aiohttp-reference-server-v1"
MODEL_ARTIFACT_IDENTITY_SHA256 = (
    "61ca4a878558de3dad5ce518ba4ec6619b7848babc6450ca90290087366df1a3"
)
CHAT_TEMPLATE_SHA256 = "b48c47f6443892716176eb200bf4ef108f64e06ca26ed0fa8ebc0a4b3992fcb2"
MODEL_FILE_SHA256 = {
    "config.json": "29e4c210b0d6ac178b16b2a255a568bdb23b581e50ca1ef6a6d071dd85704e6e",
    "generation_config.json": "189fb0c0d7fd8a527db217c0a60a0e013f0394cd8800f9697a666a9e75e5f7fd",
    "model-00001-of-00004.safetensors": "2b1879f356aed350030bb40eb45ad362c89d9891096f79a3ab323d3ba5607668",
    "model-00002-of-00004.safetensors": "09d433f650646834a83c580877bd60c6d1f88f7755305c12576b5c7058f9af15",
    "model-00003-of-00004.safetensors": "fc1cdddd6bfa91128d6e94ee73d0ce62bfcdb7af29e978ddcab30c66ae9ea7fa",
    "model-00004-of-00004.safetensors": "92ecfe1a2414458b4821ac8c13cf8cb70aed66b5eea8dc5ad9eeb4ff309d6d7b",
    "model.safetensors.index.json": "146776fce3f6db1103aa6f249e65ee5544c5923ce6f971b092eee79aa6e5d37b",
    "original/params.json": "b15b6b31b2043c0400b028ecc25c8946e21d76ac260e9ac6a357ed8727c8865f",
    "special_tokens_map.json": "6f38c73729248f6c127296386e3cdde96e254636cc58b4169d3fd32328d9a8ec",
    "tokenizer.json": "79e3e522635f3171300913bb421464a87de6222182a0570b9b2ccba2a964b2b4",
    "tokenizer_config.json": "24e8a6dc2547164b7002e3125f10b415105644fcf02bf9ad8b674c87b1eaaed6",
}


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8011)
    return parser.parse_args()


class ReferenceServer:
    def __init__(self, model_dir: Path) -> None:
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is required for the Paper-1 local reference server")
        self.model_dir = model_dir.resolve()
        for relative, expected in MODEL_FILE_SHA256.items():
            path = self.model_dir / relative
            if not path.is_file():
                raise RuntimeError(f"frozen model artifact file is missing: {relative}")
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != expected:
                raise RuntimeError(f"frozen model artifact hash mismatch: {relative}")
        self.loaded_at_monotonic = time.monotonic()
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_dir,
            local_files_only=True,
            use_fast=True,
        )
        if not isinstance(self.tokenizer.chat_template, str):
            raise RuntimeError("frozen tokenizer has no chat template")
        if hashlib.sha256(self.tokenizer.chat_template.encode()).hexdigest() != CHAT_TEMPLATE_SHA256:
            raise RuntimeError("frozen local chat-template hash mismatch")
        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_dir,
            local_files_only=True,
            dtype=torch.bfloat16,
        ).to("cuda:0")
        self.model.eval()
        # The mirrored config carries sampling-only defaults.  Greedy decoding
        # ignores them, but clearing them removes misleading warnings and makes
        # the effective deterministic surface explicit.
        self.model.generation_config.temperature = None
        self.model.generation_config.top_p = None
        self.lock = threading.Lock()

    async def health(self, _request: web.Request) -> web.Response:
        return web.json_response(
            {
                "status": "ready",
                "protocol": SERVER_PROTOCOL,
                "model": MODEL_ID,
                "revision": MODEL_REVISION,
                "model_artifact_identity_sha256": MODEL_ARTIFACT_IDENTITY_SHA256,
                "chat_template_sha256": CHAT_TEMPLATE_SHA256,
                "model_dir": str(self.model_dir),
                "torch": torch.__version__,
                "transformers": transformers.__version__,
                "cuda": torch.version.cuda,
                "gpu": torch.cuda.get_device_name(0),
                "dtype": "bfloat16",
                "concurrency": 1,
            }
        )

    async def chat_completions(self, request: web.Request) -> web.StreamResponse:
        try:
            payload = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)
        if payload.get("model") != MODEL_ID:
            return web.json_response({"error": "model identity mismatch"}, status=400)
        if payload.get("stream") is not True:
            return web.json_response({"error": "stream=true is required"}, status=400)
        if float(payload.get("temperature", 0)) != 0:
            return web.json_response({"error": "temperature=0 is required"}, status=400)
        messages = payload.get("messages")
        if not isinstance(messages, list) or not messages:
            return web.json_response({"error": "messages must be nonempty"}, status=400)
        max_new_tokens = int(payload.get("max_tokens", 0))
        if max_new_tokens not in {60, 256}:
            return web.json_response(
                {"error": "Paper-1 output limit must be 60 or 256"}, status=400
            )
        if not self.lock.acquire(blocking=False):
            return web.json_response({"error": "concurrency=1 busy"}, status=429)

        try:
            rendered = self.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
            encoded = self.tokenizer(rendered, return_tensors="pt", add_special_tokens=False)
            prompt_tokens = int(encoded["input_ids"].shape[-1])
            encoded = {key: value.to("cuda:0") for key, value in encoded.items()}
            streamer = TextIteratorStreamer(
                self.tokenizer,
                skip_prompt=True,
                skip_special_tokens=True,
                timeout=180.0,
            )
            holder: dict[str, Any] = {}

            def generate() -> None:
                try:
                    with torch.inference_mode():
                        holder["tokens"] = self.model.generate(
                            **encoded,
                            streamer=streamer,
                            max_new_tokens=max_new_tokens,
                            do_sample=False,
                            pad_token_id=self.tokenizer.eos_token_id,
                            eos_token_id=self.tokenizer.eos_token_id,
                            use_cache=True,
                        )
                except Exception as exc:  # make the stream terminate audibly
                    holder["error"] = exc
                    streamer.on_finalized_text("", stream_end=True)

            worker = threading.Thread(target=generate, daemon=True)
            worker.start()
            response = web.StreamResponse(
                status=200,
                headers={
                    "Content-Type": "text/event-stream",
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                    "X-Paper1-Server-Protocol": SERVER_PROTOCOL,
                },
            )
            await response.prepare(request)
            request_id = f"paper1-local-{uuid.uuid4().hex}"
            for piece in streamer:
                if not piece:
                    continue
                chunk = {
                    "id": request_id,
                    "object": "chat.completion.chunk",
                    "model": MODEL_ID,
                    "choices": [
                        {"index": 0, "delta": {"content": piece}, "finish_reason": None}
                    ],
                }
                await response.write(f"data: {json.dumps(chunk)}\n\n".encode())
            worker.join()
            if "error" in holder:
                error_chunk = {
                    "id": request_id,
                    "object": "chat.completion.chunk",
                    "model": MODEL_ID,
                    "error": type(holder["error"]).__name__,
                    "choices": [],
                }
                await response.write(f"data: {json.dumps(error_chunk)}\n\n".encode())
            else:
                generated = holder["tokens"]
                completion_tokens = int(generated.shape[-1]) - prompt_tokens
                finish_reason = (
                    "length" if completion_tokens >= max_new_tokens else "stop"
                )
                final_chunk = {
                    "id": request_id,
                    "object": "chat.completion.chunk",
                    "model": MODEL_ID,
                    "choices": [
                        {"index": 0, "delta": {}, "finish_reason": finish_reason}
                    ],
                    "usage": {
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": prompt_tokens + completion_tokens,
                    },
                }
                await response.write(f"data: {json.dumps(final_chunk)}\n\n".encode())
            await response.write(b"data: [DONE]\n\n")
            await response.write_eof()
            return response
        finally:
            self.lock.release()


def main() -> None:
    args = _args()
    server = ReferenceServer(args.model_dir)
    app = web.Application(client_max_size=8 * 1024 * 1024)
    app.router.add_get("/health", server.health)
    app.router.add_post("/v1/chat/completions", server.chat_completions)
    web.run_app(app, host=args.host, port=args.port, access_log=None)


if __name__ == "__main__":
    main()
