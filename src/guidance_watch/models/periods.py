"""Fiscal period value type."""

from __future__ import annotations

import re
from datetime import date
from typing import Self

from pydantic import BaseModel, Field, field_validator, model_validator

_FISCAL_RE = re.compile(r"^FY(?P<year>\d{4})Q(?P<quarter>[1-4])$")


class FiscalPeriod(BaseModel):
    """Canonical fiscal period as `FY{year}Q{n}` with optional calendar end date."""

    model_config = {"frozen": True}

    label: str = Field(..., description="Canonical label, e.g. FY2024Q3")
    fiscal_year: int
    fiscal_quarter: int = Field(..., ge=1, le=4)
    calendar_end_date: date | None = None

    @field_validator("label")
    @classmethod
    def _validate_label(cls, value: str) -> str:
        if not _FISCAL_RE.match(value):
            raise ValueError(f"Invalid fiscal period label: {value!r}; expected FYYYYYQn")
        return value

    @model_validator(mode="after")
    def _align_components(self) -> Self:
        match = _FISCAL_RE.match(self.label)
        assert match is not None
        year = int(match.group("year"))
        quarter = int(match.group("quarter"))
        if self.fiscal_year != year or self.fiscal_quarter != quarter:
            raise ValueError(
                f"label {self.label!r} does not match "
                f"fiscal_year={self.fiscal_year}, fiscal_quarter={self.fiscal_quarter}"
            )
        return self

    @classmethod
    def parse(cls, label: str, calendar_end_date: date | None = None) -> FiscalPeriod:
        match = _FISCAL_RE.match(label)
        if match is None:
            raise ValueError(f"Invalid fiscal period label: {label!r}; expected FYYYYYQn")
        return cls(
            label=label,
            fiscal_year=int(match.group("year")),
            fiscal_quarter=int(match.group("quarter")),
            calendar_end_date=calendar_end_date,
        )

    def sort_key(self) -> tuple[int, int]:
        return (self.fiscal_year, self.fiscal_quarter)

    def __lt__(self, other: FiscalPeriod) -> bool:
        return self.sort_key() < other.sort_key()
