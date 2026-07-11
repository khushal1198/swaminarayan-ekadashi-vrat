#!/usr/bin/env python3
"""
Swaminarayan Ekadashi Panchang
Complete Ekadashi calculator with all rules from Satsangi Jeevan P3/A31-36.

This tells you *which day to actually fast* for each Ekadashi at YOUR location,
because the fast day is decided by the tithi at local sunrise — so the correct
Gregorian date can differ between India and the US for the very same Ekadashi.

Features:
- Tithi at sunrise for any location (built-in city presets, or custom lat/lon)
- Dashami Vedh detection (SJ P3/A33): shuddha vs viddha determination
- 18-classification system (Shuddha/Viddha x Nyuna/Sama/Adhika x Dwadashi types)
- 24 named Ekadashis with presiding Keshavadi/Sankarshanadi deities (SJ P3/A35)
- Mandatory/Chaturmas/All-24 tier classification (SJ P3/A32)
- Paran (fast-breaking) window on Dwadashi (SJ P3/A33)
- Upcoming Ekadashi schedule

Usage:
    python ekadashi_panchang.py today [--location fremont|ahmedabad|LAT,LON]
    python ekadashi_panchang.py next [--location ...]
    python ekadashi_panchang.py check 2026-03-28 [--location ...]
    python ekadashi_panchang.py upcoming [months] [--location ...]
    python ekadashi_panchang.py locations          # list all built-in cities
"""

import argparse
import math
import sqlite3
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import ephem

from locations import DEFAULT_LOCATION, LOCATIONS, Location, list_locations

# ---------------------------------------------------------------------------
# 24 Named Ekadashis — SJ P3/A35
# (month, name, deity, shakti, tier)
# ---------------------------------------------------------------------------

SUD_EKADASHIS = {
    "Magshar": ("Mokshada", "Keshav", "Shridevi", "all_24"),
    "Posh": ("Putrada", "Narayan", "Padma", "all_24"),
    "Maha": ("Jaya", "Madhav", "Nitya", "all_24"),
    "Fagan": ("Amalaki", "Govind", "Chandra", "all_24"),
    "Chaitra": ("Kamada", "Vishnu", "Rama", "all_24"),
    "Vaishakh": ("Mohini", "Madhusudhan", "Madhavi", "all_24"),
    "Jeth": ("Nirjala", "Trivikram", "Padmakshi", "all_24"),
    "Ashadh": ("Devshayani", "Vaman", "Kamala", "mandatory"),
    "Shravan": ("Putrada", "Shridhar", "Kantimati", "chaturmas"),
    "Bhadarvo": ("Parivartini", "Hrishikesh", "Aparajita", "mandatory"),
    "Aso": ("Pashankusha", "Padmanabh", "Padmavati", "chaturmas"),
    "Kartik": ("Prabodhini", "Damodar", "Radha", "mandatory"),
}

VAD_EKADASHIS = {
    "Magshar": ("Saphala", "Sankarshan", "Sunanda", "all_24"),
    "Posh": ("Shattila", "Vasudev", "Harini", "all_24"),
    "Maha": ("Vijaya", "Pradyumna", "Dhi", "all_24"),
    "Fagan": ("Papmochani", "Aniruddh", "Sushila", "all_24"),
    "Chaitra": ("Varuthini", "Purushottam", "Nanda", "all_24"),
    "Vaishakh": ("Apara", "Adhokshaj", "Trayi", "all_24"),
    "Jeth": ("Yogini", "Nrusinh", "Kshemkari", "all_24"),
    "Ashadh": ("Kamika", "Achyut", "Vijaya", "chaturmas"),
    "Shravan": ("Aja", "Janardan", "Sundari", "chaturmas"),
    "Bhadarvo": ("Indira", "Upendra", "Subhaga", "chaturmas"),
    "Aso": ("Rama", "Hari", "Hiranya", "chaturmas"),
    "Kartik": ("Utpanna", "Shri Krishna", "Sulakshana", "chaturmas"),
}

TIER_LABELS = {
    "mandatory": "Mandatory (1 of 3 minimum — SJ P3/A32)",
    "chaturmas": "Chaturmas (monsoon observance — SJ P3/A32)",
    "all_24": "All 24 Ekadashis",
}

# ---------------------------------------------------------------------------
# Astronomical engine — reuses PyEphem (same as generate_vs_calendar_forward.py)
# ---------------------------------------------------------------------------


