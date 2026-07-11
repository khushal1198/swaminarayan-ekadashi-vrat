#!/usr/bin/env python3
"""
Generate per-location Ekadashi fasting schedules as Markdown.

For each location it walks a Gregorian year, finds every Ekadashi observance
(including the tricky cases), and writes a clean MD table saying exactly which
day to fast and when to break it.

Cases handled:
  - Shuddha Ekadashi         -> fast on the Ekadashi-at-sunrise day
  - Viddha (Dashami vedh)    -> fast shifts to the next day (Dwadashi)
  - Kshaya (Ekadashi absent) -> fast on the Dwadashi day (tithi 10 -> 12 jump)
  - Vriddhi (two sunrises)   -> de-duplicated onto the single correct fast day

Usage:
    python generate_schedules.py 2026                       # all preset cities
    python generate_schedules.py 2026 2027                  # a range of years
    python generate_schedules.py 2026 --only fremont ahmedabad
"""

import argparse
from datetime import date, datetime, timedelta

from ekadashi_panchang import (
    TITHI_NAMES,
    analyze_date,
    compute_paran,
    fmt_time,
    get_ekadashi_info,
    get_sunrise,
    get_tithi,
)
from locations import LOCATIONS

TIER_TAG = {
    "mandatory": "**MANDATORY**",
    "chaturmas": "Chaturmas",
    "all_24": "—",
    "adhik": "Adhik-maas (extra)",
}


def tithi_at(d, loc):
    """Tithi number (1-15) at local sunrise for a given date."""
    dt = datetime(d.year, d.month, d.day)  # noqa: DTZ001
    sr = get_sunrise(dt, loc)
    _, t, _ = get_tithi(sr)
    return t


def find_observances(year, loc):
    """
    Return a list of observance dicts for every Ekadashi fast in `year` at `loc`,
    sorted by fast date. Handles shuddha / viddha / kshaya / vriddhi.
    """
    start = date(year, 1, 1)
    end = date(year, 12, 31)

    # Precompute tithi at sunrise for the whole year (+ 1 day margin each side)
    tithi = {}
    d = start - timedelta(days=2)
    while d <= end + timedelta(days=2):
        tithi[d] = tithi_at(d, loc)
        d += timedelta(days=1)

    by_fast_date = {}

    # --- Normal + viddha + vriddhi: every day whose sunrise tithi is Ekadashi ---
    d = start
    while d <= end:
        if tithi.get(d) == 11:
            a = analyze_date(d, loc)
            if a.is_ekadashi:
                obs = a.observance_date
                entry = {
                    "fast_date": obs,
                    "name": a.ekadashi_name,
                    "deity": a.deity,
                    "shakti": a.shakti,
                    "tier": a.tier,
                    "paksha": a.paksha,
                    "vs_year": a.vs_year,
                    "vs_month": a.vs_month_display,
                    "series": "Keshavadi" if a.paksha == "Sud" else "Sankarshanadi",
                    "kind": "viddha" if a.vedh.is_viddha else "shuddha",
                    "paran": a.paran,
                    "analysis": a,
                }
                # De-dup vriddhi: prefer the shuddha reading of a shared fast date
                prev = by_fast_date.get(obs)
                if prev is None or (prev["kind"] == "viddha" and entry["kind"] == "shuddha"):
                    by_fast_date[obs] = entry
        d += timedelta(days=1)

    # --- Kshaya: Ekadashi skipped => Dasham (10) directly to Baras (12) ---
    d = start
    while d <= end:
        nxt = d + timedelta(days=1)
        if tithi.get(d) == 10 and tithi.get(nxt) == 12:
            # Fast is observed on the Dwadashi day (nxt)
            a = analyze_date(nxt, loc)  # nxt is Baras; gives correct VS month/paksha
            name, deity, shakti, tier = get_ekadashi_info(a.vs_month, a.paksha, a.is_adhik)
            paran = compute_paran(nxt, a.paksha, loc)
            entry = {
                "fast_date": nxt,
                "name": name,
                "deity": deity,
                "shakti": shakti,
                "tier": tier,
                "paksha": a.paksha,
                "vs_year": a.vs_year,
                "vs_month": a.vs_month_display,
                "series": "Keshavadi" if a.paksha == "Sud" else "Sankarshanadi",
                "kind": "kshaya",
                "paran": paran,
                "analysis": a,
            }
            by_fast_date.setdefault(nxt, entry)
        d += timedelta(days=1)

    return [by_fast_date[k] for k in sorted(by_fast_date)]


