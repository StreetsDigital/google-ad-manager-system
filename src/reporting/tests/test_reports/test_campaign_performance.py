"""
Tests for campaign performance report generator.
"""
import pytest
from datetime import datetime, timedelta, UTC
from unittest.mock import Mock, AsyncMock, patch
from src.reporting.reports.base import ReportConfig
from src.reporting.reports.campaign_performance import CampaignPerformanceReport, CampaignMetrics
from src.tools.soap_tools import SoapToolAdapter

@pytest.fixture
def report_config():
    """Create a sample report configuration."""
    return ReportConfig(
        start_date=datetime.now(UTC) - timedelta(days=30),
        end_date=datetime.now(UTC),
        filters={"status": "active"},
        format="json",
        include_metadata=True
    )

@pytest.fixture
def mock_adapter():
    """Create a mock SOAP adapter."""
    adapter = Mock(spec=SoapToolAdapter)
    adapter.registry = Mock()
    
    # Mock the SOAP tool response
    mock_soap_tool = AsyncMock()
    mock_soap_tool.return_value = {
        "status": "success",
        "data": {
            "results": [
                {
                    "id": "campaign1",
                    "name": "Summer Sale 2024",
                    "impressions": 10000,
                    "clicks": 250,
                    "conversions": 25,
                    "revenue": 1250.50
                },
                {
                    "id": "campaign2",
                    "name": "Brand Awareness Q2",
                    "impressions": 25000,
                    "clicks": 500,
                    "conversions": 40,
                    "revenue": 2000.75
                }
            ]
        }
    }
    adapter.registry.get_tool.return_value = mock_soap_tool
    return adapter

@pytest.fixture
def campaign_metrics():
    """Create sample campaign metrics."""
    metrics = CampaignMetrics(
        impressions=10000,
        clicks=500,
        conversions=50,
        revenue=2500.00
    )
    metrics.calculate_rates()
    return metrics

async def test_campaign_metrics_calculation():
    """Test campaign metrics calculations."""
    metrics = CampaignMetrics(
        impressions=1000,
        clicks=100,
        conversions=10,
        revenue=500.00
    )
    metrics.calculate_rates()
    
    assert metrics.ctr == 10.0  # 100 clicks / 1000 impressions * 100
    assert metrics.conversion_rate == 10.0  # 10 conversions / 100 clicks * 100

async def test_campaign_performance_report_generation(report_config, mock_adapter):
    """Test campaign performance report generation with mocked SOAP data."""
    report_generator = CampaignPerformanceReport(report_config, mock_adapter)
    result = await report_generator.generate()
    
    # Verify report structure
    assert result.metadata is not None
    assert result.data is not None
    assert result.summary is not None
    
    # Verify metadata
    assert result.metadata.report_type == "CampaignPerformanceReport"
    assert isinstance(result.metadata.generated_at, datetime)
    
    # Verify data
    assert "campaigns" in result.data
    assert len(result.data["campaigns"]) == 2
    
    # Verify campaign data structure
    campaign = result.data["campaigns"][0]
    assert campaign["id"] == "campaign1"
    assert campaign["name"] == "Summer Sale 2024"
    
    # Verify metrics
    metrics = campaign["metrics"]
    assert metrics["impressions"] == 10000
    assert metrics["clicks"] == 250
    assert metrics["conversions"] == 25
    assert metrics["revenue"] == 1250.50
    
    # Verify summary calculations
    summary = result.summary
    aggregated = summary["aggregated_metrics"]
    assert aggregated["impressions"] == 35000  # Sum of both campaigns
    assert aggregated["clicks"] == 750
    assert aggregated["conversions"] == 65
    assert aggregated["revenue"] == 3251.25

async def test_campaign_performance_report_soap_error(report_config, mock_adapter):
    """Test handling of SOAP client errors."""
    # Mock SOAP tool to return an error
    mock_soap_tool = AsyncMock()
    mock_soap_tool.return_value = {
        "status": "error",
        "message": "Failed to fetch campaign data"
    }
    mock_adapter.registry.get_tool.return_value = mock_soap_tool
    
    report_generator = CampaignPerformanceReport(report_config, mock_adapter)
    
    with pytest.raises(Exception) as exc_info:
        await report_generator.generate()
    
    assert "Failed to fetch campaign data" in str(exc_info.value)

async def test_campaign_performance_report_empty_data(report_config, mock_adapter):
    """Test report generation with empty campaign data."""
    # Mock SOAP tool to return empty results
    mock_soap_tool = AsyncMock()
    mock_soap_tool.return_value = {
        "status": "success",
        "data": {
            "results": []
        }
    }
    mock_adapter.registry.get_tool.return_value = mock_soap_tool
    
    report_generator = CampaignPerformanceReport(report_config, mock_adapter)
    result = await report_generator.generate()
    
    assert len(result.data["campaigns"]) == 0
    assert result.summary["total_campaigns"] == 0
    assert result.summary["aggregated_metrics"]["impressions"] == 0

async def test_campaign_performance_report_date_range(report_config, mock_adapter):
    """Test proper date range formatting in SOAP request."""
    report_generator = CampaignPerformanceReport(report_config, mock_adapter)
    await report_generator.generate()
    
    # Verify the SOAP tool was called with correct date range
    mock_soap_tool = mock_adapter.registry.get_tool.return_value
    call_args = mock_soap_tool.call_args[1]
    
    assert "params" in call_args
    assert "dateRange" in call_args["params"]
    date_range = call_args["params"]["dateRange"]
    
    # Verify date format and timezone handling
    start_date = datetime.strptime(date_range["startDate"], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=UTC)
    end_date = datetime.strptime(date_range["endDate"], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=UTC)
    
    assert start_date == report_config.start_date.replace(microsecond=0)
    assert end_date == report_config.end_date.replace(microsecond=0) 