def get_sunrise(date, loc):
    """Sunrise time (UTC datetime) at a location."""
    obs = ephem.Observer()
    obs.lat, obs.lon, obs.elevation = str(loc.lat), str(loc.lon), loc.elevation
    obs.date = date
    return obs.next_rising(ephem.Sun()).datetime()


def get_sunset(date, loc):
    """Sunset time (UTC datetime) at a location."""
    obs = ephem.Observer()
    obs.lat, obs.lon, obs.elevation = str(loc.lat), str(loc.lon), loc.elevation
    obs.date = date
    return obs.next_setting(ephem.Sun()).datetime()


def get_elongation(dt):
    """Moon-Sun elongation in degrees (0-360) at a given UTC datetime."""
    sun = ephem.Sun(dt)
    moon = ephem.Moon(dt)
    sun_lon = float(ephem.Ecliptic(sun).lon) * 180.0 / math.pi
    moon_lon = float(ephem.Ecliptic(moon).lon) * 180.0 / math.pi
    return (moon_lon - sun_lon) % 360.0


def get_tithi(dt):
    """
    Tithi at a given UTC datetime.
    Returns (paksha, tithi_1_to_15, elongation).
    Matches generate_vs_calendar_forward.py logic including conjunction edge case.
    """
    elong = get_elongation(dt)
    tithi_num = int(elong / 12.0) + 1
    if abs(elong) < 1e-9:
        tithi_num = 30
    if tithi_num <= 15:
        return "Sud", tithi_num, elong
    return "Vad", tithi_num - 15, elong


def find_elongation_crossing(target_deg, search_start, search_end):
    """
    Binary search for the UTC instant when elongation crosses target_deg.
    Handles the 360→0 wrap by normalizing around the target.
    Returns datetime with sub-second precision (~20 iterations on 48h window).
    """

    def normalized(dt):
        e = get_elongation(dt)
        # Normalize so values near target don't wrap
        diff = (e - target_deg + 180) % 360 - 180
        return diff

    lo, hi = search_start, search_end
    # Ensure lo is before crossing (negative diff) and hi is after (positive diff)
    if normalized(lo) > 0 and normalized(hi) < 0:
        # Swap — shouldn't normally happen for our use cases
        lo, hi = hi, lo

    for _ in range(60):
        mid = lo + (hi - lo) / 2
        if normalized(mid) < 0:
            lo = mid
        else:
            hi = mid
        if (hi - lo).total_seconds() < 1.0:
            break

    return lo + (hi - lo) / 2


def get_lahiri_ayanamsa(dt):
    """Lahiri ayanamsa — same formula as generate_vs_calendar_forward.py."""
    year_frac = dt.year + (dt.timetuple().tm_yday - 1) / 365.25
    return 23.85472 + 0.013972 * (year_frac - 2000.0)


def get_sun_rashi(dt):
    """Sidereal solar rashi (0=Aries..11=Pisces)."""
    sun = ephem.Sun(dt)
    trop_lon = float(ephem.Ecliptic(sun).lon) * 180.0 / math.pi
    sid_lon = (trop_lon - get_lahiri_ayanamsa(dt)) % 360.0
    return int(sid_lon / 30)


RASHI_TO_MONTH = {
    7: "Kartik",
    8: "Magshar",
    9: "Posh",
    10: "Maha",
    11: "Fagan",
    0: "Chaitra",
    1: "Vaishakh",
    2: "Jeth",
    3: "Ashadh",
    4: "Shravan",
    5: "Bhadarvo",
    6: "Aso",
}


def find_prev_new_moon(dt):
    """Most recent new moon strictly before dt."""
    threshold = dt - timedelta(hours=1)
    check = dt - timedelta(days=35)
    prev = None
    while True:
        nm = ephem.next_new_moon(check).datetime()
        if nm > threshold:
            break
        prev = nm
        check = nm + timedelta(days=1)
    return prev


def find_next_new_moon(dt):
    """Next new moon after dt."""
    return ephem.next_new_moon(dt).datetime()


def get_lunar_month_info(sunrise_time):
    """
    VS month via Amanta lunar intervals (new moon to new moon).
    Returns (month_name, display_name, is_adhik).
    """
    delta = timedelta(hours=9)
    prev_nm = find_prev_new_moon(sunrise_time)
    next_nm = find_next_new_moon(prev_nm + timedelta(days=1))

    rashi_start = get_sun_rashi(prev_nm + delta)
    rashi_end = get_sun_rashi(next_nm + delta)
    is_adhik = rashi_start == rashi_end
    month_name = RASHI_TO_MONTH[(rashi_start + 1) % 12]

    if is_adhik:
        display_name = f"Adhik {month_name}"
    else:
        prev_prev_nm = find_prev_new_moon(prev_nm)
        if prev_prev_nm:
            pr_start = get_sun_rashi(prev_prev_nm + delta)
            pr_end = get_sun_rashi(prev_nm + delta)
            if pr_start == pr_end and RASHI_TO_MONTH[(pr_start + 1) % 12] == month_name:
                display_name = f"Nij {month_name}"
            else:
                display_name = month_name
        else:
            display_name = month_name

    return month_name, display_name, is_adhik


