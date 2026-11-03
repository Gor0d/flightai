"""Testes com respostas simuladas no formato de cada API. Valores são FIXTURES de teste."""
import json
from datetime import date

from flighthunter.analysis import analyze, convenience, render_report
from flighthunter.config import Config
from flighthunter.http import HttpClient, ProviderError
from flighthunter.models import FlightOffer, SearchQuery, Segment
from flighthunter.providers.amadeus import AmadeusProvider
from flighthunter.providers.base import parse_iso_duration
from flighthunter.providers.duffel import DuffelProvider
from flighthunter.providers.serpapi import SerpApiProvider
from flighthunter.service import run_search
from flighthunter.storage import Storage

Q = SearchQuery("BEL", "BSB", date(2027, 1, 4), date(2027, 1, 6))


def fake_http(routes):
    """routes: lista de (substring_url, resposta|callable, status)."""
    calls = []

    def transport(method, url, headers, body, timeout):
        calls.append((method, url, body))
        for sub, resp, status in routes:
            if sub in url:
                r = resp(url, body) if callable(resp) else resp
                return status, json.dumps(r).encode()
        return 404, b"{}"
    c = HttpClient(transport)
    c.calls = calls
    return c


def test_iso_duration():
    assert parse_iso_duration("PT2H30M") == 150
    assert parse_iso_duration("P1DT1H") == 1500
    assert parse_iso_duration(None) is None


AMADEUS_RESP = {"data": [{
    "id": "1",
    "itineraries": [
        {"duration": "PT2H55M", "segments": [{"carrierCode": "G3", "number": "1100", "duration": "PT2H55M",
            "departure": {"iataCode": "BEL", "at": "2027-01-04T08:00:00"},
            "arrival": {"iataCode": "BSB", "at": "2027-01-04T10:55:00"}, "operating": {"carrierCode": "G3"}}]},
        {"duration": "PT3H10M", "segments": [{"carrierCode": "G3", "number": "1101", "duration": "PT3H10M",
            "departure": {"iataCode": "BSB", "at": "2027-01-06T12:00:00"},
            "arrival": {"iataCode": "BEL", "at": "2027-01-06T14:10:00"}}]}],
    "price": {"currency": "BRL", "grandTotal": "1200.00", "base": "1000.00"}}]}


def test_amadeus_parse():
    http = fake_http([("oauth2/token", {"access_token": "t"}, 200),
                      ("flight-offers", AMADEUS_RESP, 200)])
    p = AmadeusProvider("id", "secret", "test", http)
    [o] = p.search(Q)
    assert o.total_price == 1200 and o.taxes == 200 and o.is_direct
    assert o.outbound_duration_minutes == 175 and o.return_duration_minutes == 190
    assert o.outbound_segments[0].flight_number == "G31100"
    assert p.calls == 2


DUFFEL_RESP = {"data": {"offers": [
    {"id": "off_1", "total_amount": "1500.00", "total_currency": "BRL", "tax_amount": "300.00",
     "base_amount": "1200.00", "owner": {"name": "LATAM"},
     "slices": [{"duration": "PT6H", "segments": [
         {"origin": {"iata_code": "BEL"}, "destination": {"iata_code": "GRU"}, "departing_at": "2027-01-04T05:00:00",
          "arriving_at": "2027-01-04T09:00:00", "marketing_carrier": {"iata_code": "LA"},
          "marketing_carrier_flight_number": "1", "operating_carrier": {"iata_code": "LA"}, "duration": "PT4H"},
         {"origin": {"iata_code": "GRU"}, "destination": {"iata_code": "BSB"}, "departing_at": "2027-01-04T10:00:00",
          "arriving_at": "2027-01-04T11:00:00", "marketing_carrier": {"iata_code": "LA"},
          "marketing_carrier_flight_number": "2", "operating_carrier": {"iata_code": "LA"}, "duration": "PT1H"}]},
         {"duration": "PT3H", "segments": [
             {"origin": {"iata_code": "BSB"}, "destination": {"iata_code": "BEL"}, "departing_at": "2027-01-06T10:00:00",
              "arriving_at": "2027-01-06T13:00:00", "marketing_carrier": {"iata_code": "LA"},
              "marketing_carrier_flight_number": "3", "operating_carrier": {"iata_code": "LA"}, "duration": "PT3H"}]}]},
    {"id": "off_2", "total_amount": "10.00", "total_currency": "BRL", "owner": {"name": "Duffel Airways"},
     "slices": [{"segments": []}, {"segments": []}]}]}}


def test_duffel_parse_and_drops_sandbox_airline():
    p = DuffelProvider("tok", fake_http([("offer_requests", DUFFEL_RESP, 200)]))
    offers = p.search(Q)
    assert len(offers) == 1
    o = offers[0]
    assert o.outbound_stops == 1 and o.return_stops == 0 and o.total_stops == 1
    assert o.taxes == 300 and o.airline == "LATAM"


SERP_OUT = {"best_flights": [{
    "flights": [{"departure_airport": {"id": "BEL", "time": "2027-01-04 08:00"},
                 "arrival_airport": {"id": "BSB", "time": "2027-01-04 10:55"},
                 "duration": 175, "airline": "GOL", "flight_number": "G3 1100"}],
    "total_duration": 175, "price": 1100, "departure_token": "TOK1"},
    {"flights": [], "price": 5}, {"flights": [{"departure_airport": {"id": "BEL", "time": "x"},
                                               "arrival_airport": {"id": "BSB", "time": "y"}}]}],  # sem preço
    "other_flights": [], "search_metadata": {"google_flights_url": "https://example/flights"}}