KIND_NOTE = {
    "shuddha": "",
    "viddha": "Viddha — Dashami vedh; fast moved to Dwadashi",
    "kshaya": "Kshaya — Ekadashi absent at sunrise; fast on Dwadashi",
}


def render_md(year, loc, observances):
    L = []
    L.append(f"# Ekadashi Fasting Schedule — {loc.name} — {year}")
    L.append("")
    L.append(
        f"Computed for **{loc.name}** "
        f"({abs(loc.lat):.2f}°{'N' if loc.lat >= 0 else 'S'}, "
        f"{abs(loc.lon):.2f}°{'E' if loc.lon >= 0 else 'W'}, {loc.tz.key}). "
        "Fast day = the tithi at *local* sunrise, per Satsangi Jeevan P3/A31–36."
    )
    L.append("")
    L.append(
        "> The **Fast on** date is the day you observe the vrat. **Paran** is the "
        "window on the following day (Dwadashi) to break the fast, after sunrise "
        "and before the end of the first pahar."
    )
    L.append("")
    L.append("| # | Ekadashi | VS date | Fast on | Break fast (paran) | Tier | Note |")
    L.append("|---|----------|---------|---------|--------------------|------|------|")

    for i, e in enumerate(observances, 1):
        p = e["paran"]
        paran = (
            f"{p.paran_date.strftime('%a %b %d')} · "
            f"{fmt_time(p.window_start, loc)}–{fmt_time(p.window_end, loc)}"
        )
        fast = e["fast_date"].strftime("%a, %b %d, %Y")
        vs = f"VS {e['vs_year']} {e['vs_month']} {e['paksha']} 11"
        note = KIND_NOTE.get(e["kind"], "")
        if e["name"] == "Nirjala":
            note = (note + " · " if note else "") + "waterless (strictest)"
        if e["name"] == "Prabodhini":
            note = (note + " · " if note else "") + "equals all 24"
        L.append(
            f"| {i} | **{e['name']}** | {vs} | **{fast}** | {paran} | "
            f"{TIER_TAG.get(e['tier'], '—')} | {note} |"
        )

    L.append("")
    L.append("## Legend")
    L.append("")
    L.append("- **MANDATORY** — one of the 3 minimum Ekadashis (Devshayani, Parivartini, Prabodhini) per SJ P3/A32.")
    L.append("- **Chaturmas** — one of the 8 monsoon Ekadashis (Ashadh Sud through Kartik Sud).")
    L.append("- **Viddha** — Dashami contaminated the Ekadashi at sunrise; Vaishnavas fast on Dwadashi instead.")
    L.append("- **Kshaya** — the Ekadashi tithi was absent at every sunrise; the fast falls on the Dwadashi day.")
    L.append("")
    L.append(f"_Generated by `generate_schedules.py`. Verify against your mandir's panchang for edge cases._")
    L.append("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="Generate Ekadashi schedule MD files.")
    ap.add_argument("years", nargs="+", type=int, help="Gregorian year(s), e.g. 2026 2027")
    ap.add_argument("--only", nargs="*", help="Limit to these location keys")
    ap.add_argument("--outdir", default="schedules", help="Output directory")
    args = ap.parse_args()

    keys = args.only if args.only else list(LOCATIONS.keys())
    from pathlib import Path

    outdir = Path(args.outdir)
    outdir.mkdir(exist_ok=True)

    for year in args.years:
        for key in keys:
            loc = LOCATIONS[key]
            obs = find_observances(year, loc)
            md = render_md(year, loc, obs)
            path = outdir / f"{year}_{key}.md"
            path.write_text(md)
            print(f"  {path}  ({len(obs)} ekadashis)")


if __name__ == "__main__":
    main()
