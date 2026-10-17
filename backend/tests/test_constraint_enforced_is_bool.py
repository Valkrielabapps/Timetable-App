"""ConstraintOut.enforced must be a real bool.

An availability rule parsed with a teacher but an empty or missing period
list used to make _is_enforced return [] or None, which ConstraintOut
rejects - turning one odd rule into a 500 for a whole batch."""
import pytest

from app.models.school import Constraint
from app.routers.constraints import _is_enforced


@pytest.mark.parametrize("params,expected", [
    ({"teacher_id": 1, "period_numbers": []}, False),
    ({"teacher_id": 1, "period_numbers": None}, False),
    ({"teacher_id": 1}, False),
    ({"teacher_id": 1, "period_numbers": [1]}, True),
    ({"teacher_id": 1, "day_of_week": 5}, True),
])
def test_availability(params, expected):
    result = _is_enforced(Constraint(type="availability", parameters=params))
    assert result is expected


def test_unknown_type_is_false():
    assert _is_enforced(Constraint(type="scheduling_rule", parameters={})) is False
