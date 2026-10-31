import pytest

from app.risk import (
    Day,
    flood_hazard,
    heat_hazard,
    level,
    rain_anomaly_score,
    rain_category,
    rain_intensity_score,
    score_district,
    vulnerability_weight,
)


@pytest.mark.parametrize(
    "mm,cat",
    [(0, "light"), (15.6, "moderate"), (64.5, "heavy"), (115.6, "very heavy"), (204.5, "extremely heavy")],
)
def test_imd_rain_categories(mm, cat):
    assert rain_category(mm) == cat


def test_rain_intensity_is_monotonic_and_bounded():
    scores = [rain_intensity_score(x) for x in range(0, 400, 5)]
    assert scores == sorted(scores)
    assert scores[0] == 0 and scores[-1] == 1


def test_same_rain_is_riskier_where_it_is_unusual():
    # 120 mm over five days: routine on the Konkan coast, extreme in the Thar desert.
    wet_district = flood_hazard(60, 120, normal_rx5day_mm=450)
    dry_district = flood_hazard(60, 120, normal_rx5day_mm=90)
    assert dry_district > wet_district


def test_anomaly_without_normal_is_zero():
    assert rain_anomaly_score(500, None) == 0


def test_heat_thresholds():
    assert heat_hazard(34, 36, 24, 0) == 0
    assert 0 < heat_hazard(41, None, None, 2) < heat_hazard(46, None, None, 2) <= 1


def test_heatwave_needs_two_days():
    assert heat_hazard(44, None, None, hot_streak=1) < heat_hazard(44, None, None, hot_streak=2)


def test_warm_nights_add_risk():
    assert heat_hazard(42, None, 31, 2) > heat_hazard(42, None, 26, 2)


def test_humidity_driven_feels_like_can_dominate():
    # 38 C but feels like 52 C (coastal humidity) should not score as mild.
    assert heat_hazard(38, 52, 29, 0) > heat_hazard(38, None, 29, 0)


def test_vulnerability_weight_range():
    assert vulnerability_weight(0.2, 0.2, 0.8) == 0.5
    assert vulnerability_weight(0.8, 0.2, 0.8) == 1.0
    assert vulnerability_weight(None, 0.2, 0.8) == 0.75


@pytest.mark.parametrize("score,name", [(0, "Low"), (0.15, "Moderate"), (0.35, "High"), (0.6, "Severe"), (1, "Severe")])
def test_levels(score, name):
    assert level(score) == name


def _days(rain, tmax):
    return [Day(date=f"2026-07-0{i + 1}", rain_mm=r, tmax=t, tmin=25, feels_like=t) for i, (r, t) in enumerate(zip(rain, tmax))]


def test_calm_week_is_low():
    r = score_district(_days([0] * 7, [30] * 7), 150, 1.0)
    assert r.level == "Low" and r.overall == 0
    assert r.drivers == ["No significant rain or heat in the 7-day forecast"]


def test_storm_week_is_severe_and_peaks_on_storm_day():
    r = score_district(_days([10, 80, 250, 120, 0, 0, 0], [30] * 7), 150, 1.0)
    assert r.level == "Severe"
    assert r.peak_date == "2026-07-03"
    assert r.flood > r.heat
    assert any("extremely heavy" in d for d in r.drivers)


def test_vulnerability_scales_risk():
    days = _days([0] * 7, [46] * 7)
    assert score_district(days, 100, 0.5).heat == pytest.approx(score_district(days, 100, 1.0).heat / 2, abs=0.002)


def test_empty_forecast_rejected():
    with pytest.raises(ValueError):
        score_district([], 100, 1.0)


def test_drivers_use_readable_dates():
    r = score_district(_days([0, 0, 130, 0, 0, 0, 0], [30] * 7), 150, 1.0)
    assert r.drivers[0].startswith("130 mm of rain on Fri 3 Jul")
