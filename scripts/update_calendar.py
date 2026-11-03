import re
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

# --- Sources ---
FOMC_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"

NOW = datetime.now(timezone.utc)

# Major macro keywords to keep from BLS/BEA
MAJOR_KEYWORDS = [
    "Consumer Price Index",  # CPI
    "Employment Situation",  # Nonfarm Payrolls
    "Producer Price Index",  # PPI
    "Gross Domestic Product",  # GDP
    "Personal Income and Outlays",  # PCE-ish
]

MONTH_MAP = {
    "January": 1,
    "February": 2,
    "March": 3,
    "April": 4,
    "May": 5,
    "June": 6,
    "July": 7,
    "August": 8,
    "September": 9,
    "October": 10,
    "November": 11,
    "December": 12,
}


# ---------- Scraping Fed FOMC page ----------


def scrape_fomc_events():
    """
    Scrape FOMC meeting dates from the Fed's official calendar page.
    Dynamically detects all 'YYYY FOMC Meetings' sections instead of using
    a hard-coded year list.

    Steps:
      - fetch the page
      - detect all year headers like '2026 FOMC Meetings'
      - for each year section, find patterns: 'Month  DD-DD' (optional '*')
      - use the SECOND day as the policy decision date
      - make all-day events for those dates, only if >= NOW
      - deduplicate meeting dates in case the pattern appears more than once
    """
    resp = requests.get(FOMC_URL, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    text = soup.get_text("\n")

    now_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    # 1) Find all 'YYYY FOMC Meetings' headers dynamically
    year_header_re = re.compile(r"(\d{4}) FOMC Meetings")
    year_matches = list(year_header_re.finditer(text))

    # Extract years and keep them sorted & unique
    years_to_scan = sorted({int(m.group(1)) for m in year_matches})

    # Optionally, only scan years from "now on" to avoid ancient data
    current_year = datetime.now(timezone.utc).year
    years_to_scan = [y for y in years_to_scan if y >= current_year]

    # Precompile month+day-range pattern, e.g. "January 27-28*"
    month_pattern = (
        r"(January|February|March|April|May|June|July|August|September|October|November|December)"
        r"[^\d]{0,20}"
        r"(\d{1,2})-(\d{1,2})\*?"  # start-end, optional '*'
    )
    month_re = re.compile(month_pattern)

    events = []
    seen_dates = set()  # YYYYMMDD strings to avoid duplicates

    for year in years_to_scan:
        header = f"{year} FOMC Meetings"
        idx = text.find(header)
        if idx == -1:
            continue

        # Bound this section by the next year's header or end of text
        end_idx = len(text)
        for other_year in [int(year) - 1]:
            other_header = f"{other_year} FOMC Meetings"
            tmp = text.find(other_header)
            if tmp != -1 and tmp > idx:
                end_idx = min(end_idx, tmp)

        section = text[idx:end_idx]

        for m in month_re.finditer(section):
            month_name, _day1_str, day2_str = m.groups()
            month = MONTH_MAP[month_name]
            day2 = int(day2_str)

            try:
                dt = datetime(year, month, day2, tzinfo=timezone.utc)
            except ValueError:
                continue

            if dt < NOW:
                continue

            date_key = dt.strftime("%Y%m%d")
            if date_key in seen_dates:
                # Avoid duplicates (e.g., if pattern appears twice in the text)
                continue
            seen_dates.add(date_key)
            if date_key == "20261103":
                print(
                    "Warning: FOMC meeting date is today; ensure the calendar is up to date."
                )
                print(years_to_scan)
                # print(section)
                # print(end_idx)

            uid = f"FOMC-{date_key}@us-macro"
            ev = [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{now_str}",
                f"DTSTART;VALUE=DATE:{date_key}",
                "SUMMARY:FOMC Meeting – Rate Decision",
                (
                    "DESCRIPTION:Federal Open Market Committee meeting "
                    "(second day, policy statement expected). "
                    f"(Source: Federal Reserve FOMC calendar, {year})"
                ),
                "END:VEVENT",
            ]
            events.append(ev)

    return events


# ---------- Main entrypoint ----------


def main():
    # Fed FOMC meetings scraped live
    fomc_events = scrape_fomc_events()

    header = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//YourGitHubUser//US Macro Calendar//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:US Macro Major Events",
    ]
    footer = ["END:VCALENDAR"]

    with open("us_macro.ics", "w", encoding="utf-8") as f:
        lines = header
        lines += [l for ev in fomc_events for l in ev]
        lines += footer
        f.writelines([line + "\n" for line in lines])


if __name__ == "__main__":
    main()
