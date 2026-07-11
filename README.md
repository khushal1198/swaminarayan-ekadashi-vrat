# 🌙 Swaminarayan Ekadashi Vrat — When to actually fast

A calculator and set of ready-made calendars that tell you **which day to observe
each Ekadashi fast at your location**, following the rules laid out in the
**Satsangi Jeevan, Prakaran 3, Adhyays 31–36** — the most detailed treatment of
Ekadashi in the Swaminarayan canon.

> **Why this exists:** The fast day is decided by the tithi at *local sunrise*.
> Because sunrise in the US happens ~12.5 hours after India, the very same
> Ekadashi can fall on a **different calendar date** in Fremont than in Ahmedabad.
> This tool computes it correctly for wherever you are — no guessing, no
> copying India's dates.

---

## Quick start

```bash
pip install -r requirements.txt

# Is it Ekadashi today? Should I fast? (asks for your city if not given)
python ekadashi_panchang.py today -l fremont

# When is the next Ekadashi, and when do I break the fast?
python ekadashi_panchang.py next -l ahmedabad

# Check any specific date
python ekadashi_panchang.py check 2026-08-08 -l newyork

# Upcoming Ekadashis for the next N months
python ekadashi_panchang.py upcoming 6 -l chicago

# List all built-in cities
python ekadashi_panchang.py locations
```

Any city not in the presets? Pass coordinates directly:

```bash
python ekadashi_panchang.py today -l 51.5074,-0.1278,11,Europe/London   # London
```

---

## Ready-made schedules

Pre-generated year calendars live in [`schedules/`](schedules/) — one Markdown
file per city per year, e.g. [`schedules/2026_fremont.md`](schedules/2026_fremont.md).
Each lists every Ekadashi, the **exact day to fast**, the **paran** (fast-breaking)
window, its tier, and any special notes (viddha / kshaya / Nirjala / Prabodhini).

Regenerate them any time (or for future years):

```bash
python generate_schedules.py 2026 2027            # all cities
python generate_schedules.py 2028 --only fremont  # one city
```

---

## Built-in cities

**India:** Ahmedabad, Gandhinagar, Vadtal, Bochasan, Gadhada, Sarangpur, Junagadh,
Rajkot, Surat, Vadodara, Mumbai, Pune, Delhi, Bengaluru, Hyderabad, Chennai, Kolkata

**USA:** New York, Los Angeles, Chicago, Houston, Phoenix, Philadelphia,
San Antonio, San Diego, Dallas, San Jose, Fremont, Atlanta, Edison,
Robbinsville (BAPS Akshardham NJ)

…plus **any** latitude/longitude on earth.

---

## What the rules actually are

See [`docs/rules.md`](docs/rules.md) for the full explanation. In short:

| Concept | Rule (SJ P3/A31–36) |
|--------|----------------------|
| **Fast day** | The day the Ekadashi tithi (11) is present at local sunrise. |
| **Dashami Vedh** | If Dashami (10) lingers into *arunodaya* (sunrise − 96 min), the Ekadashi is **viddha** (contaminated) and the fast shifts to Dwadashi. |
| **Kshaya** | If the Ekadashi tithi is absent at every sunrise, the fast falls on the **Dwadashi** day. |
| **Paran** | Break the fast on Dwadashi, after sunrise and before the end of the first *pahar* (quarter of daytime) — or before Dwadashi ends, if it's short. |
| **Tiers** | Best: all 24 · Acceptable: 8 Chaturmas · Minimum: 3 mandatory (Devshayani, Parivartini, Prabodhini) · Absolute minimum: Prabodhini alone = fruit of all 24. |

The 24 named Ekadashis, their presiding deities and shaktis are in
[`docs/24-ekadashis.md`](docs/24-ekadashis.md).

---

## How it works

- **Astronomy:** [PyEphem](https://rhodesmill.org/pyephem/) computes sunrise and
  Moon–Sun elongation; tithi = `floor(elongation / 12°) + 1`. Sidereal positions
  use the Lahiri ayanamsa.
- **VS calendar:** `vs_calendar_complete.db` is a precomputed Vikram Samvat ↔
  Gregorian table (1735–2076, Gujarati Amanta reckoning, sunrise-based) used as
  the source of truth for VS year and for fast candidate dates.
- **Rule engine:** boundary crossings of the tithi are found by binary search to
  sub-second precision, then the vedh / kshaya / paran rules above are applied.

---

## Files

```
ekadashi_panchang.py     # the calculator (today / next / check / upcoming / locations)
generate_schedules.py    # builds the per-city Markdown calendars
locations.py             # built-in city presets
vs_calendar_complete.db  # precomputed VS↔Gregorian calendar (1735–2076)
schedules/               # ready-made year calendars, one MD per city per year
docs/                    # rules explainer + the 24 named Ekadashis
requirements.txt         # ephem
```

---

## A note on accuracy

This follows the classical panchang conventions and the SJ rules faithfully, and
matches standard panchangs within the usual ±1-day convention differences (sunrise
vs midnight tithi assignment). For any edge case — especially kshaya and
dual-sunrise (vriddhi) Ekadashis — **cross-check with your mandir's published
panchang**. This is a computational aid, not a replacement for sampradaya
authority.

Jay Swaminarayan 🙏
