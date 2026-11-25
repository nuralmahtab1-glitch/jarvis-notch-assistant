import io, json
from datetime import datetime, timezone
import pytest
from app.core import widgets as w

NOON_UTC = datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc)


def test_parse_clocks_drops_bad_zones_and_limits_to_four():
    got = w.parse_clocks(["London=Europe/London", "Nowhere=Mars/Olympus", "=Asia/Tokyo", "NoZone", "Tokyo=Asia/Tokyo",
                          "A=UTC", "B=UTC", "C=UTC"])
    assert got[0] == ("London", "Europe/London") and ("Nowhere", "Mars/Olympus") not in got and len(got) == 4


def test_clock_rows_times_and_day_markers():
    rows = w.clock_rows([("Tokyo", "Asia/Tokyo"), ("London", "Europe/London"), ("LA", "America/Los_Angeles")], NOON_UTC)
    by = {r["city"]: r for r in rows}
    assert by["Tokyo"]["time"] == "21:00" and by["London"]["time"] == "12:00" and by["LA"]["time"] == "04:00"
    assert by["Tokyo"]["night"] is True and by["London"]["night"] is False and by["LA"]["night"] is True


def test_day_marker_across_midnight():
    late = datetime(2026, 11, 25, 22, 0, tzinfo=timezone.utc)
    here_day = late.astimezone().date()
    rows = w.clock_rows([("Tokyo", "Asia/Tokyo")], late)               # 07:00 the next day in Tokyo
    expected_diff = (late.astimezone(w.ZoneInfo("Asia/Tokyo")).date() - here_day).days
    assert rows[0]["day"] == {1: "Tomorrow", 0: "Today", -1: "Yesterday"}[expected_diff]


def test_zone_lookup_prefers_your_clock_labels_then_the_builtin_list():
    mine = [("Home", "Asia/Dhaka")]
    assert w.zone_for("home", mine) == ("Home", "Asia/Dhaka")
    assert w.zone_for("Tokyo", mine) == ("Tokyo", "Asia/Tokyo")
    assert w.zone_for("  new   york ", mine)[1] == "America/New_York"
    assert w.zone_for("atlantis", mine) is None


def test_time_in_sentence():
    s = w.time_in("tokyo", [], NOON_UTC)
    assert s.startswith("It is 9:00 PM") and s.endswith("in Tokyo.")
    assert w.time_in("atlantis", [], NOON_UTC) is None


OPEN_METEO = {"current": {"temperature_2m": 17.6, "weather_code": 61, "is_day": 0},
              "daily": {"temperature_2m_max": [19.2], "temperature_2m_min": [11.4]}}


def test_parse_weather():
    x = w.parse_weather(OPEN_METEO, "London, GB", "C")
    assert (x.temp, x.high, x.low, x.text, x.night) == (18, 19, 11, "Light rain", True)
    assert "18 degrees" in x.sentence() and "light rain" in x.sentence() and "London, GB" in x.sentence()


@pytest.mark.parametrize("bad", [{}, {"current": {}}, {"current": {"temperature_2m": 1, "weather_code": 0}, "daily": {}}, None])
def test_parse_weather_survives_garbage(bad):
    assert (w.parse_weather(bad, "x", "C") if bad is not None else None) is None


class Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): pass


def fake_opener(payloads, seen):
    def op(req, timeout=0):
        seen.append(req.full_url)
        return Resp(json.dumps(payloads.pop(0)).encode())
    return op


def test_geocode_sends_only_the_city_name():
    seen = []
    g = w.geocode("London", fake_opener([{"results": [{"name": "London", "country_code": "GB", "latitude": 51.5, "longitude": -0.12}]}], seen))
    assert g == {"name": "London, GB", "lat": 51.5, "lon": -0.12}
    assert "name=London" in seen[0] and "ip" not in seen[0].lower().split("?")[1]


def test_geocode_unknown_city_and_blank():
    assert w.geocode("zzzxxyy", fake_opener([{}], [])) is None
    assert w.geocode("   ") is None


def test_fetch_weather_url_and_units():
    seen = []
    x = w.fetch_weather(51.5074, -0.1278, "London, GB", "F", fake_opener([OPEN_METEO], seen))
    assert x.unit == "F" and "temperature_unit=fahrenheit" in seen[0] and "latitude=51.507" in seen[0]


def test_network_failure_returns_none_not_an_exception():
    def boom(req, timeout=0): raise OSError("offline")
    assert w.fetch_weather(1, 2, "x", "C", boom) is None and w.geocode("London", boom) is None


def test_every_weather_code_has_a_visible_symbol_and_night_clear_is_a_moon():
    in_icon_font = lambda s: any(0xE000 <= ord(ch) <= 0xF8FF for ch in s)       # the private-use area the icon font lives in
    assert all(sym and not in_icon_font(sym) for _, sym in w.WMO.values())     # emoji, not missing icon-font codes
    clear_night = {"current": {"temperature_2m": 3, "weather_code": 0, "is_day": 0}, "daily": {"temperature_2m_max": [5], "temperature_2m_min": [1]}}
    assert w.parse_weather(clear_night, "x", "C").glyph == w.NIGHT_CLEAR
    day = dict(clear_night, current={"temperature_2m": 3, "weather_code": 0, "is_day": 1})
    assert w.parse_weather(day, "x", "C").glyph == "☀️"
