"""
Patterns that read text from outside - a rule a school types, a school's web
page - must take time in proportion to the text, not explode on it (ReDoS).

Each case here took from seconds to many minutes before the fix: a long run of
spaces (or non-breaking spaces, which \\s also matches) let several \\s* side
by side share it out in a huge number of ways. The limit is generous so a slow
CI machine doesn't fail it; the broken versions missed it by orders of
magnitude.
"""
import time

from app.services import constraint_parser, outreach

LIMIT_SECONDS = 1.0


def _timed(fn, *args):
    start = time.perf_counter()
    result = fn(*args)
    elapsed = time.perf_counter() - start
    assert elapsed < LIMIT_SECONDS, f"took {elapsed:.2f}s"
    return result


def test_a_rule_made_of_whitespace_is_read_quickly():
    for blank in (" ", "\t", " ", "  \t"):
        _timed(constraint_parser.parse_constraint, "Maths" + blank * 2000 + "x", ["Anil"], ["Maths", "PE"])


def test_a_rule_with_many_negations_is_read_quickly():
    _timed(constraint_parser.parse_constraint, "Maths" + " cannot" * 280, ["Anil"], ["Maths", "PE"])


def test_spacing_doesnt_change_what_a_rule_means():
    plain = constraint_parser.parse_constraint("Maths can't immediately follow PE", [], ["Maths", "PE"])
    spaced = constraint_parser.parse_constraint("Maths  can't\t immediately   follow  PE", [], ["Maths", "PE"])
    assert plain.type == "subject_sequence"
    assert spaced == plain


def test_a_page_padded_with_nbsp_is_searched_quickly():
    page = "<p>Mr Anand Kumar" + "&nbsp;" * 5000 + "x</p>"
    _timed(outreach.extract_people, outreach._page_text(page))


def test_a_page_of_repeated_names_is_searched_quickly():
    page = "<p>" + "Mr Aa " * 100_000 + "</p>"
    _timed(outreach.extract_people, outreach._page_text(page))


def test_a_page_with_one_long_word_is_searched_quickly():
    for text in ("a" * 600_000, "a@" + "a" * 600_000, "a." * 300_000):
        _timed(outreach._split_emails, text)


def test_a_name_written_before_its_role_is_still_found():
    page = "<p>" + "Mr Aa " * 1000 + "and more.</p><p>Mr. Ravi Shankar - Vice Principal</p>" \
           "<p>Regards,<br>Mrs. Lakshmi Iyer, M.Sc., B.Ed.<br>The Principal</p>"
    people = _timed(outreach.extract_people, outreach._page_text(page))
    assert people["principal_name"] == "Mrs. Lakshmi Iyer"
    assert (people["contact_name"], people["contact_role"]) == ("Mr. Ravi Shankar", "Vice Principal")


def test_names_and_emails_are_still_found():
    page = ("<div>Principal&nbsp;:&nbsp; <b>Dr. Meena Raghavan</b></div>"
            "<p>write to us at office@school.edu.in or mailto:head@school.edu.in.</p>")
    people = outreach.extract_people(outreach._page_text(page))
    assert people["principal_name"] == "Dr. Meena Raghavan"
    assert people["emails"] == ["office@school.edu.in", "head@school.edu.in"]
