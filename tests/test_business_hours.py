"""Tests for business hours functionality."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from zulip_refinement_bot.business_hours import BusinessHoursCalculator
from zulip_refinement_bot.config import Config


@pytest.fixture
def config() -> Config:
    """Create a test configuration."""
    return Config(
        zulip_email="test@example.com",
        zulip_api_key="test-key",
        zulip_site="https://test.zulipchat.com",
        holiday_country="US",
        custom_holidays="2024-12-25,2024-01-01",
    )


@pytest.fixture
def config_skip_weekends_holidays() -> Config:
    """Create a test configuration that skips weekends/holidays."""
    return Config(
        zulip_email="test@example.com",
        zulip_api_key="test-key",
        zulip_site="https://test.zulipchat.com",
        holiday_country="US",
        custom_holidays="2024-12-25,2024-01-01",
    )


@pytest.fixture
def calculator(config: Config) -> BusinessHoursCalculator:
    """Create a business hours calculator."""
    return BusinessHoursCalculator(config)


@pytest.fixture
def calculator_skip_weekends_holidays(
    config_skip_weekends_holidays: Config,
) -> BusinessHoursCalculator:
    """Create a business hours calculator that skips weekends/holidays."""
    return BusinessHoursCalculator(config_skip_weekends_holidays)


def test_business_hours_is_business_day_weekday(calculator: BusinessHoursCalculator) -> None:
    """Test that weekdays are business days."""
    # Monday, January 8, 2024
    monday = datetime(2024, 1, 8, 10, 0, tzinfo=UTC)
    assert calculator.is_business_day(monday)


def test_business_hours_is_business_day_weekend(calculator: BusinessHoursCalculator) -> None:
    """Test that weekends are not business days."""
    # Saturday, January 6, 2024
    saturday = datetime(2024, 1, 6, 10, 0, tzinfo=UTC)
    assert not calculator.is_business_day(saturday)

    # Sunday, January 7, 2024
    sunday = datetime(2024, 1, 7, 10, 0, tzinfo=UTC)
    assert not calculator.is_business_day(sunday)


def test_business_hours_is_business_day_custom_holiday(calculator: BusinessHoursCalculator) -> None:
    """Test that custom holidays are not business days."""
    # Christmas Day 2024 (configured as custom holiday)
    christmas = datetime(2024, 12, 25, 10, 0, tzinfo=UTC)
    assert not calculator.is_business_day(christmas)


def test_business_hours_is_business_hour_on_business_day(
    calculator: BusinessHoursCalculator,
) -> None:
    """Test that any time on a business day is considered a business hour."""
    # Monday, January 8, 2024 at various times
    monday_early = datetime(2024, 1, 8, 6, 0, tzinfo=UTC)
    monday_mid = datetime(2024, 1, 8, 14, 0, tzinfo=UTC)
    monday_late = datetime(2024, 1, 8, 22, 0, tzinfo=UTC)

    assert calculator.is_business_hour(monday_early)
    assert calculator.is_business_hour(monday_mid)
    assert calculator.is_business_hour(monday_late)


def test_business_hours_is_business_hour_weekend(calculator: BusinessHoursCalculator) -> None:
    """Test that weekend times are never business hours."""
    # Saturday, January 6, 2024 at 10 AM
    saturday_10am = datetime(2024, 1, 6, 10, 0, tzinfo=UTC)
    assert not calculator.is_business_hour(saturday_10am)


def test_business_hours_add_business_hours_same_day(calculator: BusinessHoursCalculator) -> None:
    """Test adding business hours within the same day."""
    # Monday, January 8, 2024 at 10 AM
    start = datetime(2024, 1, 8, 10, 0, tzinfo=UTC)
    result = calculator.add_business_hours(start, 4)
    expected = datetime(2024, 1, 8, 14, 0, tzinfo=UTC)  # 4 hours later same day
    assert result == expected


def test_business_hours_add_business_hours_skip_weekend(
    calculator: BusinessHoursCalculator,
) -> None:
    """Test adding business hours that skip over a weekend."""
    # Friday, January 5, 2024 at 3 PM
    start = datetime(2024, 1, 5, 15, 0, tzinfo=UTC)
    result = calculator.add_business_hours(start, 48)
    # 48 hours from Friday 3 PM would normally be Sunday 3 PM
    # But skipping weekend, should be Tuesday 3 PM (Monday + 24 hours)
    expected = datetime(2024, 1, 9, 15, 0, tzinfo=UTC)
    assert result == expected


def test_business_hours_get_holiday_info_custom(calculator: BusinessHoursCalculator) -> None:
    """Test getting holiday info for custom holidays."""
    christmas = datetime(2024, 12, 25, 10, 0, tzinfo=UTC)
    result = calculator.get_holiday_info(christmas)
    assert result == "Custom Holiday"


def test_business_hours_get_holiday_info_none(calculator: BusinessHoursCalculator) -> None:
    """Test getting holiday info for non-holidays."""
    regular_day = datetime(2024, 1, 8, 10, 0, tzinfo=UTC)
    result = calculator.get_holiday_info(regular_day)
    assert result is None


def test_business_hours_get_holiday_info_country_holiday(
    calculator: BusinessHoursCalculator,
) -> None:
    """Test getting holiday info for country holidays."""
    new_years = datetime(2024, 1, 1, 10, 0, tzinfo=UTC)
    result = calculator.get_holiday_info(new_years)
    # Should return "Custom Holiday" since 2024-01-01 is in custom_holidays list
    # (custom holidays take precedence over country holidays)
    assert result == "Custom Holiday"


def test_business_hours_format_business_deadline_basic(calculator: BusinessHoursCalculator) -> None:
    """Test basic deadline formatting."""
    deadline = datetime(2024, 1, 8, 14, 0, tzinfo=UTC)
    result = calculator.format_business_deadline(deadline)
    assert "2024-01-08 14:00" in result
    assert "excluding weekends/holidays" in result


def test_business_hours_format_business_deadline_with_holiday(
    calculator: BusinessHoursCalculator,
) -> None:
    """Test deadline formatting with holiday info."""
    christmas = datetime(2024, 12, 25, 14, 0, tzinfo=UTC)
    result = calculator.format_business_deadline(christmas)
    assert "2024-12-25 14:00" in result
    assert "Custom Holiday" in result


def test_business_hours_utc_handling() -> None:
    """Test that UTC timezone is used for calculations."""
    config = Config(
        zulip_email="test@example.com",
        zulip_api_key="test-key",
        zulip_site="https://test.zulipchat.com",
        holiday_country="US",
    )

    calculator = BusinessHoursCalculator(config)

    # Test that calculations work with UTC
    start = datetime(2024, 1, 8, 10, 0, tzinfo=UTC)
    result = calculator.add_business_hours(start, 4)
    assert isinstance(result, datetime)
    assert result.tzinfo is not None


def test_business_hours_config_custom_holiday_dates_parsing() -> None:
    """Test that custom holiday dates are properly parsed from config."""
    config = Config(
        zulip_email="test@example.com",
        zulip_api_key="test-key",
        zulip_site="https://test.zulipchat.com",
        custom_holidays="2024-12-25, 2024-01-01, 2024-07-04",
    )

    expected = ["2024-12-25", "2024-01-01", "2024-07-04"]
    assert config.custom_holiday_dates == expected


def test_business_hours_config_empty_custom_holidays() -> None:
    """Test that empty custom holidays string results in empty list."""
    config = Config(
        zulip_email="test@example.com",
        zulip_api_key="test-key",
        zulip_site="https://test.zulipchat.com",
        custom_holidays="",
    )

    assert config.custom_holiday_dates == []


def test_business_hours_config_whitespace_custom_holidays() -> None:
    """Test that whitespace in custom holidays is handled properly."""
    config = Config(
        zulip_email="test@example.com",
        zulip_api_key="test-key",
        zulip_site="https://test.zulipchat.com",
        custom_holidays="  2024-12-25  ,  , 2024-01-01  ",
    )

    expected = ["2024-12-25", "2024-01-01"]
    assert config.custom_holiday_dates == expected


def test_business_hours_add_hours_skip_weekends_holidays_same_week(
    calculator_skip_weekends_holidays: BusinessHoursCalculator,
) -> None:
    """Test adding hours that skip weekends/holidays but stay within the same week."""
    # Monday, January 8, 2024 at 10 AM
    start = datetime(2024, 1, 8, 10, 0, tzinfo=UTC)
    result = calculator_skip_weekends_holidays.add_business_hours(start, 24)
    # Should be Tuesday at 10 AM (24 hours later, no weekends/holidays to skip)
    expected = datetime(2024, 1, 9, 10, 0, tzinfo=UTC)
    assert result == expected


def test_business_hours_add_hours_skip_weekends_holidays_over_weekend(
    calculator_skip_weekends_holidays: BusinessHoursCalculator,
) -> None:
    """Test adding hours that span over a weekend."""
    # Friday, January 5, 2024 at 2 PM
    start = datetime(2024, 1, 5, 14, 0, tzinfo=UTC)
    result = calculator_skip_weekends_holidays.add_business_hours(start, 48)
    # 48 hours from Friday 2 PM would normally be Sunday 2 PM
    # But skipping weekend, should be Tuesday 2 PM (Monday + 24 hours)
    expected = datetime(2024, 1, 9, 14, 0, tzinfo=UTC)
    assert result == expected


def test_business_hours_add_hours_skip_weekends_holidays_over_holiday(
    calculator_skip_weekends_holidays: BusinessHoursCalculator,
) -> None:
    """Test adding hours that span over a custom holiday."""
    # December 24, 2024 at 10 AM (day before Christmas)
    start = datetime(2024, 12, 24, 10, 0, tzinfo=UTC)
    result = calculator_skip_weekends_holidays.add_business_hours(start, 48)
    # 48 hours from Dec 24 10 AM would normally be Dec 26 10 AM
    # But Christmas (Dec 25) is a holiday, and Dec 26 is Boxing Day (also a US holiday)
    # So it should be Dec 27 10 AM
    expected = datetime(2024, 12, 27, 10, 0, tzinfo=UTC)
    assert result == expected


def test_business_hours_format_deadline_skip_weekends_holidays(
    calculator_skip_weekends_holidays: BusinessHoursCalculator,
) -> None:
    """Test deadline formatting for skip weekends/holidays mode."""
    deadline = datetime(2024, 1, 8, 14, 0, tzinfo=UTC)
    result = calculator_skip_weekends_holidays.format_business_deadline(deadline)
    assert "2024-01-08 14:00" in result
    assert "excluding weekends/holidays" in result
