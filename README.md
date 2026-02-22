# Eventbrite Report Tool

Generates reports for Eventbrite events. Per-event reports include the event title, date, location, total number of registrations, and a list of confirmed attendees (first name, last name, company, diet restrictions) sorted alphabetically by first name. Diet restrictions are pulled from the Eventbrite custom question containing "dieet". An attendance overview report shows how many events each person has attended across all past events.

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

Output files are saved to the `output/` folder.
