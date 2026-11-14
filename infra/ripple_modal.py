"""Ripple BF16 on Modal; CPU-only weight staging precedes GPU serving.

    modal run infra/ripple_modal.py::download
    modal deploy infra/ripple_modal.py

Create ripple-vllm-key with VLLM_API_KEY before deployment. To download with
an existing huggingface Secret (HF_TOKEN), set RIPPLE_USE_HF_SECRET=1 locally.
If B200 capacity is unavailable, deploy with RIPPLE_MODAL_GPU=H200:2.
GPU-only list rates: B200 $6.2496/hour; two H200s $9.0792/hour.
Each container scales to zero after 900 idle seconds; at most two may run.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import modal

app = modal.App("ripple-vllm")
download_app = modal.App("ripple-weight-stage")
MODEL = "ricursiveAI/Ripple-65B-Preview"
REVISION = "b172323ffd63e62de9ce1ba3830dfffe493c7671"
MODEL_DIR = "/models/ripple-bf16"
GPU = os.environ.get("RIPPLE_MODAL_GPU", "B200")
TP = 2 if GPU == "H200:2" else 1
weights = modal.Volume.from_name("ripple-bf16-weights", create_if_missing=True)

# This lightweight image never allocates a GPU. Pin the checkpoint revision so
# repeated deployments reuse exactly the same cached weights.
download_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("huggingface_hub==0.36.0", "hf_transfer==0.1.9")
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
)
download_secrets = (
    [modal.Secret.from_name("huggingface", required_keys=["HF_TOKEN"])]
    if os.environ.get("RIPPLE_USE_HF_SECRET") == "1"
    else []
)


@download_app.function(
    image=download_image,
    cpu=8,
    memory=16384,
    volumes={"/models": weights},
    secrets=download_secrets,
    timeout=7200,
    max_containers=1,
)
def download():
    import time

    from huggingface_hub import snapshot_download
    from huggingface_hub.errors import HfHubHTTPError

    started = time.monotonic()
    marker = Path(MODEL_DIR) / ".download-complete"
    if marker.exists() and marker.read_text().strip() == REVISION:
        print(f"Weights already staged at {REVISION}")
        return
    try:
        snapshot_download(
            MODEL,
            revision=REVISION,
            local_dir=MODEL_DIR,
            max_workers=8,
            ignore_patterns=["*.bin", "*.pt", "*.pth", "original/*"],
        )
    except HfHubHTTPError as exc:
        if exc.response is not None and exc.response.status_code == 429:
            print("HUGGING_FACE_RATE_LIMITED: supply huggingface Secret and rerun with RIPPLE_USE_HF_SECRET=1", flush=True)
        raise
    marker.write_text(REVISION + "\n")
    weights.commit()
    size = sum(p.stat().st_size for p in Path(MODEL_DIR).glob("*.safetensors"))
    print(f"Weights staged: {size} bytes, {time.monotonic() - started:.1f}s")


# The build fails before deployment if the nightly predates native Ripple.
serve_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "vllm", "hf_transfer",
        extra_options="--pre",
        extra_index_url="https://wheels.vllm.ai/nightly",
    )
    .run_commands(
        "python3 -c 'from vllm.model_executor.models import ModelRegistry; "
        "assert \"RicursiveForCausalLM\" in ModelRegistry.get_supported_archs(), "
        "\"vLLM image lacks native Ripple support\"; print(\"Native Ripple registry assertion OK\")'"
    )
    .env({"HF_HUB_OFFLINE": "1", "HF_HUB_DISABLE_TELEMETRY": "1"})
)


@app.function(
    image=serve_image,
    gpu=GPU,
    cpu=8,
    memory=196608,
    volumes={"/models": weights},
    secrets=[modal.Secret.from_name("ripple-vllm-key", required_keys=["VLLM_API_KEY"])],
    scaledown_window=900,
    max_containers=2,
    timeout=3600,
)
@modal.concurrent(max_inputs=64)
@modal.web_server(8000, startup_timeout=2400)
def serve():
    marker = Path(MODEL_DIR) / ".download-complete"
    if not marker.exists() or marker.read_text().strip() != REVISION:
        raise RuntimeError("Stage weights first: modal run infra/ripple_modal.py::download")
    # vLLM reads VLLM_API_KEY directly; keeping it out of argv also avoids
    # accidental disclosure in process listings and server startup logs.
    subprocess.Popen(
        [
            "vllm", "serve", MODEL_DIR,
            "--host", "0.0.0.0", "--port", "8000",
            "--served-model-name", "ripple",
            "--dtype", "bfloat16",
            "--tensor-parallel-size", str(TP),
            "--max-model-len", "65536",
            "--enable-prefix-caching",
            "--reasoning-parser", "ripple",
            "--gpu-memory-utilization", "0.92",
        ]
    )
