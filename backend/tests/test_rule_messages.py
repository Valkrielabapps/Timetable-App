"""
Rules the way coordinators send them: a forwarded WhatsApp message with a
greeting and a sign-off, numbered or all in one paragraph, two rules on one
line, and clock times instead of period numbers.
"""
from unittest.mock import patch

from app.services.rule_splitter import split_rules
from app.services.rule_text_hints import _clock_hints, period_times, sentence_hints
from tests.conftest import create_school, signup

T = ["Bhagya Lakshmi", "Sabina Raman", "Kavitha Rao", "Ravi Kumar", "Priya Sharma", "Murali Kumar", "Anu Das"]
S = ["Physical Education", "Games", "Maths", "Physics", "Biology", "Library", "Art", "Computer Science", "Science"]


def test_a_forwarded_message_is_cut_into_its_rules():
    text = """[20/11/25, 9:14 am] Principal: Sir pls note the following for next year's TT:
1) Priya Sharma is off on Monday and can't take more than 4 periods a day
2) No PE in the last period; Ravi leaves after lunch
3) Anu can take classes only on Mon, Wed and Fri. Also no Maths in period 1
- Mr. Murali Kumar is part time - not available Wednesday morning and Friday afternoon
Thanks 🙏
Regards,
Coordinator"""
    assert split_rules(text, T, S) == [
        "Priya Sharma is off on Monday", "Priya Sharma can't take more than 4 periods a day",
        "No PE in the last period", "Ravi leaves after lunch", "Anu can take classes only on Mon, Wed and Fri",
        "No Maths in period 1", "Mr. Murali Kumar is part time - not available Wednesday morning and Friday afternoon"]


def test_a_paragraph_and_a_person_carried_into_the_next_rule():
    text = ("Hello sir, Meena is part time - not available Tuesday morning. No Computer Science after 11.50am. "
            "Avoid Science last period. No classes for Kavitha Rao on Tue and can't take more than 5 periods a day.")
    assert split_rules(text, T + ["Meena"], S) == [
        "Meena is part time - not available Tuesday morning", "No Computer Science after 11.50am",
        "Avoid Science last period", "No classes for Kavitha Rao on Tue", "Kavitha Rao can't take more than 5 periods a day"]


def test_one_rule_is_never_cut():
    for t in ["Mrs. Bhagya's Grade 12 Biology only in periods 6 and 7", "Sabina teaches only on Monday and Tuesday",
              "No double periods unless absolutely necessary", "PE and Games should not be on the same day",
              "Ravi and Priya should not teach in the same period", "Grade 9 A and B have PE together",
              "Maths and Physics not on the same day", "Kavitha is free on Mon, Wed and Fri",
              "Priya - not available Tue morning and Thu afternoon", "Kavitha can also take Grade 9"]:
        assert split_rules(t, T, S) == [t], t
    assert split_rules("Kavitha should not have more than 6 periods a day and not more than 30 a week", T, S) == [
        "Kavitha should not have more than 6 periods a day", "Kavitha not more than 30 a week"]


BELLS = ["8:40-9:20", "9:20-10:00", "10:20-11:00", "11:00-11:40", "11:40-12:20", "12:40-13:20", "13:20-14:00",
         "14:00-14:40"]
PERIODS = [(0, i, f"Period {i + 1} ({b})", "lesson") for i, b in enumerate(BELLS)] + [(0, 99, "Lunch", "break")]


def test_clock_times_become_periods_from_the_bell_times():
    assert period_times(PERIODS)[5] == (6, 760, 800)
    assert _clock_hints("Anu leaves at 12.40", PERIODS) == [
        "'12.40' = the start of period 6 (before it: periods 1-5; from it on: periods 6-8)"]
    assert "start of period 7" in _clock_hints("no PE after 1:20 pm", PERIODS)[0]
    assert "start of period 7" in _clock_hints("no PE after 1:20", PERIODS)[0]  # no pm: still the afternoon
    assert _clock_hints("Ravi can't come before 10:00", PERIODS) == [
        "'10:00' = the end of period 2 (up to it: periods 1-2; after it: periods 3-8)"]
    assert _clock_hints("meet at 1 pm", PERIODS) == ["'1 pm' falls during period 6"]
    assert _clock_hints("Maths in period 3", PERIODS) == []           # a period number, not a time
    assert _clock_hints("Anu leaves at 12.40", [(0, 0, "Period 1", "lesson")]) == []  # no bell times known
    assert any("start of period 6" in h for h in sentence_hints("Anu leaves at 12.40", T, S, [], None, PERIODS))


def _school(client):
    _, h = signup(client)
    sid = create_school(client, h)["id"]
    client.post("/api/teachers", json={"school_id": sid, "name": "Priya Sharma"}, headers=h)
    return sid, h


def test_typing_two_rules_at_once_offers_to_add_both(client):
    sid, h = _school(client)
    with patch("app.routers.constraints.parse_rule_llm") as parse:
        r = client.post("/api/constraints/interpret", headers=h, json={
            "school_id": sid, "text": "Priya Sharma is off on Monday and can't take more than 4 periods a day"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["reason"] == "several" and body["readings"] == [
        "Priya Sharma is off on Monday", "Priya Sharma can't take more than 4 periods a day"]
    parse.assert_not_called()


def test_a_pasted_message_reaches_the_parser_one_rule_at_a_time(client, monkeypatch):
    sid, h = _school(client)
    seen = []
    monkeypatch.setattr("app.routers.constraints.plans.use_ai", lambda db, school: True)
    with patch("app.routers.constraints.parse_rule_llm", side_effect=lambda text, *a, **k: seen.append(text)):
        client.post("/api/constraints/batch", headers=h, json={
            "school_id": sid, "text": "Good eve sir.\n1. Priya Sharma is off on Monday; no PE in the last period\nThanks"})
    assert sorted(set(seen)) == ["No PE in the last period", "Priya Sharma is off on Monday"]
