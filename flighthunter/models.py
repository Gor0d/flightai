"""Modelos de domínio. Nenhum preço é inventado: campos desconhecidos ficam None."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from typing import Optional


@dataclass
class Segment:
    carrier: str                       # companhia de marketing (IATA)
    flight_number: str
    origin: str
    destination: str
    departure: str                     # ISO 8601 local
    arrival: str
    duration_minutes: Optional[int] = None
    operating_carrier: Optional[str] = None
    aircraft: Optional[str] = None

    @classmethod
    def from_dict(cls, d: dict) -> "Segment":
        return cls(**d)


@dataclass
class SearchQuery:
    origin: str
    destination: str
    outbound_date: date
    return_date: date
    adults: int = 1
    cabin: str = "economy"
    currency: str = "BRL"
    nonstop_only: bool = False


@dataclass
class FlightOffer:
    provider: str
    airline: str                              # companhias de marketing (ex.: "LATAM" ou "GOL, Azul")
    operating_airline: Optional[str]
    departure_airport: str
    arrival_airport: str
    outbound_date: date
    return_date: date
    outbound_segments: list[Segment]
    return_segments: list[Segment]            # [] = provedor não retornou detalhe da volta
    outbound_stops: Optional[int]
    return_stops: Optional[int]
    outbound_duration_minutes: Optional[int]
    return_duration_minutes: Optional[int]
    total_price: float                        # total para todos os passageiros, ida+volta
    taxes: Optional[float]                    # None = não informado pelo provedor
    currency: str = "BRL"
    passengers: int = 1
    cabin: str = "economy"
    base_price: Optional[float] = None
    booking_url: Optional[str] = None
    provider_offer_id: Optional[str] = None
    return_details_known: bool = True
    retrieved_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))

    # ---- derivados -------------------------------------------------------
    @property
    def price_per_person(self) -> float:
        return round(self.total_price / max(self.passengers, 1), 2)

    @property
    def total_stops(self) -> Optional[int]:
        if self.outbound_stops is None:
            return None
        # se a volta é desconhecida, considera só a ida (ver return_details_known)
        return self.outbound_stops + (self.return_stops or 0)

    @property
    def is_direct(self) -> bool:
        return self.total_stops == 0

    @property
    def total_duration_minutes(self) -> Optional[int]:
        if self.outbound_duration_minutes is None:
            return None
        return self.outbound_duration_minutes + (self.return_duration_minutes or 0)

    @property
    def fingerprint(self) -> str:
        """Identidade estável da oferta (sem preço) para histórico/deduplicação."""
        def key(segs: list[Segment]) -> list:
            return [(s.carrier, s.flight_number, s.departure) for s in segs]
        raw = json.dumps([self.provider, str(self.outbound_date), str(self.return_date),
                          key(self.outbound_segments), key(self.return_segments),
                          self.provider_offer_id if not self.outbound_segments else None])
        return hashlib.sha1(raw.encode()).hexdigest()[:16]

    # ---- serialização ----------------------------------------------------
    def to_dict(self) -> dict:
        d = asdict(self)
        d["outbound_date"] = self.outbound_date.isoformat()
        d["return_date"] = self.return_date.isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "FlightOffer":
        d = dict(d)
        d["outbound_date"] = date.fromisoformat(d["outbound_date"])
        d["return_date"] = date.fromisoformat(d["return_date"])
        d["outbound_segments"] = [Segment.from_dict(s) for s in d["outbound_segments"]]
        d["return_segments"] = [Segment.from_dict(s) for s in d["return_segments"]]
        return cls(**d)
