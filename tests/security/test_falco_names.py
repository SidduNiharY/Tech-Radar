"""Falco rules must match the container names Compose really creates.

Every TechRadar Falco rule matches `container.name startswith "techradar-..."`.
Compose names containers `<project>-<service>-<n>`, and without a `name:` the
project is the folder name, so the containers were `techradarbrain-bot-1`
and no rule could ever fire. compose.yaml pins the project name.
"""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def compose() -> dict:
    return yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))


def test_compose_pins_the_project_name():
    assert compose().get("name") == "techradar"


def test_every_falco_service_prefix_names_a_real_container():
    data = compose()
    containers = [f"{data.get('name')}-{svc}-1" for svc in data["services"]]
    text = "\n".join(
        (ROOT / "infra/falco" / f).read_text(encoding="utf-8")
        for f in ["techradar_rules.yaml", "generated_lists.yaml"]
    )
    prefixes = set(re.findall(r'container\.name startswith "([^"]+)"', text))
    assert "techradar-" in prefixes
    # Services planned for later phases have no container yet.
    later = {"jarvis", "api", "voice-worker", "changedetection", "searxng", "zap"}
    for prefix in prefixes:
        svc = prefix.removeprefix("techradar-")
        if svc in later:
            continue
        assert any(c.startswith(prefix) for c in containers), prefix


def test_scanned_images_use_the_project_name():
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    images = re.search(r"^IMAGES := (.+)$", makefile, re.MULTILINE).group(1).split()
    assert images and all(i.startswith("techradar-") for i in images), images
