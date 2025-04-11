"""Tests for reporting service."""

import pytest
from unittest.mock import Mock, AsyncMock
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

from src.reporting.services import ReportingService, ReportSchedule
from src.campaigns.line_items.connection_pool import ConnectionPool
from src.reporting.reports.base import ReportResult, ReportMetadata

@pytest.fixture
def mock_connection():
    """Create a mock connection."""
    connection = AsyncMock()
    
    # Mock successful report data
    connection.execute_batch.return_value = {
        "status": "success",
        "data": {
            "campaigns": [
                {
                    "id": "campaign1",
                    "name": "Test Campaign",
                    "metrics": {
                        "impressions": 10000,
                        "clicks": 200,
                        "conversions": 20,
                        "revenue": 1000.50
                    }
                }
            ]
        }
    }
    
    return connection

@pytest.fixture
def mock_pool(mock_connection):
    """Create a mock connection pool."""
    pool = Mock(spec=ConnectionPool)
    pool.get_connection.return_value.__aenter__.return_value = mock_connection
    pool.get_connection.return_value.__aexit__.return_value = None
    return pool

@pytest.fixture
def sample_report_config():
    """Create a sample report configuration."""
    return {
        "filters": {
            "status": "ACTIVE",
            "revenue_min": 100
        },
        "email_recipients": ["user@example.com"],
        "export_format": "CSV"
    }

class TestReportingService:
    """Test cases for ReportingService."""

    @pytest.mark.asyncio
    async def test_generate_report(self, mock_pool, mock_connection):
        """Test generating a report."""
        service = ReportingService(mock_pool)
        result = await service.generate_report(
            report_type="campaign_performance",
            start_date=datetime.now(timezone.UTC) - timedelta(days=7),
            end_date=datetime.now(timezone.UTC)
        )
        
        assert isinstance(result, ReportResult)
        assert result.data is not None
        assert "campaigns" in result.data
        mock_connection.execute_batch.assert_called_once()

    @pytest.mark.asyncio
    async def test_schedule_report(self, mock_pool, sample_report_config):
        """Test scheduling a report."""
        service = ReportingService(mock_pool)
        schedule_id = await service.schedule_report(
            report_type="campaign_performance",
            frequency="daily",
            time_of_day="09:00",
            config=sample_report_config
        )
        
        assert schedule_id is not None
        assert schedule_id in service.scheduled_reports
        schedule = service.scheduled_reports[schedule_id]
        assert schedule.report_type == "campaign_performance"
        assert schedule.frequency == "daily"
        assert schedule.time_of_day == "09:00"
        assert schedule.email_recipients == ["user@example.com"]

    def test_update_schedule(self, mock_pool, sample_report_config):
        """Test updating a report schedule."""
        service = ReportingService(mock_pool)
        schedule_id = "test_schedule"
        service.scheduled_reports[schedule_id] = ReportSchedule(
            report_type="campaign_performance",
            frequency="daily",
            time_of_day="09:00"
        )
        
        updates = {
            "frequency": "weekly",
            "time_of_day": "10:00",
            "enabled": False
        }
        service.update_schedule(schedule_id, updates)
        
        schedule = service.scheduled_reports[schedule_id]
        assert schedule.frequency == "weekly"
        assert schedule.time_of_day == "10:00"
        assert not schedule.enabled

    def test_delete_schedule(self, mock_pool):
        """Test deleting a report schedule."""
        service = ReportingService(mock_pool)
        schedule_id = "test_schedule"
        service.scheduled_reports[schedule_id] = ReportSchedule(
            report_type="campaign_performance",
            frequency="daily",
            time_of_day="09:00"
        )
        
        service.delete_schedule(schedule_id)
        assert schedule_id not in service.scheduled_reports

    @pytest.mark.asyncio
    async def test_get_report_preview(self, mock_pool, mock_connection):
        """Test getting a report preview."""
        service = ReportingService(mock_pool)
        result = await service.get_report_preview(
            report_type="campaign_performance",
            lookback_days=7
        )
        
        assert isinstance(result, ReportResult)
        assert result.data is not None
        assert "campaigns" in result.data
        mock_connection.execute_batch.assert_called_once()

    @pytest.mark.asyncio
    async def test_aggregate_report_data(self, mock_pool):
        """Test aggregating report data."""
        service = ReportingService(mock_pool)
        data = [
            {
                "date": "2024-03-19",
                "campaign": "Campaign 1",
                "impressions": 5000,
                "clicks": 100,
                "revenue": 500.0
            },
            {
                "date": "2024-03-19",
                "campaign": "Campaign 2",
                "impressions": 3000,
                "clicks": 60,
                "revenue": 300.0
            }
        ]
        
        result = await service.aggregate_report_data(
            data=data,
            group_by=["date"],
            metrics=["impressions", "clicks", "revenue"]
        )
        
        assert len(result) == 1  # One date
        assert result[0]["impressions"] == 8000
        assert result[0]["clicks"] == 160
        assert result[0]["revenue"] == 800.0

    def test_get_scheduled_reports(self, mock_pool):
        """Test getting all scheduled reports."""
        service = ReportingService(mock_pool)
        schedule1 = ReportSchedule(
            report_type="campaign_performance",
            frequency="daily",
            time_of_day="09:00"
        )
        schedule2 = ReportSchedule(
            report_type="inventory_usage",
            frequency="weekly",
            time_of_day="10:00"
        )
        
        service.scheduled_reports = {
            "schedule1": schedule1,
            "schedule2": schedule2
        }
        
        reports = service.get_scheduled_reports()
        assert len(reports) == 2
        assert "schedule1" in reports
        assert "schedule2" in reports

    def test_get_schedule(self, mock_pool):
        """Test getting a specific schedule."""
        service = ReportingService(mock_pool)
        schedule_id = "test_schedule"
        schedule = ReportSchedule(
            report_type="campaign_performance",
            frequency="daily",
            time_of_day="09:00"
        )
        service.scheduled_reports[schedule_id] = schedule
        
        result = service.get_schedule(schedule_id)
        assert result == schedule

    def test_invalid_schedule_id(self, mock_pool):
        """Test error handling for invalid schedule ID."""
        service = ReportingService(mock_pool)
        with pytest.raises(ValueError):
            service.get_schedule("nonexistent_schedule")

    def test_invalid_frequency(self, mock_pool):
        """Test error handling for invalid frequency."""
        service = ReportingService(mock_pool)
        with pytest.raises(ValueError):
            service.schedule_report(
                report_type="campaign_performance",
                frequency="invalid",
                time_of_day="09:00"
            )

    @pytest.mark.asyncio
    async def test_unsupported_report_type(self, mock_pool):
        """Test error handling for unsupported report type."""
        service = ReportingService(mock_pool)
        with pytest.raises(ValueError):
            await service.generate_report(
                report_type="unsupported_type",
                start_date=datetime.now(timezone.UTC) - timedelta(days=7),
                end_date=datetime.now(timezone.UTC)
            ) 