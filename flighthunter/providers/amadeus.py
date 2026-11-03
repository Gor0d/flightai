"""Amadeus Self-Service — Flight Offers Search (GET /v2/shopping/flight-offers).

Atenção: o ambiente `test` devolve dados em cache/limitados e a cobertura de LCCs e das
brasileiras (GOL/Azul) é incompleta; use `production` para dados reais. Confirme na
documentação vigente da Amadeus a disponibilidade do portal Self-Service.
"""
from __future__ import annotations

from typing import Optional

from ..models import FlightOffer, SearchQuery, Segment
from .base import Provider, parse_iso_duration

HOSTS = {"test": "https://test.api.amadeus.com", "production": "https://api.amadeus.com"}


def _segs(itinerary: dict) -> list[Segment]:
    out = []
    for s in itinerary.get("segments", []):
        out.append(Segment(
            carrier=s["carrierCode"], flight_number=f'{s["carrierCode"]}{s["number"]}',
            origin=s["departure"]["iataCode"], destination=s["arrival"]["iataCode"],
            departure=s["departure"]["at"], arrival=s["arrival"]["at"],
            duration_minutes=parse_iso_duration(s.get("duration")),
            operating_carrier=(s.get("operating") or {}).get("carrierCode"),
            aircraft=(s.get("aircraft") or {}).get("code")))
    return out


class AmadeusProvider(Provider):
    name = "amadeus"

    def __init__(self, client_id: Optional[str], client_secret: Optional[str],
                 env: str = "production", http=None, max_results: int = 30):
        super().__init__(http)
        self.client_id, self.client_secret = client_id, client_secret
        self.host = HOSTS[env]
        self.max_results = max_results
        self._token: Optional[str] = None

    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def _auth(self) -> str:
        if not self._token:
            self.calls += 1
            r = self.http.request("POST", f"{self.host}/v1/security/oauth2/token", form={
                "grant_type": "client_credentials", "client_id": self.client_id,
                "client_secret": self.client_secret})
            self._token = r["access_token"]
        return self._token

    def search(self, q: SearchQuery) -> list[FlightOffer]:
        token = self._auth()
        self.calls += 1
        params = {
            "originLocationCode": q.origin, "destinationLocationCode": q.destination,
            "departureDate": q.outbound_date.isoformat(), "returnDate": q.return_date.isoformat(),
            "adults": q.adults, "travelClass": q.cabin.upper(), "currencyCode": q.currency,
            "max": self.max_results,
        }
        if q.nonstop_only:
            params["nonStop"] = "true"
        data = self.http.request("GET", f"{self.host}/v2/shopping/flight-offers",
                                 params=params, headers={"Authorization": f"Bearer {token}"})
        return [o for item in data.get("data", []) if (o := self._parse(item, q)) is not None]

    def _parse(self, item: dict, q: SearchQuery) -> Optional[FlightOffer]:
        its = item.get("itineraries", [])
        price = item.get("price", {})
        if len(its) < 2 or not price.get("grandTotal"):
            return None
        out, back = _segs(its[0]), _segs(its[1])
        base = float(price["base"]) if price.get("base") else None
        total = float(price["grandTotal"])
        marketing = list(dict.fromkeys(s.carrier for s in out + back))
        operating = list(dict.fromkeys((s.operating_carrier or s.carrier) for s in out + back))
        return FlightOffer(
            provider=self.name, airline=", ".join(marketing), operating_airline=", ".join(operating),
            departure_airport=q.origin, arrival_airport=q.destination,
            outbound_date=q.outbound_date, return_date=q.return_date,
            outbound_segments=out, return_segments=back,
            outbound_stops=len(out) - 1, return_stops=len(back) - 1,
            outbound_duration_minutes=parse_iso_duration(its[0].get("duration")),
            return_duration_minutes=parse_iso_duration(its[1].get("duration")),
            total_price=total, taxes=round(total - base, 2) if base is not None else None,
            base_price=base, currency=price.get("currency", q.currency), passengers=q.adults,
            cabin=q.cabin, provider_offer_id=item.get("id"))
