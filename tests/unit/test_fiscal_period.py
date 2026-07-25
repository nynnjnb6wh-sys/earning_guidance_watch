"""FiscalPeriod parsing and ordering."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from guidance_watch.models import FiscalPeriod


@pytest.mark.unit
def test_parse_valid() -> None:
    period = FiscalPeriod.parse("FY2024Q3", calendar_end_date=date(2024, 9, 28))
    assert period.fiscal_year == 2024
    assert period.fiscal_quarter == 3
    assert period.calendar_end_date == date(2024, 9, 28)


@pytest.mark.unit
def test_parse_invalid() -> None:
    with pytest.raises(ValueError):
        FiscalPeriod.parse("2024Q3")
    with pytest.raises(ValueError):
        FiscalPeriod.parse("FY2024Q5")


@pytest.mark.unit
def test_mismatched_components_rejected() -> None:
    with pytest.raises(ValidationError):
        FiscalPeriod(label="FY2024Q1", fiscal_year=2024, fiscal_quarter=2)


@pytest.mark.unit
def test_ordering() -> None:
    a = FiscalPeriod.parse("FY2023Q4")
    b = FiscalPeriod.parse("FY2024Q1")
    assert a < b
    assert sorted([b, a]) == [a, b]
