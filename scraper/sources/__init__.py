"""Source adapters. Each module exposes fetch(session) -> list[dict] matching jobs.json schema."""
from . import (
    liu, varbi, umu, jobbnorge, ku, aalto, academictransfer,
    euraxess, academics, jobsac_uk, phdgermany,
)

ALL_SOURCES = [
    liu, varbi, umu, jobbnorge, ku, aalto, academictransfer,
    euraxess, academics, jobsac_uk, phdgermany,
]
