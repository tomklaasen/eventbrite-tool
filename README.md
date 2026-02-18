# Eventbrite Report Tool

Generates a report for your next upcoming Eventbrite event. The report includes the event title, date, location, total number of registrations, and a list of confirmed attendees (first name, last name, company) sorted alphabetically by first name.

The following files are written to the `output/` folder:

| File | Description |
|------|-------------|
| `report_<date>_<title>.md` | Markdown report |
| `report_<date>_<title>.pdf` | PDF version of the report |
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

Output files are saved to the `output/` folder.