def _get_db_connection():
    """Lazy singleton connection to vs_calendar_complete.db."""
    if not hasattr(_get_db_connection, "_conn"):
        db_path = Path(__file__).parent / "vs_calendar_complete.db"
        if db_path.exists():
            _get_db_connection._conn = sqlite3.connect(db_path)
        else:
            _get_db_connection._conn = None
    return _get_db_connection._conn


def get_vs_year(greg_date, month_name=None, is_adhik=None):
    """
    VS year from the precomputed calendar DB (source of truth).
    Falls back to simple formula only if date is outside DB range.
    """
    conn = _get_db_connection()
    if conn:
        gd = (
            greg_date.date()
            if hasattr(greg_date, "date") and callable(greg_date.date)
            else greg_date
        )
        date_str = gd.isoformat() if hasattr(gd, "isoformat") else str(gd)
        row = conn.execute(
            "SELECT vs_year FROM vs_calendar WHERE gregorian_date = ? AND is_kshaya = 0",
            (date_str,),
        ).fetchone()
        if row:
            return row[0]

    # Fallback for dates outside DB range
    greg_year = greg_date.year if hasattr(greg_date, "year") else greg_date
    kartik_half = {"Kartik", "Magshar", "Posh", "Maha", "Fagan", "Chaitra"}
    if month_name and month_name in kartik_half and not is_adhik:
        return greg_year + 57
    return greg_year + 56


# ---------------------------------------------------------------------------
# Ekadashi rule engine — SJ P3/A31-36
# ---------------------------------------------------------------------------


def tithi_boundary_deg(paksha, tithi_num):
    """
    Elongation degree at which a tithi STARTS.
    Sud tithi N (1-15): starts at (N-1)*12 deg
    Vad tithi N (1-15): starts at (N+14)*12 deg
    """
    if paksha in ("Sud", "sud"):
        return (tithi_num - 1) * 12.0
    return (tithi_num + 14) * 12.0


@dataclass
class VedhResult:
    is_viddha: bool
    dashami_end: datetime  # when Dashami→Ekadashi boundary occurs
    arunodaya: datetime  # sunrise - 96 min
    gap_minutes: float  # how many minutes between dashami end and arunodaya
    ekadashi_start: datetime  # same as dashami_end
    ekadashi_end: datetime  # when Ekadashi→Dwadashi boundary occurs


@dataclass
class ParanResult:
    paran_date: datetime  # date to break fast
    sunrise: datetime
    window_start: datetime
    window_end: datetime
    dwadashi_start: datetime
    dwadashi_end: datetime
    note: str


@dataclass
class Classification:
    vedh_type: str  # "Shuddha" or "Viddha"
    ekadashi_class: str  # "Nyuna", "Sama", "Adhika"
    dwadashi_class: str  # "Nyuna", "Sama", "Adhika"
    label: str  # e.g. "Shuddha Adhika"
    ekadashi_ghatikas: float
    dwadashi_ghatikas: float
    classification_number: int  # 1-18


def check_vedh(sunrise, paksha, loc):
    """
    Dashami Vedh check per SJ P3/A33.
    If Dashami is present at arunodaya (sunrise - 96 min), Ekadashi is viddha.
    """
    arunodaya = sunrise - timedelta(minutes=96)

    # Degree boundaries for this paksha
    dashami_end_deg = tithi_boundary_deg(paksha, 11)  # Ekadashi starts here
    ekadashi_end_deg = tithi_boundary_deg(paksha, 12)  # Dwadashi starts here

    # Search window: 2 days before sunrise to 2 days after
    search_lo = sunrise - timedelta(days=2)
    search_hi = sunrise + timedelta(days=2)

    dashami_end = find_elongation_crossing(dashami_end_deg, search_lo, search_hi)
    ekadashi_end = find_elongation_crossing(ekadashi_end_deg, search_lo, search_hi)

    # Dashami is present at arunodaya if the Dashami→Ekadashi crossing is AFTER arunodaya
    is_viddha = dashami_end > arunodaya
    gap_minutes = (
        (arunodaya - dashami_end).total_seconds() / 60.0
        if not is_viddha
        else -(dashami_end - arunodaya).total_seconds() / 60.0
    )

    return VedhResult(
        is_viddha=is_viddha,
        dashami_end=dashami_end,
        arunodaya=arunodaya,
        gap_minutes=gap_minutes,
        ekadashi_start=dashami_end,
        ekadashi_end=ekadashi_end,
    )


