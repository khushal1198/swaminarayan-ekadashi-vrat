# Ekadashi Schedules

Ready-made fasting calendars, one Markdown file per city per year, named
`YEAR_city.md` (e.g. `2026_fremont.md`, `2026_ahmedabad.md`).

Each file lists every Ekadashi of that year with the **exact day to fast**, the
**paran** (fast-breaking) window, the tier, and notes for viddha / kshaya /
Nirjala / Prabodhini cases — all computed for that city's local sunrise.

## Regenerate / add years

```bash
python generate_schedules.py 2028              # all built-in cities
python generate_schedules.py 2028 --only fremont newyork ahmedabad
```

Cities available: run `python ekadashi_panchang.py locations`. For any other
place, use `generate_schedules.py` after adding it to `locations.py`, or use the
calculator directly with `--location LAT,LON,ELEV,TZ`.

> These are a computational aid. For edge cases, cross-check with your mandir's
> published panchang.
