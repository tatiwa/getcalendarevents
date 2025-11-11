# Google Calendar Day Exporter

- **Goal**: Grab all events for a single day, including start time, title, and event link, then push the formatted text into the macOS clipboard.
- **Main pieces**:
  - Python script that wraps Google Calendar API v3.
  - OAuth credential cache (`credentials.json` + `token.json`).
  - Clipboard handoff via `pbcopy`.
  - Optional macOS Quick Action or Shortcut for GUI launching and date prompt.

## Implementation Outline

- **Environment**
  - Python 3.11+ and `pip`.
  - Install libraries: `google-api-python-client`, `google-auth-httplib2`, `google-auth-oauthlib`, `tzlocal`.
  - macOS `pbcopy` and `textutil` (Command Line Tools) must be available so the clipboard can receive rich-text (RTF) with hyperlinks.
  - Store script and OAuth files together inside the project directory.

- **OAuth Flow**
  - Download `credentials.json` from Google Cloud Console (Desktop app client).
  - First run serves the consent screen; tokens persist in `token.json`.
  - Subsequent runs refresh silently; no browser needed unless the token expires.

- **Script Structure**
  - Arguments: optional ISO date (`YYYY-MM-DD`), defaulting to today.
  - Build Calendar service with cached credentials.
  - Query primary calendar for `timeMin`/`timeMax` covering the entire local day (system timezone via `tzlocal`/`zoneinfo` so DST is respected).
  - Iterate results; format `start`, `summary`, `htmlLink`, showing times converted to the local timezone with its abbreviation.
  - Join rows with newline separators; fall back to "No events." when empty.
  - Pipe output to `pbcopy` and echo a short confirmation to STDOUT.

- **macOS Integration**
  - Wrap script via Automator Quick Action or Shortcuts:
    - Prompt user for date.
    - Execute `/usr/bin/python3 path/to/script.py <date>`.
    - Show optional notification once clipboard is updated.
  - Alternate: package with Platypus for a double-clickable app.

- **Testing Strategy**
  - Run the script against known calendar entries (create a throwaway calendar for fixtures) and confirm clipboard output matches expected rows.
  - Exercise edge cases: no events, overlapping events, all-day events, cancelled events, daylight-savings transitions.
  - Verify repeated executions reuse `token.json` without prompting; deliberately delete/expire the token to confirm refresh flow.
  - Smoke test Automator/Shortcut wrapper: ensure date prompt feeds the script, clipboard updates, and notifications display.
  - Optional: add a dry-run flag that prints to STDOUT instead of `pbcopy` for easier automated assertions.