def classify(vedh, dwadashi_start, dwadashi_end):
    """
    18-classification system per SJ P3/A33.
    Ekadashi/Dwadashi duration compared to 60 ghatikas (24 hours).
    """
    ek_seconds = (vedh.ekadashi_end - vedh.ekadashi_start).total_seconds()
    dw_seconds = (dwadashi_end - dwadashi_start).total_seconds()

    ek_ghatikas = ek_seconds / (24 * 60)  # 1 ghatika = 24 minutes
    dw_ghatikas = dw_seconds / (24 * 60)

    def duration_class(g):
        if g < 59.5:
            return "Nyuna"
        elif g > 60.5:
            return "Adhika"
        return "Sama"

    ek_class = duration_class(ek_ghatikas)
    dw_class = duration_class(dw_ghatikas)
    vedh_type = "Viddha" if vedh.is_viddha else "Shuddha"

    # Classification number (1-18)
    vedh_idx = 1 if vedh.is_viddha else 0  # 0=Shuddha, 1=Viddha
    ek_idx = {"Nyuna": 0, "Sama": 1, "Adhika": 2}[ek_class]
    dw_idx = {"Nyuna": 0, "Sama": 1, "Adhika": 2}[dw_class]
    num = vedh_idx * 9 + ek_idx * 3 + dw_idx + 1

    return Classification(
        vedh_type=vedh_type,
        ekadashi_class=ek_class,
        dwadashi_class=dw_class,
        label=f"{vedh_type} {ek_class}",
        ekadashi_ghatikas=ek_ghatikas,
        dwadashi_ghatikas=dw_ghatikas,
        classification_number=num,
    )


def compute_paran(observance_date, paksha, loc):
    """
    Paran (fast-breaking) window per SJ P3/A33.
    Break fast on Dwadashi during first pahar (sunrise to 1/4 of daytime).
    """
    paran_date = observance_date + timedelta(days=1)
    paran_sunrise = get_sunrise(paran_date, loc)
    # Get sunset AFTER this sunrise (not after midnight UTC)
    paran_sunset = get_sunset(paran_sunrise, loc)

    # First pahar = first quarter of daytime
    day_length = (paran_sunset - paran_sunrise).total_seconds()
    first_pahar_end = paran_sunrise + timedelta(seconds=day_length / 4)

    # Dwadashi boundaries
    dw_start_deg = tithi_boundary_deg(paksha, 12)
    dw_end_deg = tithi_boundary_deg(paksha, 13)
    search_lo = paran_sunrise - timedelta(days=2)
    search_hi = paran_sunrise + timedelta(days=3)

    dw_start = find_elongation_crossing(dw_start_deg, search_lo, search_hi)
    dw_end = find_elongation_crossing(dw_end_deg, search_lo, search_hi)

    # Paran window
    window_start = max(paran_sunrise, dw_start)
    window_end = min(first_pahar_end, dw_end)

    if dw_end < paran_sunrise:
        # Dwadashi already ended before sunrise — break at sunrise (edge case)
        note = "Dwadashi ended before sunrise — break fast at sunrise"
        window_start = paran_sunrise
        window_end = paran_sunrise + timedelta(minutes=30)
    elif window_end <= window_start:
        # Dwadashi ends before first pahar — break before it ends
        note = "Dwadashi is short — break fast before it ends"
        window_end = dw_end
        window_start = max(paran_sunrise, dw_end - timedelta(hours=1))
    else:
        note = "Break fast after sunrise, before end of first pahar"

    return ParanResult(
        paran_date=paran_date,
        sunrise=paran_sunrise,
        window_start=window_start,
        window_end=window_end,
        dwadashi_start=dw_start,
        dwadashi_end=dw_end,
        note=note,
    )


def get_ekadashi_info(vs_month, paksha, is_adhik):
    """
    Named Ekadashi lookup per SJ P3/A35.
    Returns (name, deity, shakti, tier) or Adhik-month placeholder.
    """
    if is_adhik:
        return ("Adhik Masa Ekadashi", "Purushottam", "", "adhik")

    table = SUD_EKADASHIS if paksha in ("Sud", "sud") else VAD_EKADASHIS
    info = table.get(vs_month)
    if info:
        return info
    return ("Ekadashi", "—", "—", "all_24")


