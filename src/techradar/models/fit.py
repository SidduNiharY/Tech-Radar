"""VRAM and resource fit estimation for local models."""

from typing import Literal

from pydantic import BaseModel, Field


class ModelVramEstimate(BaseModel):
    """VRAM fit estimation and GPU layer offload recommendation."""

    params_b: float = Field(..., description="Parameter count in billions (e.g. 7.0 for 7B)")
    quant_bits: int = Field(..., description="Quantization bit depth (e.g. 4, 8, 16)")
    context_len: int = Field(..., description="Context window length in tokens")
    available_vram_mb: int = Field(..., description="Available GPU VRAM in megabytes")
    weight_vram_mb: int = Field(..., description="VRAM required for model weights in megabytes")
    kv_cache_vram_mb: int = Field(..., description="VRAM required for KV cache in megabytes")
    total_vram_mb: int = Field(..., description="Total required VRAM in megabytes")
    fits_in_vram: bool = Field(
        ..., description="Whether model and context fit within available VRAM"
    )
    recommended_gpu_layers: int = Field(
        ..., description="Recommended number of layers to offload to GPU"
    )
    headroom_mb: int = Field(..., description="Headroom in MB (available - total required)")


def kv_estimate(ctx: int) -> int:
    """Return conservative KV cache memory footprint in bytes.

    Uses the conservative rule: ctx * 40 * 1024 bytes.
    For ctx=8192, this yields 335,544,320 bytes (~320 MB).
    """
    if ctx < 0:
        raise ValueError("Context length cannot be negative")
    return ctx * 40 * 1024


def estimate_fit(
    model_bytes: int,
    ctx: int = 8192,
    vram_bytes: int = 6 * 2**30,
    headroom: int = 700 * 2**20,
) -> Literal["fits", "split", "mostly_ram"]:
    """Estimate whether a model fits in VRAM, splits across GPU/RAM, or resides mostly in RAM.

    - "fits": model_bytes + kv_cache + headroom <= vram_bytes
    - "split": model_bytes alone <= 2 * vram_bytes
    - "mostly_ram": otherwise
    """
    if model_bytes < 0 or ctx < 0 or vram_bytes < 0 or headroom < 0:
        raise ValueError("Memory parameters must be non-negative")

    kv = kv_estimate(ctx)
    if model_bytes + kv + headroom <= vram_bytes:
        return "fits"
    if model_bytes <= 2 * vram_bytes:
        return "split"
    return "mostly_ram"


def estimate_vram_and_fit(
    params_b: float,
    quant_bits: int,
    context_len: int,
    available_vram_mb: int,
    *,
    total_layers: int = 33,
) -> ModelVramEstimate:
    """Calculate required VRAM for weights + KV cache and evaluate GPU fit.

    Args:
        params_b: Parameter count in billions (e.g. 4.0, 7.0, 14.0).
        quant_bits: Quantization bit depth (e.g. 4, 8, 16).
        context_len: Target context length in tokens.
        available_vram_mb: Total available GPU VRAM in megabytes.
        total_layers: Total transformer layers in the model (default 33 for typical 7B/8B).

    Returns:
        ModelVramEstimate with calculated footprint, fit boolean, recommended GPU layers,
        and headroom in MB.
    """
    if params_b < 0:
        raise ValueError("params_b must be non-negative")
    if quant_bits <= 0:
        raise ValueError("quant_bits must be positive")
    if context_len < 0:
        raise ValueError("context_len must be non-negative")
    if available_vram_mb < 0:
        raise ValueError("available_vram_mb must be non-negative")
    if total_layers <= 0:
        raise ValueError("total_layers must be positive")

    # Weights calculation: params * 10^9 * (quant_bits / 8) bytes -> MB
    weight_bytes = (params_b * 1_000_000_000 * quant_bits) / 8.0
    weight_vram_mb = int(round(weight_bytes / (1024 * 1024)))

    # KV cache calculation in MB
    kv_bytes = kv_estimate(context_len)
    kv_cache_vram_mb = int(round(kv_bytes / (1024 * 1024)))

    total_vram_mb = weight_vram_mb + kv_cache_vram_mb
    fits_in_vram = total_vram_mb <= available_vram_mb
    headroom_mb = available_vram_mb - total_vram_mb

    if fits_in_vram:
        recommended_gpu_layers = total_layers
    else:
        # If KV cache doesn't fit, 0 layers on GPU
        vram_for_weights = max(0, available_vram_mb - kv_cache_vram_mb)
        if weight_vram_mb > 0 and vram_for_weights > 0:
            fraction = min(1.0, vram_for_weights / weight_vram_mb)
            recommended_gpu_layers = int(total_layers * fraction)
        else:
            recommended_gpu_layers = 0

    return ModelVramEstimate(
        params_b=params_b,
        quant_bits=quant_bits,
        context_len=context_len,
        available_vram_mb=available_vram_mb,
        weight_vram_mb=weight_vram_mb,
        kv_cache_vram_mb=kv_cache_vram_mb,
        total_vram_mb=total_vram_mb,
        fits_in_vram=fits_in_vram,
        recommended_gpu_layers=recommended_gpu_layers,
        headroom_mb=headroom_mb,
    )
