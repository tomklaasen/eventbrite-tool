# Eventbrite Report Tool

Generates reports for Eventbrite events. Per-event reports include the event title, date, location, optional speaker info, total number of registrations, and a list of confirmed attendees (first name, last name, company, diet restrictions) sorted alphabetically by first name. Diet restrictions are pulled from the Eventbrite custom question containing "dieet". An attendance overview report shows how many events each person has attended across all past events.

The following files are written to the `output/` folder:

| File | Description |
|------|-------------|
| `report_<date>_<title>.md` | Markdown report |
| `report_<date>_<title>.pdf` | PDF version of the report |
| `report_<date>_<title>_speaker.pdf` | PDF for speakers (without diet column) |
| `report_<date>_<title>.csv` | Attendee list as a spreadsheet |
| `badges.lbx` | Badge template for Brother P-touch Editor (mail merge) |
| `badges.csv` | Attendee data used by the badge template |

### Printing badges

Open `badges.lbx` in **Brother P-touch Editor**. On first use, P-touch may ask you to locate `badges.csv` — click **Reopen** and select the file from the `output/` folder. Once you save the file after doing this, P-touch will remember the location for all future runs.

To print all badges, go to **File > Print** and select **Print All Records**.

## Requirements

- Python 3
- An [Eventbrite API token](https://www.eventbrite.com/platform/api-keys)

On macOS, `weasyprint` (used for PDF generation) requires a couple of system libraries. If the install fails, run:

```bash
brew install pango libffi
```

## Setup

1. **Create and activate a virtual environment, and install dependencies:**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install requests python-dotenv markdown weasyprint
```

2. **Configure your API token:**

```bash
cp .env.example .env
```

Open `.env` and replace `your_private_token_here` with your actual Eventbrite API token.

## Usage

**Next upcoming event** (generates report + badges):
```bash
./start.sh
```

**All past events** (generates reports only, no badges):
```bash
source .venv/bin/activate
python3 generate_report.py --past
```

**Attendance overview** across all past events:
```bash
source .venv/bin/activate
python3 generate_report.py --attendance
```

Generates `output/attendance_report.md/pdf/csv` with each unique attendee ranked by number of events attended.

### Merging name duplicates

If the same person appears under slightly different names (typos, missing accents), create a `name_mappings.json` file (gitignored — copy from `name_mappings.example.json`) and add entries mapping the wrong spelling to the correct one:

```json
{
  "Jon Doe": "John Doe"
}
```

### Speaker info

To show a speaker's name and company in the report header and as the first badge, create a `speakers.json` file (gitignored — copy from `speakers.example.json`):

```json
{
  "1234567890": {
    "event": "CTO Club: Example Event",
    "date": "2026-01-15",
    "first_name": "Jan",
    "last_name": "Janssens",
    "company": "Acme Corp"
  }
}
```

The key is the Eventbrite event ID. When you run the script, it prints the event ID and automatically adds an empty entry to `speakers.json` for any event that doesn't have one yet — just fill in the name and company and re-run.

Output files are saved to the `output/` folder.

## Daily digest email

`daily_digest.py` sends an email when new registrations have come in since the last run. It only sends when there is something new.

The email shows:
- The new registrations since the last run
- The full attendee list with the current total

### Setup

1. **Create a Gmail App Password:**
   - Go to your Google Account → Security → 2-Step Verification → App passwords
   - Generate a new app password for "Mail"

2. **Add to your `.env`:**

```
GMAIL_USER=you@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
DIGEST_TO=recipient@example.com
```

3. **Prime the snapshot** by running once manually — this records all current registrations as known so only future registrations are treated as new:

```bash
./start_digest.sh
```

4. **Schedule with cron** (`crontab -e`):

```
0 18 * * * /path/to/eventbrite-tool/start_digest.sh >> /tmp/eventbrite_digest.log 2>&1
```

The snapshot is saved to `output/snapshot_<event_id>.json` and updated on each run.

### Monitoring with healthchecks.io

To monitor the cron job, create a check at [healthchecks.io](https://healthchecks.io), set its schedule to match your cron interval, and add the ping URL to `.env`:

```
HEALTHCHECKS_URL=https://hc-ping.com/your-uuid-here
```

The script pings `/start` when it begins, the base URL on success (whether or not an email was sent), and `/fail` if an exception occurs.
