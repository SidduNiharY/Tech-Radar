from __future__ import annotations

from pathlib import Path

from techradar.library.starter_packs import StarterPackItem, StarterPackManager


def test_starter_pack_load_from_repo_config() -> None:
    config_path = Path("infra/sources/exam_packs.yaml")
    assert config_path.exists()

    manager = StarterPackManager(config_path=config_path)
    packs = manager.items
    assert len(packs) == 4

    pack_ids = {p.id for p in packs}
    assert "ncert_polity_class_11" in pack_ids
    assert "nios_economics" in pack_ids
    assert "rbi_annual_report" in pack_ids
    assert "unapproved_sample" in pack_ids


def test_only_approved_packs_retrieved() -> None:
    manager = StarterPackManager(config_path=Path("infra/sources/exam_packs.yaml"))
    approved = manager.get_approved_packs()

    # Exactly 3 approved packs
    assert len(approved) == 3
    for pack in approved:
        assert pack.approved is True
        assert pack.id != "unapproved_sample"

    # Confirm unapproved item exists in raw items but not in approved
    unapproved = [p for p in manager.items if not p.approved]
    assert len(unapproved) == 1
    assert unapproved[0].id == "unapproved_sample"


def test_validate_pack_url_allowlisted(tmp_path: Path) -> None:
    allowlist_file = tmp_path / "allowlist.txt"
    allowlist_file.write_text("ncert.nic.in\nnios.ac.in\nrbi.org.in\n", encoding="utf-8")

    # Allowlisted official domains with HTTPS pass
    assert StarterPackManager.validate_pack_url(
        "https://ncert.nic.in/textbook/pdf/keps2dd.zip",
        allowlist_path=allowlist_file,
    )
    assert StarterPackManager.validate_pack_url(
        "https://nios.ac.in/media/documents/srsec318new/318_Economy_Eng/ch1.pdf",
        allowlist_path=allowlist_file,
    )
    assert StarterPackManager.validate_pack_url(
        "https://rbi.org.in/Scripts/AnnualReportPublications.aspx",
        allowlist_path=allowlist_file,
    )


def test_validate_pack_url_rejects_unallowlisted_and_file_sharing(tmp_path: Path) -> None:
    allowlist_file = tmp_path / "allowlist.txt"
    allowlist_file.write_text("ncert.nic.in\n", encoding="utf-8")

    # File sharing and piracy domains rejected
    assert not StarterPackManager.validate_pack_url(
        "https://mega.nz/file/sample#key",
        allowlist_path=allowlist_file,
    )
    assert not StarterPackManager.validate_pack_url(
        "https://mediafire.com/file/book.pdf",
        allowlist_path=allowlist_file,
    )
    assert not StarterPackManager.validate_pack_url(
        "https://drive.google.com/file/d/xyz",
        allowlist_path=allowlist_file,
    )
    assert not StarterPackManager.validate_pack_url(
        "https://piratebay.org/study_material.zip",
        allowlist_path=allowlist_file,
    )
    assert not StarterPackManager.validate_pack_url(
        "https://example.com/unapproved.pdf",
        allowlist_path=allowlist_file,
    )


def test_validate_pack_url_rejects_non_https(tmp_path: Path) -> None:
    allowlist_file = tmp_path / "allowlist.txt"
    allowlist_file.write_text("ncert.nic.in\n", encoding="utf-8")

    # Plain HTTP rejected even for allowlisted domain
    assert not StarterPackManager.validate_pack_url(
        "http://ncert.nic.in/textbook/pdf/keps2dd.zip",
        allowlist_path=allowlist_file,
    )


def test_validate_pack_url_rejects_suspicious_urls(tmp_path: Path) -> None:
    allowlist_file = tmp_path / "allowlist.txt"
    allowlist_file.write_text("ncert.nic.in\n", encoding="utf-8")

    # Subdomain hijacking or spoofing attempt
    assert not StarterPackManager.validate_pack_url(
        "https://ncert.nic.in.evil.com/book.pdf",
        allowlist_path=allowlist_file,
    )
    # Userinfo in URL
    assert not StarterPackManager.validate_pack_url(
        "https://user:pass@ncert.nic.in/book.pdf",
        allowlist_path=allowlist_file,
    )
    # Non-standard port
    assert not StarterPackManager.validate_pack_url(
        "https://ncert.nic.in:8080/book.pdf",
        allowlist_path=allowlist_file,
    )


def test_validate_download_size_limit() -> None:
    # Under or equal to 200MB (200_000_000 bytes)
    assert StarterPackManager.validate_download_size(0)
    assert StarterPackManager.validate_download_size(50_000_000)
    assert StarterPackManager.validate_download_size(200_000_000)

    # Exceeding 200MB limit
    assert not StarterPackManager.validate_download_size(200_000_001)
    assert not StarterPackManager.validate_download_size(300_000_000)

    # Negative sizes invalid
    assert not StarterPackManager.validate_download_size(-1)


def test_starter_pack_custom_max_bytes() -> None:
    custom_item = StarterPackItem(
        id="custom_pack",
        title="Custom Pack",
        exam="UPSC",
        url="https://ncert.nic.in/custom.pdf",
        approved=True,
        max_bytes=100_000_000,
    )
    assert custom_item.max_bytes == 100_000_000
    assert StarterPackManager.validate_download_size(50_000_000, custom_item.max_bytes)
    assert not StarterPackManager.validate_download_size(150_000_000, custom_item.max_bytes)
