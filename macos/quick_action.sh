#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKDIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_PATH="$WORKDIR/.venv/bin/activate"

if [[ ! -d "$WORKDIR" ]]; then
  echo "Workflow error: $WORKDIR not found" >&2
  exit 1
fi

if [[ ! -f "$VENV_PATH" ]]; then
  echo "Workflow error: virtualenv activate script missing at $VENV_PATH" >&2
  exit 1
fi

selected_date="${1:-}"
if [[ -z "$selected_date" ]]; then
  selected_date="${GETCAL_DEFAULT_DATE:-}"
fi

if [[ -z "$selected_date" ]]; then
  JXA_SCRIPT="$WORKDIR/macos/date_picker.js"
  if [[ -f "$JXA_SCRIPT" ]]; then
    set +e
    picker_output=$(/usr/bin/osascript -l JavaScript "$JXA_SCRIPT")
    picker_status=$?
    set -e
    if [[ $picker_status -eq 0 ]]; then
      if [[ "$picker_output" == "__CANCELLED__" ]]; then
        echo "Copy Calendar Events cancelled." >&2
        exit 1
      elif [[ "$picker_output" == __ERROR__:* ]]; then
        echo "JXA date picker failed ($picker_output); falling back to text dialog." >&2
      elif [[ -n "$picker_output" ]]; then
        selected_date="$picker_output"
      fi
    else
      echo "JXA date picker exited with $picker_status; falling back to text dialog." >&2
    fi
  fi
fi

if [[ -z "$selected_date" ]]; then
  set +e
  osascript_output=$(/usr/bin/osascript \
    -e 'set defaultDate to do shell script "date +%F"' \
    -e 'try' \
    -e '    set dialogResult to display dialog "Date (YYYY-MM-DD)" default answer defaultDate buttons {"Cancel", "Copy"} default button "Copy"' \
    -e '    text returned of dialogResult' \
    -e 'on error number -128' \
    -e '    error number -128' \
    -e 'end try')
  osascript_status=$?
  set -e
  if [[ $osascript_status -ne 0 ]]; then
    echo "Copy Calendar Events cancelled." >&2
    exit 1
  fi
  selected_date="$osascript_output"
fi

if [[ -z "$selected_date" ]]; then
  if [[ -t 0 ]]; then
    read -r -p "Date (YYYY-MM-DD): " selected_date
  else
    echo "No date supplied; set GETCAL_DEFAULT_DATE or provide an argument." >&2
    exit 1
  fi
fi

selected_date="${selected_date//$'\r'/}"
selected_date="${selected_date//$'\n'/}"
if [[ -z "$selected_date" ]]; then
  selected_date=$(date +%F)
fi

python_args=()
if [[ "${GETCAL_DRY_RUN:-}" == "1" ]]; then
  python_args+=(--dry-run)
fi

source "$VENV_PATH"
cd "$WORKDIR"
if (( ${#python_args[@]} > 0 )); then
  python getcal.py "${python_args[@]}" "$selected_date"
else
  python getcal.py "$selected_date"
fi
