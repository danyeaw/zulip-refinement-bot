"""Calculate deadlines excluding weekends and holidays."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import holidays
import structlog

if TYPE_CHECKING:
    from .config import Config

logger = structlog.get_logger(__name__)


class BusinessHoursCalculator:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.holidays_calendar = self._get_holidays_calendar()

    def _get_holidays_calendar(self) -> dict[str, str] | None:
        if not self.config.holiday_country:
            return None

        try:
            current_year = datetime.now().year
            holiday_calendar = {}

            countries = [country.strip() for country in self.config.holiday_country.split(",")]

            for country in countries:
                if not country:
                    continue

                for year in [current_year, current_year + 1]:
                    year_holidays = holidays.country_holidays(country, years=year)
                    holiday_calendar.update(
                        {date.strftime("%Y-%m-%d"): name for date, name in year_holidays.items()}
                    )

            logger.info(
                f"Loaded {len(holiday_calendar)} holidays for {self.config.holiday_country}"
            )
            return holiday_calendar
        except Exception as e:
            logger.warning(f"Failed to load holidays for {self.config.holiday_country}: {e}")
            return None

    def is_business_day(self, dt: datetime) -> bool:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)

        local_dt = dt.astimezone(UTC)

        if local_dt.weekday() >= 5:
            return False

        date_str = local_dt.strftime("%Y-%m-%d")

        if date_str in self.config.custom_holiday_dates:
            return False

        if self.holidays_calendar and date_str in self.holidays_calendar:
            return False

        return True

    def is_business_hour(self, dt: datetime) -> bool:
        if not self.is_business_day(dt):
            return False
        return True

    def add_business_hours(self, start_dt: datetime, hours: int) -> datetime:
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=UTC)
        return self._add_hours_skip_weekends_holidays(start_dt, hours)

    def _add_hours_skip_weekends_holidays(self, start_dt: datetime, hours: int) -> datetime:
        current_dt = start_dt
        target_dt = current_dt + timedelta(hours=hours)
        check_dt = current_dt
        while check_dt < target_dt:
            if not self.is_business_day(check_dt):
                next_business_day = self._next_business_day(check_dt)
                days_skipped = (next_business_day.date() - check_dt.date()).days
                target_dt += timedelta(days=days_skipped)
                check_dt = next_business_day
            else:
                check_dt += timedelta(days=1)

        return target_dt

    def _next_business_day(self, dt: datetime) -> datetime:
        current = dt + timedelta(days=1)
        current = current.replace(
            hour=dt.hour, minute=dt.minute, second=dt.second, microsecond=dt.microsecond
        )

        max_iterations = 14
        iterations = 0

        while iterations < max_iterations:
            if self.is_business_day(current):
                return current
            current += timedelta(days=1)
            iterations += 1

        logger.warning("Could not find next business day within 2 weeks, using fallback")
        return dt + timedelta(days=1)

    def get_holiday_info(self, dt: datetime) -> str | None:
        local_dt = dt.astimezone(UTC)
        date_str = local_dt.strftime("%Y-%m-%d")

        if date_str in self.config.custom_holiday_dates:
            return "Custom Holiday"

        if self.holidays_calendar and date_str in self.holidays_calendar:
            return self.holidays_calendar[date_str]

        return None

    def format_business_deadline(self, deadline: datetime) -> str:
        local_deadline = deadline.astimezone(UTC)
        formatted = local_deadline.strftime("%Y-%m-%d %H:%M %Z")

        holiday_info = self.get_holiday_info(deadline)
        if holiday_info:
            formatted += f" - Note: {holiday_info}"

        return formatted
