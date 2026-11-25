"""Now-playing from Windows media sessions + synced lyrics from LRCLIB. Made by Nur Al Mahtab.

Privacy: lyrics lookups send only the track title, artist and length to lrclib.net, once per song,
and can be turned off (settings: lyrics). Nothing you say is ever sent.
"""
from __future__ import annotations
import asyncio, json, re, threading, time, urllib.parse, urllib.request
from typing import Callable

LRC_LINE = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\]\s*(.*)")


def parse_lrc(text: str) -> list[tuple[float, str]]:
    out = []
    for line in (text or "").splitlines():
        m = LRC_LINE.match(line.strip())
        if m:
            out.append((int(m.group(1)) * 60 + float(m.group(2)), m.group(3).strip()))
    return sorted(out)


def lyric_window(lines: list[tuple[float, str]], pos: float) -> list[str]:
    """[previous, current, next] lyric lines at playback position `pos` (seconds)."""
    if not lines:
        return ["", "", ""]
    i = -1
    for k, (t, _) in enumerate(lines):
        if t <= pos:
            i = k
        else:
            break
    get = lambda k: lines[k][1] if 0 <= k < len(lines) else ""
    return [get(i - 1), get(i) if i >= 0 else "", get(i + 1)]


def fetch_lyrics(title: str, artist: str, duration: float | None, timeout: float = 6.0) -> list[tuple[float, str]]:
    q = {"track_name": title, "artist_name": artist}
    if duration:
        q["duration"] = str(int(duration))
    url = "https://lrclib.net/api/get?" + urllib.parse.urlencode(q)
    req = urllib.request.Request(url, headers={"User-Agent": "Jarvis-notch/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return parse_lrc(json.loads(r.read().decode("utf-8")).get("syncedLyrics") or "")
    except Exception:
        return []


class MediaWatcher:
    def __init__(self, on_update: Callable[[dict], None], on_track_change: Callable[[dict], None] | None = None,
                 lyrics: bool = True):
        self.on_update, self.on_track_change, self.use_lyrics = on_update, on_track_change, lyrics
        self._stop = threading.Event()
        self._lyrics: dict[str, list] = {}
        self._last_key = None
        self.state: dict = {"playing": False, "title": "", "artist": "", "pos": 0.0, "dur": 0.0, "lyrics": ["", "", ""]}

    def start(self):
        threading.Thread(target=lambda: asyncio.run(self._run()), daemon=True).start()

    def stop(self):
        self._stop.set()

    async def _poll(self, mgr):
        s = mgr.get_current_session()
        if not s:
            return {"playing": False, "title": "", "artist": "", "pos": 0.0, "dur": 0.0}
        info = await s.try_get_media_properties_async()
        pb, tl = s.get_playback_info(), s.get_timeline_properties()
        playing = int(pb.playback_status) == 4          # PLAYING
        pos = tl.position.total_seconds()
        if playing:                                      # position is a snapshot: extrapolate
            try:
                pos += max(0.0, time.time() - tl.last_updated_time.timestamp())
            except Exception:
                pass
        return {"playing": playing, "title": info.title or "", "artist": info.artist or "",
                "pos": pos, "dur": tl.end_time.total_seconds()}

    async def _run(self):
        try:
            from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as M
            mgr = await M.request_async()
        except Exception as e:
            print("[media]", e)
            return
        while not self._stop.is_set():
            try:
                st = await self._poll(mgr)
                key = (st["title"], st["artist"])
                if st["title"] and key != self._last_key:
                    self._last_key = key
                    if self.use_lyrics and key not in self._lyrics:
                        self._lyrics[key] = []
                        threading.Thread(target=self._load_lyrics, args=(key, st["dur"]), daemon=True).start()
                    if self.on_track_change and st["playing"]:
                        self.on_track_change(st)
                st["lyrics"] = lyric_window(self._lyrics.get(key, []), st["pos"])
                self.state = st
                self.on_update(st)
            except Exception as e:
                print("[media poll]", e)
            await asyncio.sleep(1.0)

    def _load_lyrics(self, key, dur):
        self._lyrics[key] = fetch_lyrics(key[0], key[1], dur)