- **Incremental Build & Test Plan**
  - Step 1: Scaffold Python environment, install dependencies, and create a minimal script that authenticates and prints a hello message; test with `python script.py --help`.
  - Step 2: Implement OAuth token handling (`credentials.json` + `token.json`); first run should launch consent, subsequent run verifies silent reuse.
  - Step 3: Add event-fetch logic for a fixed date, dumping raw JSON to confirm API responses; test with a day containing known events (today's run can return `[]` if no events are scheduled).
  - Step 4: Introduce command-line date argument (`python getcal.py 2025-01-01`) and consistency checks; test with valid, missing, and malformed dates.
  - Step 5: Format output as multi-line blocks (`timestamp` newline `title (link)`), add "No events." fallback; test against days with zero and multiple events, verify clipboard via dry-run mode.
  - Step 6: Wire `pbcopy` integration plus a `--dry-run` flag; test by copying to clipboard (default) and with `--dry-run` to keep terminal output only.
  - Step 7: Build an Automator Quick Action (or Shortcuts automation) that prompts for a date, runs `macos/quick_action.sh`, and ensure clipboard output shows up in GUI workflows.
  - Step 8: Document usage, maintenance, and troubleshooting; rerun full suite (script + wrapper) after any refinements.

- **Quality-of-life Tweaks (future)**
  - Convert event times into local timezone with `dateutil`.
  - Support multiple calendars or custom `calendarId`.
  - Append location/attendees to clipboard payload.
  - Emit Markdown or rich text for note apps.

## Usage

- **CLI**
  - Activate the virtualenv: `source .venv/bin/activate`.
  - Run for today: `python getcal.py`.
  - Run for a specific day: `python getcal.py 2025-11-01`.
  - Dry run (keeps output in terminal): `python getcal.py --dry-run 2025-11-01`.
  - Non-interactive automation (fails if OAuth needed): `python getcal.py --non-interactive 2025-11-01`.
  - Sample clipboard flow: `python getcal.py 2025-11-01 && pbpaste`.
  - All start times are converted to your system timezone and show the abbreviation (e.g., `2025-10-31 20:30 (PST)`).
  - Each event prints on one line: `timestamp - [Title](https://event-link)`; the clipboard copy also pushes rich-text (RTF) so Google Docs/Notes get clickable links.
- **Quick Action**
  - Install workflow to `~/Library/Services/Copy Calendar Events.workflow` (already versioned in `macos/`).
  - Launch via Services menu or assigned shortcut; dialog prompts for date.
  - Optional env overrides (set before invoking workflow or script):
    - `GETCAL_DEFAULT_DATE=2025-11-01` to skip the dialog.
    - `GETCAL_DRY_RUN=1` to avoid altering the clipboard (useful for testing).
  - Direct script invocation: `GETCAL_DEFAULT_DATE=2025-11-01 GETCAL_DRY_RUN=1 macos/quick_action.sh`.

## Troubleshooting

- **Missing `credentials.json`**: Download the OAuth client secret and place it next to `getcal.py`. The CLI exits with a clear error if the file is missing.
- **Consent blocked (`access_denied`)**: Add your account under `APIs & Services → OAuth consent screen → Test users` and retry.
- **API not enabled**: Enable “Google Calendar API” under `APIs & Services → Library`.
- **`pbcopy not found`**: Install Xcode command line tools or run with `--dry-run` until macOS clipboard utilities are available.
- **Rich-text copy failed**: Ensure `textutil` exists (Command Line Tools). If conversion fails, the script falls back to plain text and logs a warning.
- **Token revoked/expired**: Delete `token.json` and rerun interactively to obtain a fresh token.
- **Automator workflow fails**: Verify `macos/quick_action.sh` and `.venv` paths inside the script; run it manually with `GETCAL_DEFAULT_DATE=<date> macos/quick_action.sh` to see the error.
- **LibreSSL/OpenSSL warnings**: Upgrading to Python ≥3.13 via `uv` removes the fatal issues; warnings can be ignored for local use.

## Automator Quick Action Notes (Step 7 Prep)

- Launch `Automator.app` → `New Document` → `Quick Action`.
- Workflow receives `no input` in `any application`.
- Add a single action: `Run Shell Script` with `/bin/zsh`, pass input as `arguments`, contents: `"$HOME/dev/codex/getcalendarevents/macos/quick_action.sh" "$@"`.
- The helper script:
  - Falls back to the first CLI argument or `GETCAL_DEFAULT_DATE` when provided (handy for scripted tests).
  - Tries a JXA/Cocoa date picker (`macos/date_picker.js`) so the user gets a proper calendar control; if Automation permissions or GUI access are unavailable, it falls back to the original text dialog and, as a last resort, a terminal prompt.
  - Adds `--dry-run` when `GETCAL_DRY_RUN=1`.
  - Activates `.venv`, runs `python getcal.py <date>`, and surfaces the CLI output/exit status.
- Save as "Copy Calendar Events". Assign a keyboard shortcut via System Settings → Keyboard → Keyboard Shortcuts → Services.
- Test by invoking the Quick Action from Finder/Services, choosing a date from the picker, and pasting to verify clipboard contents.

## Google Cloud Setup Checklist

Follow these exact UI labels in the Google Cloud console (https://console.cloud.google.com):

1. **Create/Select Project**
   - Top navigation bar → project drop-down → `New Project` (or pick an existing one). Give it a name such as `getcalendarevents`.
   - Once created, ensure the project is selected in the header.

2. **Create OAuth Client ID (Desktop)**
   - Left nav: `APIs & Services` → `Credentials`.
   - If prompted, the console will ask you to configure the consent screen first (see Step 3). Complete that flow, then return here.
   - Click `+ CREATE CREDENTIALS` → `OAuth client ID`.
   - Application type: `Desktop app`. Name it (e.g., `getcal`), then `Create`.
   - Click `Download JSON`. Rename the file to `credentials.json` and place it in the project root next to `getcal.py`.

3. **Enable Google Calendar API**
   - Left nav: `APIs & Services` → `Library`.
   - Search for **Google Calendar API**.
   - Click the result, then press `Enable`.

4. **Configure OAuth Consent Screen**
   - Left nav: `APIs & Services` → `OAuth consent screen`.
   - User type: `External`, then `Create`.
   - Fill **App name**, **User support email**, and **Developer contact information**.
   - Under `Scopes`, click `Add or Remove Scopes`, search for *calendar*, and add `.../auth/calendar.readonly`.
   - Under `Test users`, click `Add users` and enter every Google account that should run the script.
   - `Save and Continue` until the summary page, then `Back to Dashboard`.

5. **Verify Access**
   - Run the script without `--non-interactive`. The browser consent screen should show the app name you entered, list the calendar scope, and allow only the test users you configured.
   - After consent, `token.json` appears locally; future runs reuse it silently unless revoked.
