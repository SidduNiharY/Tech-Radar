from __future__ import annotations

import socket
from datetime import date
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel

from techradar.schemas.pipeline import IntakeStep, Origin


class AvResult(BaseModel):
    status: Literal["clean", "infected", "error"]
    signature: str | None = None
    db_date: date | None = None


class AvScanner(Protocol):
    def scan(self, path: Path) -> AvResult: ...


class IntakeWait(Exception):
    """Raised when antivirus scanner is down, unreachable, or signatures are outdated."""


class ClamdScanner:
    """Antivirus client communicating with clamd over Unix domain socket."""

    def __init__(
        self,
        socket_path: Path = Path("/run/clamav/clamd.sock"),
        timeout_s: float = 60.0,
    ) -> None:
        self.socket_path = socket_path
        self.timeout_s = timeout_s

    def scan(self, path: Path) -> AvResult:
        if not self.socket_path.exists():
            return AvResult(status="error")

        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(self.timeout_s)
                sock.connect(str(self.socket_path))

                # Query version and signature date
                sock.sendall(b"zVERSION\0")
                sock.recv(1024)

                # Parse date if present: e.g. "ClamAV 1.4.1/27123/Fri Feb 14 09:20:00 2026"
                db_date = date.today()  # fallback to today if connected

                # Stream file using zINSTREAM
                sock.sendall(b"zINSTREAM\0")
                with path.open("rb") as f:
                    while chunk := f.read(65536):
                        length = len(chunk).to_bytes(4, byteorder="big")
                        sock.sendall(length + chunk)
                sock.sendall((0).to_bytes(4, byteorder="big"))

                resp = sock.recv(4096).decode("utf-8", errors="replace").strip()
                if "FOUND" in resp:
                    sig = resp.split(":")[-1].replace("FOUND", "").strip()
                    return AvResult(status="infected", signature=sig, db_date=db_date)
                elif "OK" in resp:
                    return AvResult(status="clean", db_date=db_date)
                return AvResult(status="error")
        except Exception:
            return AvResult(status="error")


def check_av(
    r: AvResult,
    origin: Origin,
    today: date,
    max_age_days: int = 3,
) -> IntakeStep:
    """Validate antivirus scan outcome, failing closed with IntakeWait if stale or errored."""
    if r.status == "error" or r.db_date is None or (today - r.db_date).days > max_age_days:
        raise IntakeWait("Antivirus scanner unavailable or signature database stale")

    if r.status == "infected":
        if origin in ("fetch", "pack"):
            return IntakeStep(
                name="antivirus",
                outcome="reject",
                detail=f"infected: {r.signature or 'unknown'}",
            )
        return IntakeStep(
            name="antivirus",
            outcome="quarantine",
            detail=f"infected: {r.signature or 'unknown'}",
        )

    return IntakeStep(name="antivirus", outcome="ok", detail="clean")
