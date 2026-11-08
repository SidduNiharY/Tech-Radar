from pathlib import Path

import pytest
from pydantic import ValidationError

from techradar.llm.roles import Role, RoleConfigError, load_roles


def test_load_roles_repo_file_ok() -> None:
    roles = load_roles(Path("infra/models/roles.yaml"), allow_cloud=False)
    assert roles[Role.WORKER].family != roles[Role.CHECKER].family
    assert len(roles) == 5
    assert Role.WORKER in roles
    assert Role.CHECKER in roles
    assert Role.NIGHT in roles
    assert Role.EMBED in roles
    assert Role.VISION in roles
    assert roles[Role.WORKER].ollama_tag == "qwen3.5:4b"
    assert roles[Role.CHECKER].family == "gemma"
    assert roles[Role.WORKER].provider == "ollama"


def test_same_family_worker_checker_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        """
worker:  {ollama_tag: "qwen3.5:4b", family: qwen, num_ctx: 8192, think: false}
checker: {ollama_tag: "qwen3.5:7b", family: qwen, num_ctx: 8192, think: false}
night:   {ollama_tag: "gemma4:12b", family: gemma, num_ctx: 8192, think: false}
embed:   {ollama_tag: "bge-m3",     family: bge,   num_ctx: 8192, think: false}
vision:  {ollama_tag: "qwen3.5:4b", family: qwen,  num_ctx: 8192, think: false}
"""
    )
    with pytest.raises(RoleConfigError, match="family"):
        load_roles(bad, allow_cloud=False)


def test_missing_role_rejected(tmp_path: Path) -> None:
    no_vision = tmp_path / "no_vision.yaml"
    no_vision.write_text(
        """
worker:  {ollama_tag: "qwen3.5:4b",        family: qwen,  num_ctx: 8192, think: false}
checker: {ollama_tag: "gemma4:e2b-it-qat", family: gemma, num_ctx: 8192, think: false}
night:   {ollama_tag: "gemma4:12b-it-qat", family: gemma, num_ctx: 8192, think: false}
embed:   {ollama_tag: "bge-m3",            family: bge,   num_ctx: 8192, think: false}
"""
    )
    with pytest.raises(RoleConfigError, match="missing"):
        load_roles(no_vision, allow_cloud=False)


def test_bad_tag_rejected(tmp_path: Path) -> None:
    bad_tag = tmp_path / "bad_tag.yaml"
    bad_tag.write_text(
        """
worker:  {ollama_tag: "qwen3.5:4b; rm -rf /", family: qwen,  num_ctx: 8192, think: false}
checker: {ollama_tag: "gemma4:e2b-it-qat",    family: gemma, num_ctx: 8192, think: false}
night:   {ollama_tag: "gemma4:12b-it-qat",    family: gemma, num_ctx: 8192, think: false}
embed:   {ollama_tag: "bge-m3",               family: bge,   num_ctx: 8192, think: false}
vision:  {ollama_tag: "qwen3.5:4b",           family: qwen,  num_ctx: 8192, think: false}
"""
    )
    with pytest.raises((RoleConfigError, ValidationError)):
        load_roles(bad_tag, allow_cloud=False)


def test_cloud_provider_rejected_when_not_allowed(tmp_path: Path) -> None:
    cloud = tmp_path / "cloud.yaml"
    cloud.write_text(
        """
worker:  {ollama_tag: "qwen3.5:4b",        family: qwen,  num_ctx: 8192, think: false,
          provider: "openai"}
checker: {ollama_tag: "gemma4:e2b-it-qat", family: gemma, num_ctx: 8192, think: false}
night:   {ollama_tag: "gemma4:12b-it-qat", family: gemma, num_ctx: 8192, think: false}
embed:   {ollama_tag: "bge-m3",            family: bge,   num_ctx: 8192, think: false}
vision:  {ollama_tag: "qwen3.5:4b",        family: qwen,  num_ctx: 8192, think: false}
"""
    )
    with pytest.raises(RoleConfigError, match="provider"):
        load_roles(cloud, allow_cloud=False)


def test_num_ctx_bounds_rejected(tmp_path: Path) -> None:
    bad_ctx = tmp_path / "bad_ctx.yaml"
    bad_ctx.write_text(
        """
worker:  {ollama_tag: "qwen3.5:4b",        family: qwen,  num_ctx: 512,  think: false}
checker: {ollama_tag: "gemma4:e2b-it-qat", family: gemma, num_ctx: 8192, think: false}
night:   {ollama_tag: "gemma4:12b-it-qat", family: gemma, num_ctx: 8192, think: false}
embed:   {ollama_tag: "bge-m3",            family: bge,   num_ctx: 8192, think: false}
vision:  {ollama_tag: "qwen3.5:4b",        family: qwen,  num_ctx: 8192, think: false}
"""
    )
    with pytest.raises(ValidationError):
        load_roles(bad_ctx, allow_cloud=False)
