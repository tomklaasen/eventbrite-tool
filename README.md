# Eventbrite Report Tool

Generates a report for your next upcoming Eventbrite event. The report includes the event title, date, location, total number of registrations, and a list of confirmed attendees (first name, last name, company) sorted alphabetically by first name.

Three output files are written to the `output/` folder:

| File | Description |
|------|-------------|
| `report_<date>_<title>.md` | Markdown report |
| `report_<date>_<title>.pdf` | PDF version of the report |
| `report_<date>_<title>.csv` | Attendee list as a spreadsheet |

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

```bash
./start.sh
```

This activates the virtual environment and runs the script. Output files are saved to the `output/` folder.
