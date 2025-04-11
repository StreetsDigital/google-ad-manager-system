"""
Reporting service for managing ad performance reports.

This module provides the high-level service for generating, scheduling,
and managing reports in the Google Ad Manager system.
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from pydantic import BaseModel

from src.tools.soap_tools import SoapToolAdapter
from src.campaigns.line_items.connection_pool import ConnectionPool
from .reports.base import ReportConfig, ReportResult
from .reports.campaign_performance import CampaignPerformanceReport
from .reports.inventory_usage import InventoryUsageReport, InventoryReportConfig
from .reports.creative_performance import CreativePerformanceReport
from .aggregation import aggregate_performance_data

logger = logging.getLogger(__name__)

class ReportSchedule(BaseModel):
    """Configuration for report scheduling."""
    report_type: str
    frequency: str  # daily, weekly, monthly
    time_of_day: str  # HH:MM format
    enabled: bool = True
    email_recipients: Optional[List[str]] = None
    export_format: str = "CSV"  # CSV, EXCEL, JSON
    filters: Optional[Dict[str, Any]] = None

class ReportingService:
    """Service for managing ad performance reporting."""

    def __init__(self, connection_pool: ConnectionPool):
        """Initialize with connection pool."""
        self.connection_pool = connection_pool
        self.scheduled_reports: Dict[str, ReportSchedule] = {}

    async def generate_report(
        self,
        report_type: str,
        start_date: datetime,
        end_date: datetime,
        config: Optional[Dict[str, Any]] = None
    ) -> ReportResult:
        """
        Generate a report for the specified type and date range.

        Args:
            report_type: Type of report to generate
            start_date: Start date for report data
            end_date: End date for report data
            config: Optional additional configuration

        Returns:
            ReportResult containing the generated report data
        """
        try:
            # Create base report config
            report_config = ReportConfig(
                start_date=start_date,
                end_date=end_date,
                filters=config.get("filters") if config else None
            )

            # Get SOAP adapter from connection pool
            async with self.connection_pool.get_connection() as conn:
                # Create appropriate report generator
                if report_type == "campaign_performance":
                    generator = CampaignPerformanceReport(report_config, conn)
                elif report_type == "inventory_usage":
                    inv_config = InventoryReportConfig(
                        **report_config.dict(),
                        include_key_values=config.get("include_key_values", True)
                        if config else True
                    )
                    generator = InventoryUsageReport(inv_config, conn)
                elif report_type == "creative_performance":
                    generator = CreativePerformanceReport(report_config, conn)
                else:
                    raise ValueError(f"Unsupported report type: {report_type}")

                # Generate report
                return await generator.generate()

        except Exception as e:
            logger.error(f"Error generating report: {e}")
            raise

    async def schedule_report(
        self,
        report_type: str,
        frequency: str,
        time_of_day: str,
        config: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Schedule a report for recurring generation.

        Args:
            report_type: Type of report to schedule
            frequency: How often to generate (daily, weekly, monthly)
            time_of_day: When to generate (HH:MM)
            config: Optional additional configuration

        Returns:
            str: ID of the scheduled report
        """
        try:
            # Validate frequency
            if frequency not in ["daily", "weekly", "monthly"]:
                raise ValueError("Invalid frequency. Must be daily, weekly, or monthly")

            # Create schedule
            schedule = ReportSchedule(
                report_type=report_type,
                frequency=frequency,
                time_of_day=time_of_day,
                email_recipients=config.get("email_recipients"),
                export_format=config.get("export_format", "CSV"),
                filters=config.get("filters")
            )

            # Generate schedule ID
            schedule_id = f"{report_type}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            self.scheduled_reports[schedule_id] = schedule

            return schedule_id

        except Exception as e:
            logger.error(f"Error scheduling report: {e}")
            raise

    def update_schedule(
        self,
        schedule_id: str,
        updates: Dict[str, Any]
    ) -> None:
        """
        Update a scheduled report's configuration.

        Args:
            schedule_id: ID of the scheduled report
            updates: Fields to update in the schedule
        """
        if schedule_id not in self.scheduled_reports:
            raise ValueError(f"Schedule not found: {schedule_id}")

        schedule = self.scheduled_reports[schedule_id]
        for key, value in updates.items():
            if hasattr(schedule, key):
                setattr(schedule, key, value)

    def delete_schedule(self, schedule_id: str) -> None:
        """
        Delete a scheduled report.

        Args:
            schedule_id: ID of the scheduled report
        """
        if schedule_id not in self.scheduled_reports:
            raise ValueError(f"Schedule not found: {schedule_id}")

        del self.scheduled_reports[schedule_id]

    async def get_report_preview(
        self,
        report_type: str,
        lookback_days: int = 7,
        config: Optional[Dict[str, Any]] = None
    ) -> ReportResult:
        """
        Generate a preview report for the last N days.

        Args:
            report_type: Type of report to preview
            lookback_days: Number of days to look back
            config: Optional additional configuration

        Returns:
            ReportResult containing the preview data
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=lookback_days)
        return await self.generate_report(report_type, start_date, end_date, config)

    async def aggregate_report_data(
        self,
        data: List[Dict[str, Any]],
        group_by: List[str],
        metrics: List[str],
        filters: Optional[Dict[str, Any]] = None,
        time_window: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Aggregate report data based on specified dimensions and metrics.

        Args:
            data: Raw report data to aggregate
            group_by: Dimensions to group by
            metrics: Metrics to include
            filters: Optional filters to apply
            time_window: Optional time window for aggregation

        Returns:
            List[Dict[str, Any]]: Aggregated report data
        """
        return await aggregate_performance_data(
            data=data,
            group_by=group_by,
            metrics=metrics,
            filters=filters,
            time_window=time_window
        )

    def get_scheduled_reports(self) -> Dict[str, ReportSchedule]:
        """
        Get all scheduled reports.

        Returns:
            Dict[str, ReportSchedule]: Dictionary of scheduled reports
        """
        return self.scheduled_reports.copy()

    def get_schedule(self, schedule_id: str) -> ReportSchedule:
        """
        Get a specific scheduled report.

        Args:
            schedule_id: ID of the scheduled report

        Returns:
            ReportSchedule: The scheduled report configuration
        """
        if schedule_id not in self.scheduled_reports:
            raise ValueError(f"Schedule not found: {schedule_id}")

        return self.scheduled_reports[schedule_id] 