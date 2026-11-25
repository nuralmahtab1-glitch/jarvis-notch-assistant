"""Dictation clean-up: fillers, self-corrections, bullets, punctuation. Made by Nur Al Mahtab.

clean(text) -> str. Also diff_marks(raw) returns the raw words flagged as removed, so the notch can
show them struck through before the final text lands.
"""
from __future__ import annotations
import re

FILLERS = r"(?:um+|uh+|erm+|er|ah|hmm+|you know|i mean|like,)"
SELF_CORRECT = re.compile(
    r"(?P<old>\b[\w'\-:]+(?:\s[\w'\-:]+){0,1})\s*[,.]?\s*(?:actually|no wait|no,? i mean|i mean|sorry|rather)[,.]?\s+(?P<new>[\w'\-:]+(?:\s[\w'\-:]+){0,1})",
    re.I)
SCRATCH = re.compile(r"[^.!?]*?\b(?:scratch that|delete that|ignore that)\b[,.!]?\s*", re.I)
NUMBER_WORDS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
                "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
                "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
                "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50}
SPOKEN_PUNCT = [(r"\bnew paragraph\b", "\n\n"), (r"\bnew line\b", "\n"), (r"\bfull stop\b", "."),
                (r"\bcomma\b", ","), (r"\bquestion mark\b", "?"), (r"\bexclamation (mark|point)\b", "!"),
                (r"\bcolon\b", ":"), (r"\bsemicolon\b", ";"), (r"\bopen quote\b", '"'), (r"\bclose quote\b", '"')]


def _words_to_number(w: str) -> str:
    return str(NUMBER_WORDS[w.lower()]) if w.lower() in NUMBER_WORDS else w


def remove_fillers(text: str) -> str:
    t = re.sub(rf"(?<![\w']){FILLERS}(?![\w'])[,.]?\s*", "", text, flags=re.I)
    return re.sub(r"\s{2,}", " ", t).strip()


def apply_corrections(text: str) -> str:
    """'about ten, actually fifteen minutes' -> 'about fifteen minutes'."""
    t = text
    for _ in range(6):
        m = SELF_CORRECT.search(t)
        if not m:
            break
        old_w, new_w = m.group("old").split(), m.group("new").split()
        keep = old_w[:-len(new_w)] if len(new_w) <= len(old_w) else []
        repl = " ".join(keep + new_w)
        pre = t[:m.start()]
        if not keep:
            pre = re.sub(r",\s*$", " ", pre)   # "about, ten, actually fifteen" -> "about fifteen"
        t = pre + repl + t[m.end():]
    return re.sub(r"\s{2,}", " ", t)


def apply_scratch(text: str) -> str:
    """'send it tonight. scratch that send it tomorrow' -> 'send it tomorrow'."""
    pat = re.compile(r"\b(?:scratch that|delete that|ignore that)\b[,.!]?\s*", re.I)
    while True:
        m = pat.search(text)
        if not m:
            return text.strip()
        left = text[:m.start()].rstrip()
        # drop the previous sentence (or the whole clause if there is only one)
        body = left[:-1] if left[-1:] in (".", "?", "!") else left
        cut = max(body.rfind(". "), body.rfind("? "), body.rfind("! "))
        left = left[:cut + 1] if cut >= 0 else ""
        text = (left + " " + text[m.end():]).strip()


def bulletize(text: str) -> str:
    if not re.search(r"\bbullet point\b|\bnumbered list\b|\bnext item\b", text, re.I):
        return text
    lead, *items = re.split(r"\bbullet point\b[,.:]?\s*", text, flags=re.I)
    out = []
    for it in items:
        it = it.strip(" ,.;")
        if it:
            out.append("- " + it[0].upper() + it[1:])
    prefix = lead.strip()
    return (prefix + "\n\n" if prefix else "") + "\n".join(out)


def punctuate(text: str) -> str:
    for pat, rep in SPOKEN_PUNCT:
        text = re.sub(rf"\s*{pat}\s*", rep + (" " if rep in ".,?!:;" else ""), text, flags=re.I)
    text = re.sub(r"\s+([.,?!:;])", r"\1", text)
    lines = []
    for line in text.split("\n"):
        s = line.strip()
        if not s or s.startswith("- "):
            lines.append(line)
            continue
        s = re.sub(r"(^|[.?!]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), s)
        s = re.sub(r"\bi\b", "I", s)
        s = re.sub(r"\bi'(m|ll|ve|d)\b", lambda m: "I'" + m.group(1), s)
        if s[-1] not in ".?!:\"')":
            s += "."
        lines.append(s)
    return "\n".join(lines)


def clean(text: str) -> str:
    t = text.strip()
    if not t:
        return ""
    t = apply_scratch(t)
    t = remove_fillers(t)
    t = apply_corrections(t)
    t = bulletize(t)
    t = punctuate(t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    return t.strip()


def diff_marks(raw: str) -> list[tuple[str, bool]]:
    """Return [(word, removed?)] so the UI can strike fillers through."""
    cleaned = remove_fillers(raw)
    out = []
    for w in raw.split():
        bare = re.sub(r"[^\w']", "", w).lower()
        out.append((w, bool(re.fullmatch(FILLERS, bare, re.I)) and bare not in cleaned.lower().split()))
    return out