SERP_BACK = {"best_flights": [{
    "flights": [{"departure_airport": {"id": "BSB", "time": "2027-01-06 12:00"},
                 "arrival_airport": {"id": "BEL", "time": "2027-01-06 14:10"},
                 "duration": 190, "airline": "GOL", "flight_number": "G3 1101"}],
    "total_duration": 190, "price": 1250}]}


def test_serpapi_outbound_then_return_detail_and_no_price_dropped():
    def resp(url, body):
        return SERP_BACK if "departure_token" in url else SERP_OUT
    p = SerpApiProvider("key", fake_http([("serpapi.com", resp, 200)]), return_details=1)
    offers = p.search(Q)
    assert len(offers) == 1                      # ofertas sem preço descartadas
    o = offers[0]
    assert o.return_details_known and o.return_stops == 0 and o.total_price == 1250
    assert o.is_direct and p.calls == 2


def test_serpapi_without_return_detail_is_marked_unknown():
    p = SerpApiProvider("key", fake_http([("serpapi.com", SERP_OUT, 200)]), return_details=0)
    [o] = p.search(Q)
    assert not o.return_details_known and o.return_segments == [] and o.total_price == 1100


def test_http_error_hides_api_key():
    p = SerpApiProvider("SECRETKEY", fake_http([("serpapi.com", {"error": "bad"}, 401)]))
    try:
        p.search(Q)
        assert False
    except ProviderError as e:
        assert "SECRETKEY" not in str(e)


def _offer(price, out=date(2027, 1, 4), ret=date(2027, 1, 6), stops=0, provider="x", n=0):
    seg = Segment("G3", f"G3{n}", "BEL", "BSB", f"{out}T08:00", f"{out}T11:00", 180)
    return FlightOffer(provider, "GOL", None, "BEL", "BSB", out, ret, [seg] * (stops + 1), [seg] * (stops + 1),
                       stops, stops, 180 + 120 * stops, 180 + 120 * stops, price, None)


def test_analysis_separates_alternatives_and_prefers_cheapest():
    cfg = Config()
    offers = [_offer(1500, n=1), _offer(1000, stops=1, n=2), _offer(800, ret=date(2027, 1, 7), n=3),
              _offer(1450, out=date(2027, 1, 3), n=4)]
    a = analyze(offers, cfg)
    assert [o.total_price for o in a.main] == [1000, 1450, 1500]
    assert [o.total_price for o in a.alternatives] == [800]       # volta ≠ 06/01 só em alternativas
    assert a.best_overall.total_price == 1000 and not a.best_overall.is_direct
    assert a.best_direct.total_price == 1450
    assert a.best_ranked.total_price == 1000                     # direto >5% mais caro não vence o preço
    assert convenience(a.best_direct, a.min_duration) > convenience(a.best_overall, a.min_duration)
    assert "ALTERNATIVAS" in render_report(a, cfg)


def test_prefer_direct_tiebreak_within_5pct():
    a = analyze([_offer(1000, stops=1, n=1), _offer(1040, n=2)], Config())
    assert a.best_ranked.total_price == 1040


class StubProvider:
    name = "stub"
    calls = 0

    def __init__(self, offers):
        self.offers = offers

    def is_configured(self):
        return True

    def search(self, q):
        self.calls += 1
        return [o for o in self.offers if o.outbound_date == q.outbound_date and o.return_date == q.return_date]


class Capture:
    def __init__(self):
        self.sent = []

    def send(self, s, b):
        self.sent.append((s, b))


def test_alerts_target_drop_and_dedup():
    cfg = Config(alternative_outbounds=[], max_calls_per_run=0)
    store, cap = Storage(":memory:"), Capture()
    # 1ª execução: acima do alvo, sem histórico -> sem alerta
    r1 = run_search(cfg, [StubProvider([_offer(1600, n=1)])], store, [cap], include_alternatives=False)
    assert r1.alerts == [] and cap.sent == []
    # 2ª: cai para 1250 (<= alvo e queda >10%) -> alerta
    r2 = run_search(cfg, [StubProvider([_offer(1250, n=1)])], store, [cap], include_alternatives=False)
    assert len(r2.alerts) == 1 and "alvo" in r2.alerts[0].lower() and len(cap.sent) == 1
    # 3ª: mesmo preço -> não repete
    r3 = run_search(cfg, [StubProvider([_offer(1250, n=1)])], store, [cap], include_alternatives=False)
    assert r3.alerts == []
    # 4ª: cai mais -> alerta de novo
    r4 = run_search(cfg, [StubProvider([_offer(1100, n=1)])], store, [cap], include_alternatives=False)
    assert len(r4.alerts) == 1


def test_unconfigured_provider_skipped_and_failure_isolated():
    class Broken(StubProvider):
        def search(self, q):
            raise ProviderError("boom")

    class Off(StubProvider):
        def is_configured(self):
            return False
    cfg = Config(alternative_outbounds=[], max_calls_per_run=0)
    res = run_search(cfg, [Off([]), Broken([]), StubProvider([_offer(900)])], Storage(":memory:"),
                     include_alternatives=False)
    assert len(res.offers) == 1 and len(res.skipped) == 1 and len(res.errors) == 1


def test_offer_roundtrip_and_fingerprint_ignores_price():
    o = _offer(900)
    assert FlightOffer.from_dict(json.loads(json.dumps(o.to_dict()))).fingerprint == o.fingerprint
    assert _offer(500).fingerprint == o.fingerprint
