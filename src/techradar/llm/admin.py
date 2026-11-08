"""Models administration and VRAM fit estimation for TechRadar Brain."""

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

KNOWN_MODEL_SPECS: dict[str, dict[str, Any]] = {
    "qwen3.5:4b": {"vram_gb": 3.3, "quant": "q4_k_m"},
    "gemma4:e2b-it-qat": {"vram_gb": 4.3, "quant": "qat"},
    "gemma4:12b-it-qat": {"vram_gb": 7.2, "quant": "qat"},
    "bge-m3": {"vram_gb": 1.2, "quant": "fp16"},
    "gemma4:e4b-it-qat": {"vram_gb": 6.1, "quant": "qat"},
}


class ModelSpec(BaseModel):
    """Specification of a configured model and its resource profile."""

    name: str
    family: str
    context_limit: int
    vram_gb: float
    quant: str
    role: str


class hybridmethod:
    """Descriptor enabling a method to be called on either class or instance."""

    def __init__(self, func: Callable[..., Any]) -> None:
        self.func = func

    def __get__(self, instance: Any, owner: Any) -> Callable[..., Any]:
        if instance is None:
            return lambda *args, **kwargs: self.func(owner(), *args, **kwargs)
        return lambda *args, **kwargs: self.func(instance, *args, **kwargs)


def _default_roles_path() -> Path:
    """Locate default infra/models/roles.yaml path."""
    repo_root = Path(__file__).resolve().parents[3]
    candidate = repo_root / "infra" / "models" / "roles.yaml"
    if candidate.is_file():
        return candidate
    local_path = Path("infra/models/roles.yaml")
    if local_path.is_file():
        return local_path
    return candidate


class ModelsAdmin:
    """Admin manager for local LLM specifications and VRAM fit estimation."""

    def __init__(self, config_path: Path | None = None) -> None:
        self.config_path = config_path

    @classmethod
    def _resolve_model_vram(cls, name_or_role: str, configured: list[ModelSpec]) -> float:
        """Resolve expected VRAM footprint in GB for a given model tag or role."""
        # 1. Match by role name
        for spec in configured:
            if spec.role.lower() == name_or_role.lower():
                return spec.vram_gb

        # 2. Match by model tag/name
        for spec in configured:
            if spec.name.lower() == name_or_role.lower():
                return spec.vram_gb

        # 3. Match known catalog
        if name_or_role in KNOWN_MODEL_SPECS:
            return float(KNOWN_MODEL_SPECS[name_or_role]["vram_gb"])

        # 4. Infer parameter size from tag (e.g. :8b -> 8.0 GB)
        match = re.search(r"(\d+(\.\d+)?)b", name_or_role.lower())
        if match:
            return float(match.group(1))

        # 5. Default fallback
        return 4.0

    @hybridmethod
    def list_configured_models(self, config_path: Path | None = None) -> list[ModelSpec]:
        """Parse infra/models/roles.yaml and return specifications for all roles."""
        path = config_path or self.config_path or _default_roles_path()
        if not path.is_file():
            raise FileNotFoundError(f"Roles configuration not found at: {path}")

        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"Roles configuration must be a YAML mapping, got: {type(raw)}")

        specs: list[ModelSpec] = []
        for role, conf in raw.items():
            if not isinstance(conf, dict):
                continue

            tag = str(conf.get("ollama_tag") or conf.get("name") or "")
            family = str(conf.get("family") or "unknown")
            context_limit = int(conf.get("num_ctx") or conf.get("context_limit") or 8192)

            default_vram = float(KNOWN_MODEL_SPECS.get(tag, {}).get("vram_gb", 4.0))
            vram_gb = float(conf.get("vram_gb", default_vram))

            default_quant = str(
                KNOWN_MODEL_SPECS.get(tag, {}).get("quant", "qat" if "qat" in tag else "q4_k_m")
            )
            quant = str(conf.get("quant", default_quant))

            specs.append(
                ModelSpec(
                    name=tag,
                    family=family,
                    context_limit=context_limit,
                    vram_gb=vram_gb,
                    quant=quant,
                    role=str(role),
                )
            )

        return specs

    @hybridmethod
    def estimate_vram_fit(
        self,
        total_vram_gb: float,
        model_names: list[str],
        config_path: Path | None = None,
    ) -> dict[str, Any]:
        """Evaluate whether requested models fit concurrently within available VRAM budget."""
        configured = self.list_configured_models(config_path)
        breakdown: dict[str, float] = {}
        total_required = 0.0

        for name in model_names:
            vram = self._resolve_model_vram(name, configured)
            breakdown[name] = vram
            total_required += vram

        fits = total_required <= total_vram_gb
        overflow = not fits
        overflow_gb = max(0.0, total_required - total_vram_gb)
        remaining_vram_gb = max(0.0, total_vram_gb - total_required)

        return {
            "fits": fits,
            "overflow": overflow,
            "total_vram_gb": total_vram_gb,
            "required_vram_gb": round(total_required, 2),
            "total_required_gb": round(total_required, 2),
            "remaining_vram_gb": round(remaining_vram_gb, 2),
            "overflow_gb": round(overflow_gb, 2),
            "model_vram": breakdown,
            "models": model_names,
            "model_names": model_names,
        }