# ---------------------------------------------------------------------------
# Full analysis
# ---------------------------------------------------------------------------


@dataclass
class EkadashiAnalysis:
    date: object  # date object
    location: Location
    sunrise: datetime
    paksha: str
    tithi: int
    vs_year: int
    vs_month: str
    vs_month_display: str
    is_adhik: bool
    is_ekadashi: bool
    # Ekadashi-specific (only if is_ekadashi)
    ekadashi_name: str
    deity: str
    shakti: str
    tier: str
    vedh: VedhResult
    classification: Classification
    paran: ParanResult
    observance_date: object  # actual fast date (may differ if viddha)


def analyze_date(target_date, loc):
    """Full Ekadashi analysis for a given date and location."""
    date_dt = datetime(target_date.year, target_date.month, target_date.day)  # noqa: DTZ001
    sunrise = get_sunrise(date_dt, loc)
    paksha, tithi, elong = get_tithi(sunrise)

    month_name, display_month, is_adhik = get_lunar_month_info(sunrise)
    vs_year = get_vs_year(target_date, month_name, is_adhik)

    is_ekadashi = tithi == 11

    if not is_ekadashi:
        return EkadashiAnalysis(
            date=target_date,
            location=loc,
            sunrise=sunrise,
            paksha=paksha,
            tithi=tithi,
            vs_year=vs_year,
            vs_month=month_name,
            vs_month_display=display_month,
            is_adhik=is_adhik,
            is_ekadashi=False,
            ekadashi_name="",
            deity="",
            shakti="",
            tier="",
            vedh=None,
            classification=None,
            paran=None,
            observance_date=None,
        )

    # Ekadashi — full analysis
    name, deity, shakti, tier = get_ekadashi_info(month_name, paksha, is_adhik)
    vedh = check_vedh(sunrise, paksha, loc)
    observance_date = (
        target_date if not vedh.is_viddha else target_date + timedelta(days=1)
    )

    # Dwadashi boundaries for classification
    dw_start_deg = tithi_boundary_deg(paksha, 12)
    dw_end_deg = tithi_boundary_deg(paksha, 13)
    search_lo = sunrise - timedelta(days=2)
    search_hi = sunrise + timedelta(days=3)
    dw_start = find_elongation_crossing(dw_start_deg, search_lo, search_hi)
    dw_end = find_elongation_crossing(dw_end_deg, search_lo, search_hi)

    cls = classify(vedh, dw_start, dw_end)
    paran = compute_paran(observance_date, paksha, loc)

    return EkadashiAnalysis(
        date=target_date,
        location=loc,
        sunrise=sunrise,
        paksha=paksha,
        tithi=tithi,
        vs_year=vs_year,
        vs_month=month_name,
        vs_month_display=display_month,
        is_adhik=is_adhik,
        is_ekadashi=True,
        ekadashi_name=name,
        deity=deity,
        shakti=shakti,
        tier=tier,
        vedh=vedh,
        classification=cls,
        paran=paran,
        observance_date=observance_date,
    )


def find_next_ekadashi(start_date, loc):
    """Find the next date where tithi=11 at sunrise, starting from start_date."""
    for i in range(1, 20):
        d = start_date + timedelta(days=i)
        dt = datetime(d.year, d.month, d.day)  # noqa: DTZ001
        sr = get_sunrise(dt, loc)
        _, t, _ = get_tithi(sr)
        if t == 11:
            return d
    return None


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------

TITHI_NAMES = [
    "Pad",
    "Beej",
    "Treej",
    "Choth",
    "Pancham",
    "Chhath",
    "Satam",
    "Aatham",
    "Nom",
    "Dasham",
    "Ekadashi",
    "Baras",
    "Teras",
    "Chaudas",
    "Poonam/Amas",
]


def fmt_time(dt_utc, loc):
    """Format a UTC datetime in local time."""
    local = dt_utc.replace(tzinfo=UTC).astimezone(loc.tz)
    return local.strftime("%I:%M %p %Z").lstrip("0")


def fmt_datetime(dt_utc, loc):
    """Format a UTC datetime with date and time in local."""
    local = dt_utc.replace(tzinfo=UTC).astimezone(loc.tz)
    return local.strftime("%b %d, %I:%M %p %Z")


