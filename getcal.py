#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import sys
import subprocess
from html import escape
from pathlib import Path
from typing import Optional, Sequence, Tuple

try:
    from importlib import metadata as importlib_metadata
except ImportError:  # pragma: no cover - Python <3.8 fallback
    import importlib_metadata  # type: ignore

from tzlocal import get_localzone_name
from zoneinfo import ZoneInfo
if not hasattr(importlib_metadata, "packages_distributions"):
    def _packages_distributions_stub():
        return {}

    importlib_metadata.packages_distributions = _packages_distributions_stub  # type: ignore[attr-defined]

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
APP_VERSION = "0.3.0"
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
BASE_DIR = Path(__file__).resolve().parent
CREDENTIALS_FILE = BASE_DIR / "credentials.json"
TOKEN_FILE = BASE_DIR / "token.json"
LOCAL_TZ_NAME = get_localzone_name()
LOCAL_TZ = ZoneInfo(LOCAL_TZ_NAME)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch Google Calendar events for a given day."
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"getcal {APP_VERSION}",
        help="Show the tool version and exit.",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Fail instead of opening a browser if OAuth consent is required.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print results to stdout instead of copying them to the clipboard.",
    )
    parser.add_argument(
        "date",
        nargs="?",
        help="ISO date (YYYY-MM-DD). Defaults to today if omitted.",
    )
    return parser


def ensure_credentials_file() -> Path:
    if not CREDENTIALS_FILE.exists():
        raise SystemExit(
            "credentials.json not found. Download the OAuth desktop client secret "
            f"and place it at {CREDENTIALS_FILE}."
        )
    return CREDENTIALS_FILE


def get_credentials(interactive: bool) -> Credentials:
    creds: Optional[Credentials] = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN_FILE.write_text(creds.to_json())
        return creds

    if not interactive:
        raise SystemExit(
            "OAuth consent required but --non-interactive flag was provided. "
            "Run again without --non-interactive to authorize."
        )

    ensure_credentials_file()
    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
    creds = flow.run_local_server(port=0)
    TOKEN_FILE.write_text(creds.to_json())
    return creds


def build_calendar_service(creds: Credentials):
    # cache_discovery avoids relying on importlib.metadata features missing on older Python
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def fetch_events_for_day(service, day: dt.date) -> list[dict]:
    local_start = dt.datetime.combine(day, dt.time.min, tzinfo=LOCAL_TZ)
    local_end = local_start + dt.timedelta(days=1)
    result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=local_start.isoformat(),
            timeMax=local_end.isoformat(),
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    return result.get("items", [])


def extract_event_fields(event: dict) -> Tuple[str, str, str]:
    start = event.get("start", {})
    start_value = format_start_time(start)
    summary = event.get("summary") or "(no title)"
    html_link = event.get("htmlLink") or ""
    return start_value, summary, html_link


def format_start_time(start: dict) -> str:
    raw_dt = start.get("dateTime")
    raw_date = start.get("date")
    if raw_dt:
        try:
            parsed = dt.datetime.fromisoformat(raw_dt)
        except ValueError:
            return f"{raw_dt} (raw)"
        local_dt = parsed.astimezone(LOCAL_TZ)
        tz_label = local_dt.tzname() or LOCAL_TZ_NAME
        return f"{local_dt.strftime('%Y-%m-%d %H:%M')} ({tz_label})"
    if raw_date:
        return f"{raw_date} (all-day)"
    return "?"


def format_events_text(events: list[dict]) -> str:
    if not events:
        return "No events."
    blocks = []
    for event in events:
        start_value, summary, html_link = extract_event_fields(event)
        link_text = f"[{summary}]({html_link})" if html_link else summary
        blocks.append(f"{start_value} - {link_text}")
    return "\n".join(blocks)


def format_events_html(events: list[dict]) -> str:
    if not events:
        return "<p>No events.</p>"
    parts = ["<html><body>"]
    for event in events:
        start_value, summary, html_link = extract_event_fields(event)
        start_html = escape(start_value)
        summary_html = escape(summary)
        if html_link:
            link_html = f'<a href="{escape(html_link)}">{summary_html}</a>'
        else:
            link_html = summary_html
        parts.append(f"<p><strong>{start_html}</strong> - {link_html}</p>")
    parts.append("</body></html>")
    return "".join(parts)


def convert_html_to_rtf(html: str) -> bytes:
    try:
        result = subprocess.run(
            [
                "textutil",
                "-convert",
                "rtf",
                "-stdin",
                "-stdout",
                "-format",
                "html",
            ],
            input=html.encode("utf-8"),
            capture_output=True,
            check=True,
        )
    except FileNotFoundError as exc:  # pragma: no cover
        raise SystemExit(
            "textutil not found. Install Xcode command line tools to enable rich-text clipboard."
        ) from exc
    return result.stdout


def copy_plain_text(text: str) -> None:
    try:
        subprocess.run(
            ["pbcopy"],
            input=text.encode("utf-8"),
            check=True,
        )
    except FileNotFoundError as exc:  # pragma: no cover - macOS specific
        raise SystemExit("pbcopy not found. Install macOS command line tools or use --dry-run.") from exc
    except subprocess.CalledProcessError as exc:  # pragma: no cover - unlikely
        raise SystemExit(f"Failed to copy to clipboard: {exc}") from exc


def copy_to_clipboard(plain_text: str, html_text: str) -> None:
    try:
        rtf_bytes = convert_html_to_rtf(html_text)
    except SystemExit:
        print("Falling back to plain-text clipboard copy.", file=sys.stderr)
        copy_plain_text(plain_text)
        return
    except subprocess.CalledProcessError as exc:
        print(
            f"Failed to convert HTML to RTF ({exc.stderr.decode().strip()}), using plain text.",
            file=sys.stderr,
        )
        copy_plain_text(plain_text)
        return

    try:
        subprocess.run(["pbcopy", "-Prefer", "rtf"], input=rtf_bytes, check=True)
    except FileNotFoundError as exc:  # pragma: no cover
        raise SystemExit("pbcopy not found. Install macOS command line tools or use --dry-run.") from exc
    except subprocess.CalledProcessError as exc:  # pragma: no cover
        raise SystemExit(f"Failed to copy RTF to clipboard: {exc}") from exc


def parse_date(date_str: Optional[str]) -> dt.date:
    if not date_str:
        return dt.date.today()
    try:
        return dt.date.fromisoformat(date_str)
    except ValueError as exc:  # pragma: no cover - CLI handling
        raise SystemExit(f"Invalid date '{date_str}': {exc}") from exc


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        creds = get_credentials(interactive=not args.non_interactive)
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        raise

    service = build_calendar_service(creds)
    target_day = parse_date(args.date)
    events = fetch_events_for_day(service, target_day)
    plain_output = format_events_text(events)
    html_output = format_events_html(events)
    event_count = len(events)
    print(f"Fetched {event_count} event(s) for {target_day}:")
    if args.dry_run:
        print(plain_output)
        return

    copy_to_clipboard(plain_output, html_output)
    print(f"Copied {event_count} event(s) for {target_day} to clipboard.")


if __name__ == "__main__":
    main()
