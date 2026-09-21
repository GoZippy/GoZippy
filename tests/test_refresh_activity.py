"""Privacy, provenance and atomic-write tests; no network requests."""

import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "scripts/refresh_activity.py"
SPEC = importlib.util.spec_from_file_location("refresh_activity", SOURCE)
activity = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(activity)
START, END, CAPTURED = "2026-09-18", "2026-09-20", "2026-09-21T01:00:00Z"


def fixture():
    return {
        "data": {
            "viewer": {"login": "GoZippy"},
            "user": {
                "login": "GoZippy",
                "contributionsCollection": {
                    "startedAt": START + "T00:00:00Z",
                    "endedAt": END + "T23:59:59Z",
                    "restrictedContributionsCount": 2,
                    "contributionCalendar": {
                        "totalContributions": 6,
                        "weeks": [
                            {
                                "contributionDays": [
                                    {"date": START, "contributionCount": 1},
                                    {"date": "2026-09-19", "contributionCount": 2},
                                    {"date": END, "contributionCount": 3},
                                ]
                            }
                        ],
                    },
                },
            },
        }
    }


def normalized(payload=None):
    return activity.normalize(
        fixture() if payload is None else payload,
        expected_login="GoZippy",
        start=START,
        end=END,
        captured_at=CAPTURED,
    )


def collection(payload):
    return payload["data"]["user"]["contributionsCollection"]


class NormalizeTests(unittest.TestCase):
    def test_allowlist_discards_private_fields_at_every_depth(self):
        value = fixture()
        value["privateRepository"] = "PRIVATE_SENTINEL"
        value["data"]["viewer"]["email"] = "PRIVATE_SENTINEL"
        user = value["data"]["user"]
        user["repositories"] = [{"name": "PRIVATE_SENTINEL", "url": "PRIVATE_SENTINEL"}]
        col = collection(value)
        col["commitContributionsByRepository"] = {"commit": "PRIVATE_SENTINEL"}
        col["contributionCalendar"]["private"] = "PRIVATE_SENTINEL"
        days = col["contributionCalendar"]["weeks"][0]["contributionDays"]
        days[0]["commitMessage"] = "PRIVATE_SENTINEL"
        result = normalized(value)
        self.assertEqual(set(result), activity.OUTPUT_KEYS)
        self.assertEqual(set(result["window"]), {"start", "end"})
        self.assertEqual(set(result["daily"][0]), {"date", "count"})
        self.assertNotIn("PRIVATE_SENTINEL", json.dumps(result))
        self.assertEqual(result, normalized())

    def test_deterministic_sort_and_case_insensitive_identity(self):
        value = fixture()
        value["data"]["viewer"]["login"] = "gozippy"
        collection(value)["contributionCalendar"]["weeks"][0][
            "contributionDays"
        ].reverse()
        self.assertEqual(normalized(value), normalized())

    def test_missing_or_null_restricted_is_unknown(self):
        value = fixture()
        del collection(value)["restrictedContributionsCount"]
        self.assertIsNone(normalized(value)["restricted_contributions"])
        collection(value)["restrictedContributionsCount"] = None
        self.assertIsNone(normalized(value)["restricted_contributions"])
        collection(value)["restrictedContributionsCount"] = 0
        self.assertEqual(normalized(value)["restricted_contributions"], 0)

    def test_missing_calendar_or_total_never_fabricates_zero(self):
        for field in ("contributionCalendar",):
            value = fixture()
            del collection(value)[field]
            with self.assertRaises(activity.ActivityError):
                normalized(value)
        value = fixture()
        del collection(value)["contributionCalendar"]["totalContributions"]
        with self.assertRaises(activity.ActivityError):
            normalized(value)

    def test_wrong_user_or_owner_rejected(self):
        for identity in ("viewer", "user"):
            value = fixture()
            value["data"][identity]["login"] = "other-owner"
            with self.assertRaises(activity.ActivityError):
                normalized(value)

    def test_unavailable_or_error_payload_rejected(self):
        for value in (
            None,
            [],
            {},
            {"data": None},
            {"data": {"user": None}},
            {**fixture(), "errors": [{"message": "PRIVATE_SENTINEL"}]},
        ):
            with self.subTest(value_type=type(value).__name__), self.assertRaises(
                activity.ActivityError
            ):
                normalized(value if value is not None else {"data": None})

    def test_invalid_count_types_rejected(self):
        for bad in (True, False, -1, 2.5, "2", None, float("nan"), 2147483648):
            for location in ("total", "day", "restricted"):
                if bad is None and location == "restricted":
                    continue
                value = fixture()
                col = collection(value)
                if location == "total":
                    col["contributionCalendar"]["totalContributions"] = bad
                elif location == "restricted":
                    col["restrictedContributionsCount"] = bad
                else:
                    col["contributionCalendar"]["weeks"][0]["contributionDays"][0][
                        "contributionCount"
                    ] = bad
                with self.subTest(location=location, bad=bad), self.assertRaises(
                    activity.ActivityError
                ):
                    normalized(value)

    def test_invalid_dates_duplicates_missing_days_and_total_mismatch(self):
        for bad in (
            "2026-09-31",
            "2026-9-18",
            "2026-09-17",
            "2026-09-19",
            "PRIVATE_SENTINEL",
        ):
            value = fixture()
            collection(value)["contributionCalendar"]["weeks"][0]["contributionDays"][
                0
            ]["date"] = bad
            with self.subTest(bad=bad), self.assertRaises(activity.ActivityError):
                normalized(value)
        value = fixture()
        collection(value)["contributionCalendar"]["weeks"][0]["contributionDays"].pop()
        with self.assertRaises(activity.ActivityError):
            normalized(value)
        value = fixture()
        collection(value)["contributionCalendar"]["totalContributions"] = 999
        with self.assertRaises(activity.ActivityError):
            normalized(value)

    def test_response_window_and_capture_must_match(self):
        value = fixture()
        collection(value)["startedAt"] = "2026-09-17T00:00:00Z"
        with self.assertRaises(activity.ActivityError):
            normalized(value)
        for stamp in (
            "2026-09-20T01:00:00Z",
            "2026-09-21",
            "2026-09-21T01:00:00+01:00",
        ):
            with self.assertRaises(activity.ActivityError):
                activity.normalize(
                    fixture(),
                    expected_login="GoZippy",
                    start=START,
                    end=END,
                    captured_at=stamp,
                )

    def test_window_bounds(self):
        for start, end in ((END, START), ("2024-01-01", END), ("bad", END)):
            with self.assertRaises(activity.ActivityError):
                activity.checked_window(start, end)


