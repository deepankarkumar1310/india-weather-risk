# Methodology

How a forecast becomes a district risk score. All code is in [`app/risk.py`](../app/risk.py).

## 1. Framework

The app follows the IPCC definition:

> **Risk = Hazard × Vulnerability**

*Hazard* is how dangerous the forecast weather is. *Vulnerability* is how badly a district is likely to be affected when that weather hits. Both are scored from 0 to 1. Every score is computed **per day** for 7 days, and the headline score is the highest day.

## 2. Forecast input

The app requests these daily values from the [Open-Meteo forecast API](https://open-meteo.com/en/docs) for one point in each district (`shapely.representative_point`, which is always inside the polygon):

`precipitation_sum`, `temperature_2m_max`, `temperature_2m_min`, `apparent_temperature_max`, `precipitation_probability_max`

All 640 districts are fetched in 7 batched requests (100 points each), with retries and backoff.

## 3. Flood hazard

```
flood = 0.6 × intensity + 0.4 × anomaly
```

**Intensity** places one day's rain on IMD's national rainfall scale:

| Daily rain | IMD term | Score |
|---|---|---|
| < 15.6 mm | light | 0 |
| 64.5 mm | heavy | 0.35 |
| 115.6 mm | very heavy | 0.60 |
| 204.5 mm | extremely heavy | 0.85 |
| ≥ 300 mm | | 1.0 |

Scores between these points are linear.

**Anomaly** measures how unusual the rain is *for this district*. It compares the 5-day running total with `rx5day`, the district's average wettest 5-day spell per year, from IMD 0.25° gridded rainfall for 1991–2020. A total equal to half of `rx5day` scores 0, and 1.5 × `rx5day` scores 1.

Why both parts: intensity alone would put Konkan-coast districts in permanent alarm during the monsoon. Anomaly alone would raise alarms over 30 mm of rain in the desert. The 60/40 split keeps absolute severity as the main signal.

## 4. Heat hazard

```
heat = max(temperature score, feels-like score)
       + 0.10   if Tmin ≥ 30 °C and Tmax ≥ 40 °C   (no relief at night)
       × 0.85   if Tmax ≥ 40 °C on fewer than 2 consecutive days
```

| Tmax | Score | | Feels-like | Score |
|---|---|---|---|---|
| 35 °C | 0 | | 38 °C | 0 |
| 40 °C (IMD heatwave) | 0.30 | | 46 °C | 0.60 |
| 45 °C (IMD severe) | 0.75 | | 54 °C | 1.0 |
| 48 °C | 1.0 | | | |

Why feels-like: humid coastal heat at 38 °C can be as dangerous as dry heat at 45 °C. Why the 2-day rule: IMD declares a heatwave only after the criteria hold for two consecutive days.

## 5. Vulnerability

The [NITI Aayog Climate Vulnerability Index (2021)](https://ndap.niti.gov.in/) combines more than 30 indicators, including poverty, health access, irrigation, forest cover and road density. It covers 589 of the 640 districts after matching 2021 districts back to 2011 census codes. The other 51 districts get their state's median, and this is flagged in the API as `vulnerability_imputed`.

The index is rescaled to a weight:

```
weight = 0.5 + 0.5 × (CVI − min) / (max − min)       → 0.5 … 1.0
```

The floor is 0.5 so that well-prepared districts still show up on the map when a severe storm or heatwave is forecast.

## 6. Levels

| Score (0–100) | Level |
|---|---|
| < 15 | Low |
| 15–34 | Moderate |
| 35–59 | High |
| ≥ 60 | Severe |

Rough guide: one day of very heavy rain (~120 mm) in a highly vulnerable district reaches *High*. Two or more days above 45 °C reach *High* in any district and *Severe* in the more vulnerable ones.

## 7. Why there is no machine-learning model

A supervised model needs labelled outcomes, such as records of which districts actually flooded or had heat deaths on which days. No open, consistent dataset like that exists at district level for India. A model trained on proxy labels would only learn the thresholds above in a more opaque way. Rules based on IMD's published thresholds are transparent, testable, and match how official warnings are issued.

## 8. Known limitations

See [README → Limitations](../README.md#limitations).
