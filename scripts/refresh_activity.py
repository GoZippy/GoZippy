"""Fetch only an owner-visible GitHub contribution aggregate; never repository details."""

from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

ENDPOINT = "https://api.github.com/graphql"
MAX_RESPONSE_BYTES = 1024 * 1024
SCOPE = (
    "Authenticated owner-visible GitHub contribution-calendar aggregate; may include "
    "public and private activity visible to this viewer. GitHub's restricted count "
    "means contributions inaccessible to the viewer, not an exact private/public "
    "split. No repository names, URLs, commits, messages, or contribution details "
    "are requested or retained. Missing restricted count is null, not zero."
)
QUERY = """query ProfileActivity($login: String!, $from: DateTime!, $to: DateTime!) {
  viewer { login }
  user(login: $login) {
    login
    contributionsCollection(from: $from, to: $to) {
      startedAt
      endedAt
      restrictedContributionsCount
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}"""
OUTPUT_KEYS = {
    "source",
    "captured_at",
    "window",
    "total_contributions",
    "daily",
    "restricted_contributions",
    "scope",
}


class ActivityError(ValueError):
    """A bounded, non-sensitive diagnostic code."""


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # Even a mistakenly pasted credential in an unknown option must not echo.
        self.exit(2, "Invalid arguments; use --help. No request or write performed.\n")


def parse_day(value: object) -> date:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ActivityError("invalid_date")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ActivityError("invalid_date") from None


def parse_utc(value: object) -> datetime:
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value
    ):
        raise ActivityError("invalid_utc_timestamp")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        raise ActivityError("invalid_utc_timestamp") from None


def utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def valid_login(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", value
    ):
        raise ActivityError("invalid_login")
    return value


def count(value: object) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 <= value <= 2147483647
    ):
        raise ActivityError("invalid_count")
    return value


def checked_window(start: str, end: str) -> tuple[date, date]:
    first, last = parse_day(start), parse_day(end)
    if not 0 <= (last - first).days <= 364:
        raise ActivityError("invalid_window")
    return first, last


def normalize(
    payload: object, *, expected_login: str, start: str, end: str, captured_at: str
) -> dict:
    """Return only allowlisted scalars, deterministically; reject incomplete calendars."""
    expected_login = valid_login(expected_login)
    first, last = checked_window(start, end)
    captured = parse_utc(captured_at)
    if last >= captured.date():
        raise ActivityError("window_requires_completed_utc_days")
    if not isinstance(payload, dict) or payload.get("errors"):
        raise ActivityError("github_response_unavailable")
    try:
        data = payload["data"]
        viewer = valid_login(data["viewer"]["login"])
        user = data["user"]
        login = valid_login(user["login"])
        if (
            viewer.casefold() != expected_login.casefold()
            or login.casefold() != expected_login.casefold()
        ):
            raise ActivityError("owner_identity_mismatch")
        collection = user["contributionsCollection"]
        started = parse_utc(collection["startedAt"])
        ended = parse_utc(collection["endedAt"])
        if started != datetime.combine(
            first, time.min, timezone.utc
        ) or ended != datetime.combine(last, time(23, 59, 59), timezone.utc):
            raise ActivityError("response_window_mismatch")
        calendar = collection["contributionCalendar"]
        total = count(calendar["totalContributions"])
        weeks = calendar["weeks"]
        if not isinstance(weeks, list) or not 1 <= len(weeks) <= 54:
            raise ActivityError("calendar_unavailable")
        daily = {}
        for week in weeks:
            days = week["contributionDays"]
            if not isinstance(days, list) or not 1 <= len(days) <= 7:
                raise ActivityError("invalid_calendar_week")
            for day in days:
                when = parse_day(day["date"])
                if when < first or when > last or when in daily:
                    raise ActivityError("invalid_calendar_dates")
                daily[when] = count(day["contributionCount"])
        if len(daily) != (last - first).days + 1:
            raise ActivityError("incomplete_calendar")
        if sum(daily.values()) != total:
            raise ActivityError("calendar_total_mismatch")
        restricted_raw = collection.get("restrictedContributionsCount")
        restricted = None if restricted_raw is None else count(restricted_raw)
        if restricted is not None and restricted > total:
            raise ActivityError("restricted_count_exceeds_total")
    except (KeyError, TypeError, AttributeError):
        raise ActivityError("github_response_unavailable") from None
    # Never spread or copy input objects: private fields at any depth are discarded.
    return {
        "source": ENDPOINT,
        "captured_at": utc_text(captured),
        "window": {"start": first.isoformat(), "end": last.isoformat()},
        "total_contributions": total,
        "daily": [
            {"date": day.isoformat(), "count": daily[day]} for day in sorted(daily)
        ],
        "restricted_contributions": restricted,
        "scope": SCOPE,
    }


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ActivityError("github_redirect_refused")