def print_ekadashi_analysis(a):
    """Print full Ekadashi analysis."""
    loc = a.location
    day_str = a.date.strftime("%A, %B %d, %Y")

    w = 64
    print()
    print("=" * w)
    print(f"  EKADASHI PANCHANG — {day_str}")
    print(
        f"  Location: {loc.name} ({abs(loc.lat):.2f}{'N' if loc.lat >= 0 else 'S'}, "
        f"{abs(loc.lon):.2f}{'E' if loc.lon >= 0 else 'W'})"
    )
    print("=" * w)
    print()

    paksha_full = "Sud (Shukla)" if a.paksha == "Sud" else "Vad (Krishna)"
    tithi_name = TITHI_NAMES[a.tithi - 1]
    if a.paksha == "Sud" and a.tithi == 15:
        tithi_name = "Poonam"
    elif a.paksha == "Vad" and a.tithi == 15:
        tithi_name = "Amas"

    print(
        f"  VS {a.vs_year} {a.vs_month_display} {paksha_full} {tithi_name} ({a.tithi})"
    )
    print(f"  Sunrise: {fmt_time(a.sunrise, loc)}")
    print()

    if not a.is_ekadashi:
        print("  Not an Ekadashi day.")
        print()
        nxt = find_next_ekadashi(a.date, loc)
        if nxt:
            nxt_analysis = analyze_date(nxt, loc)
            days_away = (nxt - a.date).days
            nxt_name = (
                nxt_analysis.ekadashi_name if nxt_analysis.is_ekadashi else "Ekadashi"
            )
            print(
                f"  Next Ekadashi: {nxt_analysis.vs_month_display} {nxt_analysis.paksha} — {nxt_name}"
            )
            print(
                f"    {nxt.strftime('%A, %B %d, %Y')} ({days_away} day{'s' if days_away != 1 else ''} away)"
            )
        print()
        print("=" * w)
        print()
        return

    # --- Full Ekadashi output ---
    print(f"  {a.ekadashi_name} Ekadashi")
    print(f"  Presiding Deity: {a.deity}" + (f" with {a.shakti}" if a.shakti else ""))
    series = "Keshavadi" if a.paksha == "Sud" else "Sankarshanadi"
    print(f"  Series: {series}")
    print(f"  Tier: {TIER_LABELS.get(a.tier, a.tier)}")
    print()

    # Vedh check
    v = a.vedh
    print("  VEDH CHECK (SJ P3/A33):")
    print(f"    Sunrise       : {fmt_time(a.sunrise, loc)}")
    print(f"    Arunodaya     : {fmt_time(v.arunodaya, loc)} (sunrise - 96 min)")
    print(f"    Dashami ended : {fmt_datetime(v.dashami_end, loc)}")
    if v.is_viddha:
        print(
            f"    Gap           : Dashami bled {abs(v.gap_minutes):.0f} min INTO arunodaya"
        )
        print("    Verdict       : VIDDHA — Ekadashi is contaminated")
        print(
            f"                    Fast shifts to Dwadashi ({a.observance_date.strftime('%A, %B %d')})"
        )
    else:
        print(f"    Gap           : {v.gap_minutes:.0f} min before arunodaya — clear")
        print("    Verdict       : SHUDDHA — fast today")
    print()

    # Classification
    c = a.classification
    print(f"  CLASSIFICATION: {c.label} (#{c.classification_number} of 18)")
    print(
        f"    Ekadashi duration : {c.ekadashi_ghatikas:.1f} ghatikas ({c.ekadashi_class})"
    )
    print(
        f"    Dwadashi duration : {c.dwadashi_ghatikas:.1f} ghatikas ({c.dwadashi_class})"
    )
    if v.is_viddha:
        print("    Note: Vaishnavas reject all Viddha types (SJ P3/A33)")
    print()

    # Paran
    p = a.paran
    print("  PARAN — fast-breaking (SJ P3/A33):")
    print(f"    Date          : {p.paran_date.strftime('%A, %B %d, %Y')}")
    print(f"    Sunrise       : {fmt_time(p.sunrise, loc)}")
    print(f"    Dwadashi ends : {fmt_datetime(p.dwadashi_end, loc)}")
    print(
        f"    Paran window  : {fmt_time(p.window_start, loc)} — {fmt_time(p.window_end, loc)}"
    )
    print(f"    {p.note}")
    print()

    # Practical summary
    print("  SUMMARY:")
    if v.is_viddha:
        print(
            f"    Fast on: {a.observance_date.strftime('%A, %B %d')} (Dwadashi — shifted due to vedh)"
        )
    else:
        print(f"    Fast on: {a.date.strftime('%A, %B %d')}")
    print(
        f"    Break fast: {p.paran_date.strftime('%A, %B %d')}, {fmt_time(p.window_start, loc)} — {fmt_time(p.window_end, loc)}"
    )
    if a.tier == "mandatory":
        print("    ** This is one of the 3 MANDATORY Ekadashis **")
    if a.ekadashi_name == "Prabodhini":
        print("    ** SUPREME Ekadashi — equals fruit of all 24 (SJ P3/A32 v.90) **")
    if a.ekadashi_name == "Nirjala":
        print(
            "    ** Nirjala (waterless) — strictest observance, even water prohibited **"
        )
    print()
    print("=" * w)
    print()


