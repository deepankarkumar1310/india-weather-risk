import httpx

from app.forecast import BATCH_SIZE, build_params, fetch_forecasts, parse_location


def test_build_params_joins_coordinates():
    p = build_params([(19.0, 72.875), (26.25, 73.0)])
    assert p["latitude"] == "19.0000,26.2500"
    assert p["longitude"] == "72.8750,73.0000"
    assert "precipitation_sum" in p["daily"]
    assert p["timezone"] == "Asia/Kolkata"


def test_parse_handles_nulls(open_meteo_payload):
    mumbai, jodhpur = (parse_location(p) for p in open_meteo_payload)
    assert len(mumbai) == 7
    assert mumbai[5].rain_mm == 0.0  # null rain -> 0
    assert len(jodhpur) == 6  # day with null temperature dropped
    assert jodhpur[2].tmax == 46.9 and jodhpur[2].feels_like == 50.1


def test_fetch_batches_and_keeps_order(open_meteo_payload, monkeypatch):
    monkeypatch.setattr("app.forecast.time.sleep", lambda s: None)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        n = len(request.url.params["latitude"].split(","))
        calls.append(n)
        return httpx.Response(200, json=[open_meteo_payload[i % 2] for i in range(n)])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    points = [(20.0, 78.0)] * (BATCH_SIZE + 5)
    out = fetch_forecasts(points, client=client)
    assert calls == [BATCH_SIZE, 5]
    assert len(out) == BATCH_SIZE + 5
    assert out[0][0].tmax == 30.1 and out[1][0].tmax == 44.8


def test_fetch_retries_on_server_error(open_meteo_payload, monkeypatch):
    monkeypatch.setattr("app.forecast.time.sleep", lambda s: None)
    attempts = {"n": 0}

    def handler(request):
        attempts["n"] += 1
        if attempts["n"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, json=open_meteo_payload[0])

    out = fetch_forecasts([(19.0, 72.875)], client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert attempts["n"] == 3 and len(out) == 1
