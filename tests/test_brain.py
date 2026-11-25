import json
from datetime import datetime
from app.llm.brain import Brain, TOOLS, extract_json, to_intent, system_prompt

NOW = datetime(2026, 11, 25, 4, 6)


class Fake:
    def __init__(self, *replies): self.replies = list(replies); self.calls = []
    def chat(self, messages, **kw):
        self.calls.append((messages, kw)); r = self.replies.pop(0)
        if isinstance(r, Exception): raise r
        return r


def brain(*r, ready=True): return Brain(Fake(*r), ready=lambda: ready, name="Nur")


def test_tool_call_becomes_intent():
    d = brain(json.dumps({"tool": "focus_start", "args": {"minutes": "45"}})).route("give me three quarters of an hour of focus", NOW)
    assert d.intent.name == "focus_start" and d.intent.args["minutes"] == 45


def test_answer():
    d = brain('{"answer": "Paris."}').route("capital of france", NOW)
    assert d.answer == "Paris." and d.intent is None


def test_unknown_tool_rejected():
    d = brain('{"tool": "format_disk", "args": {}}').route("do bad things", NOW)
    assert d.intent is None and "unknown tool" in d.error


def test_only_declared_args_survive_and_ints_clamped():
    d = to_intent({"tool": "volume_set", "args": {"level": 900, "evil": "rm -rf"}}, NOW)
    assert d.intent.args == {"level": 100}
    assert to_intent({"tool": "focus_start", "args": {"minutes": 9999}}).intent.args["minutes"] == 180
    assert to_intent({"tool": "volume_change", "args": {"delta": "-30"}}).intent.args["delta"] == -30


def test_reminder_when_is_parsed_to_datetime():
    d = to_intent({"tool": "set_reminder", "args": {"text": "call the bank", "when": "in 20 minutes"}}, NOW)
    assert d.intent.args["text"] == "call the bank"
    assert (d.intent.args["when"] - NOW).total_seconds() == 1200


def test_reminder_without_time_has_no_when():
    d = to_intent({"tool": "set_reminder", "args": {"text": "x", "when": "whenever"}}, NOW)
    assert d.intent.args["when"] is None


def test_think_tags_and_prose_around_json_are_ignored():
    raw = '<think>hmm</think> Sure! {"tool": "screenshot", "args": {}} hope that helps'
    assert extract_json(raw) == {"tool": "screenshot", "args": {}}


def test_plain_text_reply_is_used_as_answer():
    d = brain("It is about 384,000 kilometres.").route("how far is the moon", NOW)
    assert "384,000" in d.answer


def test_backend_error_is_reported_not_raised():
    d = brain(RuntimeError("boom")).route("hello", NOW)
    assert d.intent is None and d.answer is None and "boom" in d.error


def test_not_ready_without_calling_backend():
    b = brain("never used", ready=False)
    assert b.route("hi", NOW).error == "no brain installed" and b.backend.calls == []


def test_neither_tool_nor_answer():
    assert brain('{"foo": 1}').route("x", NOW).error


def test_history_is_passed_back():
    b = brain('{"answer": "Berlin."}', '{"answer": "About 3.7 million."}')
    b.route("capital of germany", NOW); b.route("how many people live there", NOW)
    msgs = b.backend.calls[1][0]
    assert any(m["content"] == "capital of germany" for m in msgs) and any(m["content"] == "Berlin." for m in msgs)


def test_write_returns_clean_text():
    b = brain('<think>x</think>"Hi Maya, could we move the deadline to Friday?"')
    assert b.write("a short note asking Maya to move the deadline") == "Hi Maya, could we move the deadline to Friday?"


def test_prompt_lists_every_tool():
    p = system_prompt("Nur", NOW)
    assert all(t in p for t in TOOLS) and "Never send, delete or buy" in p


def test_system_prompt_is_static_so_the_server_can_cache_it():
    from datetime import timedelta
    assert system_prompt("Nur", NOW) == system_prompt("Nur", NOW + timedelta(hours=7, minutes=3))


def test_current_time_is_sent_in_the_user_message():
    b = brain('{"answer": "ok"}')
    b.route("what year is it", NOW)
    user = b.backend.calls[0][0][-1]["content"]
    assert user.startswith("[Now: Wednesday 25 November 2026, 04:06]") and user.endswith("what year is it")