def print_upcoming(months, loc):
    """Print upcoming Ekadashis for N months."""
    today = datetime.now(loc.tz).date()
    end_date = today + timedelta(days=months * 30)

    # Try DB first for speed
    db_path = Path(__file__).parent / "vs_calendar_complete.db"
    ekadashi_dates = []

    if db_path.exists():
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT gregorian_date FROM vs_calendar "
            "WHERE tithi = 11 AND is_kshaya = 0 "
            "AND gregorian_date BETWEEN ? AND ? "
            "ORDER BY gregorian_date",
            (today.isoformat(), end_date.isoformat()),
        )
        ekadashi_dates = [
            datetime.strptime(row[0], "%Y-%m-%d").date()  # noqa: DTZ007
            for row in cursor.fetchall()
        ]
        conn.close()

    if not ekadashi_dates:
        # Fallback: scan day by day
        d = today
        while d <= end_date:
            dt = datetime(d.year, d.month, d.day)  # noqa: DTZ001
            sr = get_sunrise(dt, loc)
            _, t, _ = get_tithi(sr)
            if t == 11:
                ekadashi_dates.append(d)
            d += timedelta(days=1)

    w = 72
    print()
    print("=" * w)
    print(f"  UPCOMING EKADASHIS — Next {months} month{'s' if months != 1 else ''}")
    print(f"  Location: {loc.name}")
    print("=" * w)
    print()

    # DB is for Ahmedabad. For other locations, also check day before/after each DB date.
    candidate_set = set()
    for d in ekadashi_dates:
        candidate_set.add(d)
        candidate_set.add(d - timedelta(days=1))
        candidate_set.add(d + timedelta(days=1))
    # Filter to actual Ekadashis at this location
    verified = []
    for d in sorted(candidate_set):
        if d < today or d > end_date:
            continue
        a = analyze_date(d, loc)
        if a.is_ekadashi:
            verified.append((d, a))

    # Deduplicate: if a viddha Ekadashi shifts to Dwadashi on day X,
    # and day X also shows as Ekadashi at sunrise, skip the duplicate
    viddha_shift_dates = set()
    for _d, a in verified:
        if a.vedh and a.vedh.is_viddha and a.observance_date:
            viddha_shift_dates.add(a.observance_date)

    num = 0
    for d, a in verified:
        if d in viddha_shift_dates and not (a.vedh and a.vedh.is_viddha):
            continue  # Skip — this date is covered by the viddha shift above
        num += 1

        vedh_mark = " *VIDDHA*" if a.vedh and a.vedh.is_viddha else ""
        tier_mark = ""
        if a.tier == "mandatory":
            tier_mark = " [MANDATORY]"
        elif a.tier == "chaturmas":
            tier_mark = " [chaturmas]"

        print(
            f"  {num:>2}. {d.strftime('%b %d, %Y  %a'):>20}  "
            f"{a.vs_month_display:>12} {a.paksha}  "
            f"{a.ekadashi_name:<14}{vedh_mark}{tier_mark}"
        )

        if a.vedh and a.vedh.is_viddha:
            obs = a.observance_date
            print(f"      -> Fast shifts to Dwadashi: {obs.strftime('%b %d, %Y  %a')}")

    has_viddha = any(a.vedh and a.vedh.is_viddha for _, a in verified)
    print()
    if has_viddha:
        print(
            "  * VIDDHA = Dashami vedh contaminates Ekadashi; fast on Dwadashi instead"
        )
    print()
    print("=" * w)
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def resolve_location(loc_str):
    """Resolve a location string (preset key or LAT,LON[,ELEV,TZ]) to a Location."""
    if not loc_str:
        return None
    key = loc_str.strip().lower().replace(" ", "").replace(",", "")
    if loc_str in LOCATIONS:
        return LOCATIONS[loc_str]
    if key in LOCATIONS:
        return LOCATIONS[key]
    # Try parsing as LAT,LON[,ELEV,TZ]
    if "," in loc_str:
        parts = loc_str.split(",")
        if len(parts) >= 2:
            try:
                lat, lon = float(parts[0]), float(parts[1])
            except ValueError:
                return None
            elev = float(parts[2]) if len(parts) > 2 and parts[2] else 0
            tz_name = parts[3] if len(parts) > 3 else "UTC"
            return Location(
                f"Custom ({lat:.2f}, {lon:.2f})", lat, lon, elev, ZoneInfo(tz_name)
            )
    return None


