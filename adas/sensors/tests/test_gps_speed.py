"""Unit tests for the GPS speed parser (no serial port or Pi needed)."""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from gps_speed import nmea_checksum_ok, rmc_speed_kmh, shown_speed  # noqa: E402


def sentence(body: str) -> str:
    """Wrap an NMEA body in $...*hh with a correct checksum."""
    calc = 0
    for ch in body:
        calc ^= ord(ch)
    return f"${body}*{calc:02X}"


# Captured from the NEO-6M on the bench, indoors (no lock).
NO_LOCK = "$GPRMC,095105.00,V,,,,,,,181126,,,N*78"


def test_captured_line_has_a_good_checksum():
    assert nmea_checksum_ok(NO_LOCK)


def test_no_lock_gives_no_speed():
    assert rmc_speed_kmh(NO_LOCK) is None


def test_locked_rmc_gives_kmh():
    line = sentence("GPRMC,101500.00,A,1345.12345,N,10030.54321,E,27.000,90.0,181126,,,A")
    assert abs(rmc_speed_kmh(line) - 27.0 * 1.852) < 1e-9


def test_gn_talker_is_accepted():
    line = sentence("GNRMC,101500.00,A,1345.12345,N,10030.54321,E,10.0,90.0,181126,,,A")
    assert abs(rmc_speed_kmh(line) - 18.52) < 1e-9


def test_mode_n_means_not_valid():
    line = sentence("GPRMC,101500.00,A,1345.12345,N,10030.54321,E,10.0,90.0,181126,,,N")
    assert rmc_speed_kmh(line) is None


def test_bad_checksum_is_ignored():
    line = sentence("GPRMC,101500.00,A,1345.12345,N,10030.54321,E,27.000,90.0,181126,,,A")
    assert rmc_speed_kmh(line[:-2] + "00") is None


def test_other_sentences_are_ignored():
    assert rmc_speed_kmh("$GPGGA,095105.00,,,,,0,00,99.99,,,,,,*6E") is None
    assert rmc_speed_kmh("garbage") is None


def test_empty_speed_field_is_ignored():
    line = sentence("GPRMC,101500.00,A,1345.12345,N,10030.54321,E,,90.0,181126,,,A")
    assert rmc_speed_kmh(line) is None


def test_standing_still_drift_reads_zero():
    assert shown_speed(1.4) == 0.0
    assert shown_speed(2.99) == 0.0
    assert shown_speed(3.0) == 3.0
    assert shown_speed(50.04) == 50.0
