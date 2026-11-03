from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Optional

from ..http import HttpClient
from ..models import FlightOffer, SearchQuery


def parse_iso_duration(s: Optional[str]) -> Optional[int]:
    """'PT2H30M' / 'P0DT2H30M' -> minutos."""
    if not s:
        return None
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?", s)
    if not m:
        return None
    d, h, mi = (int(x or 0) for x in m.groups())
    return d * 1440 + h * 60 + mi


class Provider(ABC):
    name: str = ""

    def __init__(self, http: HttpClient | None = None):
        self.http = http or HttpClient()
        self.calls = 0  # chamadas HTTP feitas (para o teto por execução)

    @abstractmethod
    def is_configured(self) -> bool: ...

    @abstractmethod
    def search(self, q: SearchQuery) -> list[FlightOffer]: ...