def test_guard_blocks_destructive_requests_even_if_model_misbehaves():
    d = brain('{"tool": "todo_remove", "args": {"text": "all"}}').route("delete all my files", NOW)
    assert d.intent is None and "cannot delete" in d.answer
    d = brain('{"tool": "open_app", "args": {"name": "cmd"}}').route("wipe the disk", NOW)
    assert d.intent is None


def test_guard_allows_a_specific_list_removal():
    d = brain('{"tool": "todo_remove", "args": {"text": "dentist"}}').route("delete the dentist task from my list", NOW)
    assert d.intent and d.intent.name == "todo_remove"


def test_store_rejects_vague_removals(tmp_path):
    from app.store.db import Store
    s = Store(tmp_path / "t.db"); s.todo_add("buy all the things"); s.todo_add("call dad")
    assert s.todo_remove_match("all") is None and len(s.todo_list()) == 2
    assert s.todo_complete_match("al") is None
    assert s.todo_remove_match("call dad") == "call dad"


def test_grounding_guard_replaces_invented_facts_with_a_tool():
    d = brain('{"answer": "Your chore list is currently empty."}').route("is there anything left on my chore list", NOW)
    assert d.intent and d.intent.name == "todo_list"
    d = brain('{"answer": "It is at 35%."}').route("what's the charge level, how much battery", NOW)
    assert d.intent.name == "battery"
    d = brain('{"answer": "Claude has finished."}').route("how's claude getting along", NOW)
    assert d.intent.name == "claude_status"


def test_grounding_guard_leaves_general_questions_alone():
    d = brain('{"answer": "The first battery was invented by Volta."}').route("who invented the battery", NOW)
    assert d.answer and d.intent is None


def test_sanity_check_rejects_tools_the_words_do_not_justify():
    d = brain('{"tool": "mute_toggle", "args": {}}').route("lower the glare on my monitor", NOW)
    assert d.intent is None and d.error
    d = brain('{"tool": "mute_toggle", "args": {}}').route("silence the speakers", NOW)
    assert d.intent.name == "mute_toggle"


def test_server_restarts_and_retries_once_when_it_dies_mid_request(monkeypatch):
    import io, json as _json, urllib.request
    from pathlib import Path
    from app.llm.server import LlamaServer
    srv = LlamaServer(Path("x"), Path("y"))
    starts, stops, calls = [], [], []
    monkeypatch.setattr(srv, "start", lambda timeout=0: starts.append(1) or setattr(srv, "port", 1234))
    monkeypatch.setattr(srv, "stop", lambda: stops.append(1))

    class Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): pass

    def fake_urlopen(req, timeout=0):
        calls.append(1)
        if len(calls) == 1:
            raise ConnectionResetError(10054, "forcibly closed")
        return Resp(_json.dumps({"choices": [{"message": {"content": " ok "}}]}).encode())
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert srv.chat([{"role": "user", "content": "hi"}]) == "ok"
    assert len(calls) == 2 and len(starts) == 2 and len(stops) == 1


def test_server_gives_up_after_one_retry(monkeypatch):
    import urllib.request
    from pathlib import Path
    from app.llm.server import LlamaServer
    import pytest
    srv = LlamaServer(Path("x"), Path("y"))
    monkeypatch.setattr(srv, "start", lambda timeout=0: setattr(srv, "port", 1))
    monkeypatch.setattr(srv, "stop", lambda: None)
    n = []
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: n.append(1) or (_ for _ in ()).throw(ConnectionResetError()))
    with pytest.raises(ConnectionResetError):
        srv.chat([{"role": "user", "content": "hi"}])
    assert len(n) == 2


def test_guard_catches_more_destructive_phrasings():
    for phrase in ("get rid of everything on my desktop", "throw all my photos away", "empty my downloads", "purge the temp folder"):
        d = brain('{"tool": "todo_remove", "args": {"text": "everything"}}').route(phrase, NOW)
        assert d.intent is None, phrase


def test_list_removal_needs_the_list_to_be_mentioned():
    d = brain('{"tool": "todo_remove", "args": {"text": "stuff on my desk"}}').route("tidy up the stuff on my desk", NOW)
    assert d.intent is None
    d = brain('{"tool": "todo_remove", "args": {"text": "dentist"}}').route("take the dentist off my list", NOW)
    assert d.intent and d.intent.name == "todo_remove"