class StorageAndTransportTests(unittest.TestCase):
    def test_successful_atomic_write_contains_only_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "data/activity.json"
            activity.atomic_write(target, normalized())
            self.assertEqual(json.loads(target.read_text()), normalized())
            self.assertEqual(list(target.parent.iterdir()), [target])

    def test_failed_replace_preserves_previous_file_and_removes_temp(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "activity.json"
            target.write_bytes(b"previous snapshot")
            with patch.object(
                activity.os, "replace", side_effect=OSError("PRIVATE_SENTINEL")
            ):
                with self.assertRaises(OSError):
                    activity.atomic_write(target, normalized())
            self.assertEqual(target.read_bytes(), b"previous snapshot")
            self.assertEqual(list(target.parent.iterdir()), [target])

    def test_failed_fetch_or_normalization_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "activity.json"
            target.write_bytes(b"previous snapshot")
            for value in (
                {"data": None},
                {**fixture(), "errors": [{"message": "PRIVATE_SENTINEL"}]},
            ):
                with patch.object(activity, "fetch_graphql", return_value=value), patch(
                    "sys.stderr", new_callable=io.StringIO
                ) as output:
                    self.assertEqual(
                        activity.main(
                            [
                                "--fetch",
                                "--start",
                                START,
                                "--end",
                                END,
                                "--output",
                                str(target),
                            ]
                        ),
                        2,
                    )
                    self.assertNotIn("PRIVATE_SENTINEL", output.getvalue())
                self.assertEqual(target.read_bytes(), b"previous snapshot")

    def test_gh_request_has_only_allowed_query_and_no_token_argument(self):
        fake = subprocess.CompletedProcess(
            [], 0, stdout=json.dumps(fixture()).encode(), stderr=b""
        )
        with patch.dict(os.environ, {"GH_DEBUG": "api"}, clear=True), patch.object(
            activity.subprocess, "run", return_value=fake
        ) as run:
            self.assertEqual(activity.fetch_graphql("GoZippy", START, END), fixture())
            args, kwargs = run.call_args
            self.assertEqual(
                args[0],
                ["gh", "api", "--hostname", "github.com", "graphql", "--input", "-"],
            )
            request = json.loads(kwargs["input"])
            self.assertEqual(request["query"], activity.QUERY)
            self.assertEqual(request["variables"]["login"], "GoZippy")
            self.assertNotIn("GH_DEBUG", kwargs["env"])
            self.assertFalse(kwargs["shell"])
            for forbidden in (
                "repositories",
                "commitContributions",
                "message",
                "email",
                "url",
            ):
                self.assertNotIn(forbidden, activity.QUERY)

    def test_gh_failure_never_relays_stderr(self):
        bad = subprocess.CompletedProcess([], 1, stdout=b"", stderr=b"PRIVATE_SENTINEL")
        with patch.dict(os.environ, {}, clear=True), patch.object(
            activity.subprocess, "run", return_value=bad
        ):
            with self.assertRaisesRegex(
                activity.ActivityError, "^github_request_failed$"
            ):
                activity.fetch_graphql("GoZippy", START, END)

    def test_explicit_token_uses_header_not_process_or_output(self):
        response = io.BytesIO(json.dumps(fixture()).encode())
        with patch.dict(
            os.environ, {"TEST_ACTIVITY_TOKEN": "synthetic-secret"}, clear=True
        ), patch.object(
            activity.urllib.request, "build_opener"
        ) as opener, patch.object(
            activity.subprocess, "run"
        ) as run:
            opener.return_value.open.return_value = response
            result = activity.fetch_graphql(
                "GoZippy", START, END, token_env="TEST_ACTIVITY_TOKEN"
            )
            request = opener.return_value.open.call_args.args[0]
            self.assertEqual(
                request.get_header("Authorization"), "Bearer synthetic-secret"
            )
            self.assertEqual(request.full_url, activity.ENDPOINT)
            self.assertNotIn("synthetic-secret", request.data.decode())
            self.assertNotIn("synthetic-secret", json.dumps(result))
            run.assert_not_called()

    def test_missing_explicit_token_does_not_fall_back(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(
            activity.subprocess, "run"
        ) as run:
            with self.assertRaisesRegex(
                activity.ActivityError, "token_environment_unavailable"
            ):
                activity.fetch_graphql(
                    "GoZippy", START, END, token_env="TEST_ACTIVITY_TOKEN"
                )
            run.assert_not_called()

    def test_redirects_refused_and_response_size_bounded(self):
        with self.assertRaisesRegex(activity.ActivityError, "github_redirect_refused"):
            activity.NoRedirect().redirect_request(
                None, None, 302, "", {}, "https://elsewhere.invalid"
            )
        fake = subprocess.CompletedProcess(
            [], 0, stdout=b"x" * (activity.MAX_RESPONSE_BYTES + 1), stderr=b""
        )
        with patch.dict(os.environ, {}, clear=True), patch.object(
            activity.subprocess, "run", return_value=fake
        ):
            with self.assertRaisesRegex(
                activity.ActivityError, "github_response_too_large"
            ):
                activity.fetch_graphql("GoZippy", START, END)

    def test_no_fetch_flag_means_no_network_or_write(self):
        with patch.object(activity, "fetch_graphql") as fetch, patch(
            "sys.stderr", new_callable=io.StringIO
        ):
            with self.assertRaises(SystemExit):
                activity.main([])
            fetch.assert_not_called()

    def test_invalid_arguments_do_not_echo_accidental_token(self):
        with patch("sys.stderr", new_callable=io.StringIO) as output:
            with self.assertRaises(SystemExit):
                activity.main(["--unknown-token-option", "PRIVATE_SENTINEL"])
            self.assertNotIn("PRIVATE_SENTINEL", output.getvalue())


if __name__ == "__main__":
    unittest.main()
