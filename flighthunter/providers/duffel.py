"""Duffel — POST /air/offer_requests?return_offers=true (Duffel-Version: v2).

Duffel é API de busca + emissão (NDC/GDS). A cobertura de companhias brasileiras depende do
que a Duffel tem contratado; pode retornar zero ofertas para BEL-BSB. Use o token de teste
(`duffel_test_...`) só para validar integração: o ambiente de teste retorna a companhia
fictícia "Duffel Airways", cujas ofertas NÃO são tarifas reais e são descartadas aqui.
"""
from __future__ import annotations

from typing import Optional

from ..models import FlightOffer, SearchQuery, Segment
from .base import Provider, parse_iso_duration

URL = "https://api.duffel.com/air/offer_requests"


def _segs(slice_: dict) -> list[Segment]:
    out = []
    for s in slice_.get("segments", []):
        mk, op = s.get("marketing_carrier") or {}, s.get("operating_carrier") or {}
        out.append(Segment(
            carrier=mk.get("iata_code", ""), flight_number=f'{mk.get("iata_code", "")}{s.get("marketing_carrier_flight_number", "")}',
            origin=s["origin"]["iata_code"], destination=s["destination"]["iata_code"],
            departure=s["departing_at"], arrival=s["arriving_at"],
            duration_minutes=parse_iso_duration(s.get("duration")),
            operating_carrier=op.get("iata_code"), aircraft=(s.get("aircraft") or {}).get("name")))
    return out


class DuffelProvider(Provider):
    name = "duffel"

    def __init__(self, token: Optional[str], http=None):
        super().__init__(http)
        self.token = token

    def is_configured(self) -> bool:
        return bool(self.token)

    def search(self, q: SearchQuery) -> list[FlightOffer]:
        self.calls += 1
        body = {"data": {
            "slices": [
                {"origin": q.origin, "destination": q.destination, "departure_date": q.outbound_date.isoformat()},
                {"origin": q.destination, "destination": q.origin, "departure_date": q.return_date.isoformat()}],
            "passengers": [{"type": "adult"} for _ in range(q.adults)],
            "cabin_class": q.cabin,
            "max_connections": 0 if q.nonstop_only else 2}}
        data = self.http.request("POST", URL, params={"return_offers": "true", "supplier_timeout": 20000},
                                 json_body=body, headers={
                                     "Authorization": f"Bearer {self.token}", "Duffel-Version": "v2"})
        offers = (data.get("data") or {}).get("offers", [])
        return [o for item in offers if (o := self._parse(item, q)) is not None]

    def _parse(self, item: dict, q: SearchQuery) -> Optional[FlightOffer]:
        slices = item.get("slices", [])
        if len(slices) < 2 or not item.get("total_amount"):
            return None
        owner = item.get("owner") or {}
        if owner.get("name") == "Duffel Airways":
            return None  # companhia fictícia do sandbox
        out, back = _segs(slices[0]), _segs(slices[1])
        total = float(item["total_amount"])
        tax = float(item["tax_amount"]) if item.get("tax_amount") else None
        base = float(item["base_amount"]) if item.get("base_amount") else None
        operating = list(dict.fromkeys((s.operating_carrier or s.carrier) for s in out + back))
        return FlightOffer(
            provider=self.name, airline=owner.get("name") or ", ".join(dict.fromkeys(s.carrier for s in out + back)),
            operating_airline=", ".join(operating),
            departure_airport=q.origin, arrival_airport=q.destination,
            outbound_date=q.outbound_date, return_date=q.return_date,
            outbound_segments=out, return_segments=back,
            outbound_stops=len(out) - 1, return_stops=len(back) - 1,
            outbound_duration_minutes=parse_iso_duration(slices[0].get("duration")),
            return_duration_minutes=parse_iso_duration(slices[1].get("duration")),
            total_price=total, taxes=tax, base_price=base, currency=item.get("total_currency", q.currency),
            passengers=q.adults, cabin=q.cabin, provider_offer_id=item.get("id"))
