"""SerpAPI — engine google_flights.

Prós: cobre as companhias brasileiras (LATAM, GOL, Azul) como o Google Flights.
Limite: a busca ida+volta retorna as opções de IDA com o preço TOTAL ida+volta; o detalhe
da volta exige uma 2ª chamada com `departure_token` (1 crédito cada). Por isso só buscamos
o detalhe para as N ofertas mais baratas (`return_details`). As demais ficam com
return_segments=[] e return_details_known=False — nada é estimado.
"""
from __future__ import annotations

from typing import Optional

from ..http import ProviderError
from ..models import FlightOffer, SearchQuery, Segment
from .base import Provider

URL = "https://serpapi.com/search.json"
TRAVEL_CLASS = {"economy": 1, "premium_economy": 2, "business": 3, "first": 4}


def _seg(f: dict) -> Segment:
    fn = (f.get("flight_number") or "").replace(" ", "")
    dep, arr = f["departure_airport"], f["arrival_airport"]
    code = fn[:2] if fn else ""
    return Segment(carrier=code or (f.get("airline") or ""), flight_number=fn,
                   origin=dep.get("id", ""), destination=arr.get("id", ""),
                   departure=dep.get("time", "").replace(" ", "T"),
                   arrival=arr.get("time", "").replace(" ", "T"),
                   duration_minutes=f.get("duration"), aircraft=f.get("airplane"))


def _airlines(group: list[dict]) -> str:
    seen: list[str] = []
    for f in group:
        a = f.get("airline")
        if a and a not in seen:
            seen.append(a)
    return ", ".join(seen)


class SerpApiProvider(Provider):
    name = "serpapi"

    def __init__(self, api_key: Optional[str], http=None, return_details: int = 2):
        super().__init__(http)
        self.api_key = api_key
        self.return_details = return_details

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _call(self, params: dict) -> dict:
        self.calls += 1
        data = self.http.request("GET", URL, params={**params, "api_key": self.api_key})
        if data.get("error"):
            if "hasn't returned any results" in data["error"]:
                return {}
            raise ProviderError(f"SerpAPI: {data['error']}")
        return data

    def search(self, q: SearchQuery) -> list[FlightOffer]:
        params = {
            "engine": "google_flights", "departure_id": q.origin, "arrival_id": q.destination,
            "outbound_date": q.outbound_date.isoformat(), "return_date": q.return_date.isoformat(),
            "type": 1, "adults": q.adults, "currency": q.currency, "hl": "pt-br", "gl": "br",
            "travel_class": TRAVEL_CLASS.get(q.cabin, 1),
        }
        if q.nonstop_only:
            params["stops"] = 1  # 1 = somente sem escalas
        data = self._call(params)
        groups = (data.get("best_flights") or []) + (data.get("other_flights") or [])
        pairs = [(o, g) for g in groups if (o := self._parse_outbound(g, q, data)) is not None]
        pairs.sort(key=lambda p: p[0].total_price)
        # detalhe da volta apenas para as mais baratas
        for o, g in pairs[: self.return_details]:
            if g.get("departure_token"):
                try:
                    self._fill_return(o, g["departure_token"], params)
                except ProviderError:
                    pass  # mantém sem detalhe da volta
        return [o for o, _ in pairs]

    def _parse_outbound(self, g: dict, q: SearchQuery, data: dict) -> Optional[FlightOffer]:
        flights = g.get("flights") or []
        price = g.get("price")
        if not flights or price is None:
            return None  # sem preço real => descarta, nunca estima
        segs = [_seg(f) for f in flights]
        link = (data.get("search_metadata") or {}).get("google_flights_url")
        return FlightOffer(
            provider=self.name, airline=_airlines(flights), operating_airline=None,
            departure_airport=q.origin, arrival_airport=q.destination,
            outbound_date=q.outbound_date, return_date=q.return_date,
            outbound_segments=segs, return_segments=[],
            outbound_stops=len(segs) - 1, return_stops=None,
            outbound_duration_minutes=g.get("total_duration"), return_duration_minutes=None,
            total_price=float(price), taxes=None, currency=q.currency, passengers=q.adults,
            cabin=q.cabin, booking_url=link, provider_offer_id=g.get("departure_token"),
            return_details_known=False,
        )

    def _fill_return(self, offer: FlightOffer, token: str, base_params: dict) -> None:
        data = self._call({**base_params, "departure_token": token})
        groups = (data.get("best_flights") or []) + (data.get("other_flights") or [])
        groups = [g for g in groups if g.get("flights") and g.get("price") is not None]
        if not groups:
            return
        g = min(groups, key=lambda x: x["price"])
        # com departure_token, `price` é o total ida+volta da combinação escolhida
        offer.return_segments = [_seg(f) for f in g["flights"]]
        offer.return_stops = len(g["flights"]) - 1
        offer.return_duration_minutes = g.get("total_duration")
        offer.total_price = float(g["price"])
        offer.airline = ", ".join(dict.fromkeys(
            [*offer.airline.split(", "), *_airlines(g["flights"]).split(", ")]))
        offer.return_details_known = True