def fetch_graphql(
    login: str, start: str, end: str, *, token_env: str | None = None
) -> dict:
    valid_login(login)
    first, last = checked_window(start, end)
    body = json.dumps(
        {
            "query": QUERY,
            "variables": {
                "login": login,
                "from": utc_text(datetime.combine(first, time.min, timezone.utc)),
                "to": utc_text(datetime.combine(last, time(23, 59, 59), timezone.utc)),
            },
        }
    ).encode("utf-8")
    if token_env is not None:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", token_env):
            raise ActivityError("invalid_token_environment_name")
        token = os.environ.get(token_env)
        if not token:
            raise ActivityError("token_environment_unavailable")
    else:
        token = next(
            (
                os.environ[name]
                for name in ("ACTIVITY_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN")
                if os.environ.get(name)
            ),
            None,
        )
    try:
        if token:
            request = urllib.request.Request(
                ENDPOINT,
                data=body,
                headers={
                    "Authorization": "Bearer " + token,
                    "Accept": "application/vnd.github+json",
                    "Content-Type": "application/json",
                    "User-Agent": "zippy-profile-aggregate-adapter",
                },
                method="POST",
            )
            with urllib.request.build_opener(NoRedirect()).open(
                request, timeout=45
            ) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        else:
            environment = os.environ.copy()
            environment.pop("GH_DEBUG", None)
            environment.update({"GH_PROMPT_DISABLED": "1", "GIT_TERMINAL_PROMPT": "0"})
            result = subprocess.run(
                ["gh", "api", "--hostname", "github.com", "graphql", "--input", "-"],
                input=body,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=45,
                check=False,
                shell=False,
                env=environment,
            )
            if result.returncode:
                raise ActivityError("github_request_failed")
            raw = result.stdout
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ActivityError("github_response_too_large")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ActivityError("github_response_unavailable")
        return payload
    except ActivityError:
        raise
    except (OSError, ValueError, subprocess.SubprocessError, urllib.error.URLError):
        # Do not relay HTTP bodies, gh stderr, request headers or exception strings.
        raise ActivityError("github_request_failed") from None


def atomic_write(output: Path, snapshot: dict) -> None:
    if set(snapshot) != OUTPUT_KEYS:
        raise ActivityError("unexpected_output_fields")
    encoded = (
        json.dumps(snapshot, indent=2, ensure_ascii=True, allow_nan=False) + "\n"
    ).encode("utf-8")
    output = Path(output).absolute()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=".activity-",
            suffix=".tmp",
            dir=output.parent,
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = SafeArgumentParser(description=__doc__)
    parser.add_argument(
        "--fetch",
        action="store_true",
        help="Explicitly authorize this live, read-only fetch",
    )
    parser.add_argument("--login", default="GoZippy")
    parser.add_argument(
        "--start", help="Inclusive UTC date; paired with --end, at most 365 days"
    )
    parser.add_argument("--end", help="Inclusive completed UTC date")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data/activity.json",
    )
    parser.add_argument(
        "--token-env",
        help="Name of environment variable containing token; never token text",
    )
    args = parser.parse_args(argv)
    if not args.fetch:
        parser.error("--fetch is required; no network request or write performed")
    try:
        if bool(args.start) != bool(args.end):
            raise ActivityError("start_and_end_required_together")
        captured = datetime.now(timezone.utc).replace(microsecond=0)
        end = args.end or (captured.date() - timedelta(days=1)).isoformat()
        start = args.start or (parse_day(end) - timedelta(days=364)).isoformat()
        checked_window(start, end)
        if parse_day(end) >= captured.date():
            raise ActivityError("window_requires_completed_utc_days")
        payload = fetch_graphql(args.login, start, end, token_env=args.token_env)
        snapshot = normalize(
            payload,
            expected_login=args.login,
            start=start,
            end=end,
            captured_at=utc_text(captured),
        )
        atomic_write(args.output, snapshot)
        print(json.dumps({"status": "snapshot_saved", "days": len(snapshot["daily"])}))
        return 0
    except (ActivityError, OSError, ValueError):
        # Deliberately never print raw exception text, paths, or API response data.
        print(
            '{"status":"failed","code":"activity_refresh_failed","previous_snapshot_preserved":true}',
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
