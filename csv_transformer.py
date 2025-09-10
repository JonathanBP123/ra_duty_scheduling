import csv
import datetime

INPUT_FILE = "google_form_export.csv"
OUTPUT_FILE = "ra_prefs.csv"

MONTHS = {
    "Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,
    "Jul":7,"Aug":8,"Sep":9,"Sept":9,"Oct":10,"Nov":11,"Dec":12
}

def parse_weekend_unavailable(raw):
    """Convert 'Sat Sept 27, Fri Oct 17' -> ISO dates"""
    if not raw or raw.strip() == "":
        return ""
    dates = []
    for token in raw.split(","):
        token = token.strip()
        parts = token.split()
        if len(parts) >= 3:
            month = MONTHS[parts[1][:3]]
            day = int(parts[2])
            # Assume year is 2025 fall quarter
            dt = datetime.date(2025, month, day)
            dates.append(dt.isoformat())
    return ";".join(dates)

def normalize_pref(raw):
    """Map Google Form responses -> First/Second/Third/Not Available"""
    if not raw:
        return "Not Available"
    raw = raw.strip()
    if raw.startswith("First"):
        return "First"
    if raw.startswith("Second"):
        return "Second"
    if raw.startswith("Third"):
        return "Third"
    if raw.startswith("Not Available"):
        return "Not Available"
    return "Not Available"

with open(INPUT_FILE, newline="") as infile, open(OUTPUT_FILE, "w", newline="") as outfile:
    reader = csv.DictReader(infile)
    fieldnames = [
        "ra_id","name","home_area","home_area_pref","block_pref",
        "Sun","Mon","Tue","Wed","Thu",
        "blackout_dates","weekend_unavailable"
    ]
    writer = csv.DictWriter(outfile, fieldnames=fieldnames)
    writer.writeheader()

    for row in reader:
        first = row["First Name"].strip()
        last = row["Last Name"].strip()
        ra_id = (first[0] + last).lower().replace(" ", "")
        name = f"{first} {last}"

        outrow = {
            "ra_id": ra_id,
            "name": name,
            "home_area": row.get("Home Area", "").strip(),
            "home_area_pref": row["Preference for NE1 vs NE2?"].strip(),
            "block_pref": "Yes" if "Yes" in row["Preference for block scheduling?"] else "No",
            "Sun": normalize_pref(row["Sunday's"]),
            "Mon": normalize_pref(row["Monday's"]),
            "Tue": normalize_pref(row["Tuesday's"]),
            "Wed": normalize_pref(row["Wednesday's"]),
            "Thu": normalize_pref(row["Thursday's"]),
            "blackout_dates": row.get("Are there any weeks/weekdays during the quarter that you can not work?", "").strip(),
            "weekend_unavailable": parse_weekend_unavailable(row.get("What weekend shifts can you not work?"))
        }

        writer.writerow(outrow)

print(f"✅ Export complete: {OUTPUT_FILE}")
