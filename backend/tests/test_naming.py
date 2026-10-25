"""Teachers sort by name, never title - the same rule as the app's lists
(frontend/src/sorting.js), so exports come out in the same order."""
import pytest

from app.services.naming import name_sort_key, without_title


@pytest.mark.parametrize("name, bare", [
    ("Mrs. Rao", "Rao"), ("Mr Khan", "Khan"), ("ms. shallu", "shallu"), ("MISS Gupta", "Gupta"),
    ("Dr. Bose", "Bose"), ("Prof. Dr. Iyer", "Iyer"), ("Professor Iyer", "Iyer"),
    ("Drishti", "Drishti"), ("Mrinal", "Mrinal"), ("Dr.", "Dr."),
])
def test_titles_are_ignored(name, bare):
    assert without_title(name) == bare


def test_a_staff_list_sorts_by_first_name():
    staff = ["Ms. Shallu", "Mrs. Zareena", "Mrs. Anjali", "Dr. Bose", "anil", "Mr. Kamal 2", "Mr. Kamal 10"]
    assert sorted(staff, key=name_sort_key) == [
        "anil", "Mrs. Anjali", "Dr. Bose", "Mr. Kamal 2", "Mr. Kamal 10", "Ms. Shallu", "Mrs. Zareena",
    ]
