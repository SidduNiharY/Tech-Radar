"""Tests for VRAM fit estimation and resource bounds."""

import pytest

from techradar.models.fit import estimate_fit, estimate_vram_and_fit, kv_estimate


def test_kv_estimate() -> None:
    """Test conservative KV cache estimation formula."""
    # 8192 tokens * 40 bytes/token * 1024 = 335,544,320 bytes (~320 MB)
    assert kv_estimate(8192) == 335_544_320
    assert kv_estimate(4096) == 167_772_160
    assert kv_estimate(0) == 0

    with pytest.raises(ValueError, match="negative"):
        kv_estimate(-1)


def test_estimate_fit() -> None:
    """Test standard fit thresholds from Phase 10 specification."""
    gb = 2**30
    # 3.3 GB model fits in 6GB VRAM
    assert estimate_fit(int(3.3 * gb)) == "fits"
    # 7.2 GB model splits across GPU and RAM
    assert estimate_fit(int(7.2 * gb)) == "split"
    # 16 GB model is mostly in RAM on 6GB VRAM
    assert estimate_fit(int(16 * gb)) == "mostly_ram"


def test_estimate_fit_negative_inputs() -> None:
    """Test that negative memory parameters raise ValueError."""
    with pytest.raises(ValueError):
        estimate_fit(-100)


def test_estimate_vram_and_fit_fits() -> None:
    """Test a 4B model at 4-bit quant with 8192 context on 6GB VRAM."""
    est = estimate_vram_and_fit(
        params_b=4.0,
        quant_bits=4,
        context_len=8192,
        available_vram_mb=6144,
        total_layers=33,
    )
    assert est.fits_in_vram is True
    assert est.weight_vram_mb == 1907  # (4e9 * 0.5) / 1048576 = 1907.3 MB
    assert est.kv_cache_vram_mb == 320  # 335544320 / 1048576 = 320.0 MB
    assert est.total_vram_mb == 1907 + 320
    assert est.headroom_mb == 6144 - est.total_vram_mb
    assert est.recommended_gpu_layers == 33


def test_estimate_vram_and_fit_does_not_fit() -> None:
    """Test a 14B model at 8-bit quant with 8192 context on 6GB VRAM."""
    est = estimate_vram_and_fit(
        params_b=14.0,
        quant_bits=8,
        context_len=8192,
        available_vram_mb=6144,
        total_layers=33,
    )
    assert est.fits_in_vram is False
    assert est.headroom_mb < 0
    # Weights need ~13351 MB, available for weights is 6144 - 320 = 5824 MB
    assert est.recommended_gpu_layers < 33
    assert est.recommended_gpu_layers == int(33 * (5824 / est.weight_vram_mb))


def test_estimate_vram_and_fit_zero_available_vram() -> None:
    """Test behavior when no GPU VRAM is available (CPU only)."""
    est = estimate_vram_and_fit(
        params_b=7.0,
        quant_bits=4,
        context_len=4096,
        available_vram_mb=0,
        total_layers=32,
    )
    assert est.fits_in_vram is False
    assert est.recommended_gpu_layers == 0
    assert est.headroom_mb == -est.total_vram_mb


def test_estimate_vram_and_fit_validation() -> None:
    """Test input validations for estimate_vram_and_fit."""
    with pytest.raises(ValueError, match="params_b"):
        estimate_vram_and_fit(params_b=-1.0, quant_bits=4, context_len=2048, available_vram_mb=4096)

    with pytest.raises(ValueError, match="quant_bits"):
        estimate_vram_and_fit(params_b=7.0, quant_bits=0, context_len=2048, available_vram_mb=4096)

    with pytest.raises(ValueError, match="context_len"):
        estimate_vram_and_fit(params_b=7.0, quant_bits=4, context_len=-10, available_vram_mb=4096)

    with pytest.raises(ValueError, match="available_vram_mb"):
        estimate_vram_and_fit(params_b=7.0, quant_bits=4, context_len=2048, available_vram_mb=-100)