def prompt_for_location():
    """Interactively ask the user for a location (used when none is supplied)."""
    print()
    print("Where are you? (this decides which day you actually fast)")
    print()
    print(list_locations())
    print()
    while True:
        choice = input("Enter a city name or LAT,LON[,ELEV,TZ]: ").strip()
        if not choice:
            print(f"  Using default: {DEFAULT_LOCATION}")
            return LOCATIONS[DEFAULT_LOCATION]
        loc = resolve_location(choice)
        if loc:
            return loc
        print(f"  Unknown location '{choice}'. Try again (see the list above).")


def parse_location(args, *, allow_prompt=True):
    """Parse --location argument into a Location object, prompting if absent."""
    raw = getattr(args, "location", None)
    # Distinguish "user asked for the default" from "user gave nothing"
    supplied = raw is not None and raw != DEFAULT_LOCATION
    loc = resolve_location(raw)
    if loc is not None:
        return loc
    if supplied:
        # A real value was given but didn't resolve — that's an error, not a prompt
        print(f"Unknown location: {raw}")
        print(f"Run 'python ekadashi_panchang.py locations' to see the presets,")
        print("or pass LAT,LON[,ELEV,TIMEZONE].")
        sys.exit(1)
    if allow_prompt and sys.stdin.isatty():
        return prompt_for_location()
    return LOCATIONS[DEFAULT_LOCATION]


def main():
    parser = argparse.ArgumentParser(
        description="Swaminarayan Ekadashi Panchang — SJ P3/A31-36 rules",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--location",
        "-l",
        default=None,
        help="City preset (e.g. fremont, ahmedabad) or LAT,LON[,ELEV,TZ]",
    )

    sub = parser.add_subparsers(dest="command")

    # Add --location to each subparser so it can go after the subcommand
    loc_kwargs = {
        "default": None,
        "help": "City preset (e.g. fremont, ahmedabad) or LAT,LON[,ELEV,TZ]",
    }

    p_today = sub.add_parser("today", help="Is today Ekadashi? Full analysis.")
    p_today.add_argument("--location", "-l", **loc_kwargs)

    p_next = sub.add_parser("next", help="When is the next Ekadashi?")
    p_next.add_argument("--location", "-l", **loc_kwargs)

    p_check = sub.add_parser("check", help="Analyze a specific date.")
    p_check.add_argument("date", help="Date in YYYY-MM-DD format")
    p_check.add_argument("--location", "-l", **loc_kwargs)

    p_upcoming = sub.add_parser("upcoming", help="Upcoming Ekadashis.")
    p_upcoming.add_argument(
        "months",
        nargs="?",
        type=int,
        default=3,
        help="Number of months to show (default: 3)",
    )
    p_upcoming.add_argument("--location", "-l", **loc_kwargs)

    sub.add_parser("locations", help="List all built-in city presets.")

    args = parser.parse_args()

    if args.command == "locations":
        print()
        print("Built-in locations (pass with --location <key>):")
        print()
        print(list_locations())
        print()
        return

    loc = parse_location(args)

    if args.command == "today" or args.command is None:
        today = datetime.now(loc.tz).date()
        a = analyze_date(today, loc)
        print_ekadashi_analysis(a)

    elif args.command == "next":
        today = datetime.now(loc.tz).date()
        # Check today first
        a_today = analyze_date(today, loc)
        if a_today.is_ekadashi:
            print_ekadashi_analysis(a_today)
            return

        nxt = find_next_ekadashi(today, loc)
        if nxt:
            a = analyze_date(nxt, loc)
            print_ekadashi_analysis(a)
        else:
            print("Could not find next Ekadashi within 20 days.")

    elif args.command == "check":
        target = datetime.strptime(args.date, "%Y-%m-%d").date()  # noqa: DTZ007
        a = analyze_date(target, loc)
        print_ekadashi_analysis(a)

    elif args.command == "upcoming":
        print_upcoming(args.months, loc)


if __name__ == "__main__":
    main()
