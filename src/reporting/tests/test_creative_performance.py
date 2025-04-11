"""Tests for creative performance report generation."""
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock

from src.reporting.reports.creative_performance import CreativePerformanceReport, CreativeMetrics
from src.reporting.reports.base import ReportConfig
from src.tools.soap_tools import SoapToolAdapter

@pytest.fixture
def mock_adapter():
    """Create a mock SOAP adapter."""
    adapter = Mock(spec=SoapToolAdapter)
    adapter.registry.get_tool.return_value = AsyncMock()
    return adapter

@pytest.fixture
def sample_config():
    """Create a sample report configuration."""
    return ReportConfig(
        start_date=datetime.now() - timedelta(days=7),
        end_date=datetime.now(),
        filters={"orderIds": [123456]}
    )

@pytest.fixture
def sample_creative_data():
    """Sample creative performance data."""
    return {
        "status": "success",
        "data": {
            "results": [
                {
                    "creativeId": "1",
                    "creativeName": "Banner Ad 1",
                    "creativeType": "DISPLAY",
                    "totalImpressions": 10000,
                    "totalClicks": 150,
                    "totalInteractions": 200,
                    "averageDisplayTime": 5.5
                },
                {
                    "creativeId": "2",
                    "creativeName": "Video Ad 1",
                    "creativeType": "VIDEO",
                    "totalImpressions": 5000,
                    "totalClicks": 100,
                    "totalInteractions": 300,
                    "totalVideoCompletions": 2500,
                    "averageDisplayTime": 15.0
                }
            ]
        }
    }

@pytest.mark.asyncio
async def test_fetch_creative_data(mock_adapter, sample_config, sample_creative_data):
    """Test fetching creative data from Ad Manager."""
    # Setup
    mock_adapter.registry.get_tool.return_value.return_value = sample_creative_data
    report = CreativePerformanceReport(sample_config, mock_adapter)
    
    # Execute
    result = await report._fetch_creative_data()
    
    # Assert
    assert result == sample_creative_data["data"]["results"]
    mock_adapter.registry.get_tool.assert_called_once_with("soap.execute")
    mock_adapter.registry.get_tool.return_value.assert_called_once()

@pytest.mark.asyncio
async def test_generate_data(mock_adapter, sample_config, sample_creative_data):
    """Test generating creative performance data."""
    # Setup
    mock_adapter.registry.get_tool.return_value.return_value = sample_creative_data
    report = CreativePerformanceReport(sample_config, mock_adapter)
    
    # Execute
    result = await report._generate_data()
    
    # Assert
    assert "creatives" in result
    assert len(result["creatives"]) == 2
    
    display_creative = result["creatives"][0]
    assert display_creative["id"] == "1"
    assert display_creative["type"] == "DISPLAY"
    assert display_creative["metrics"]["impressions"] == 10000
    assert display_creative["metrics"]["clicks"] == 150
    assert display_creative["metrics"]["ctr"] == pytest.approx(1.5)  # 150/10000 * 100
    
    video_creative = result["creatives"][1]
    assert video_creative["id"] == "2"
    assert video_creative["type"] == "VIDEO"
    assert video_creative["metrics"]["completion_rate"] == pytest.approx(50.0)  # 2500/5000 * 100

@pytest.mark.asyncio
async def test_generate_summary(mock_adapter, sample_config, sample_creative_data):
    """Test generating summary metrics."""
    # Setup
    mock_adapter.registry.get_tool.return_value.return_value = sample_creative_data
    report = CreativePerformanceReport(sample_config, mock_adapter)
    data = await report._generate_data()
    
    # Execute
    summary = await report._generate_summary(data)
    
    # Assert
    assert summary["total_creatives"] == 2
    assert "aggregated_metrics" in summary
    assert "metrics_by_type" in summary
    
    agg_metrics = summary["aggregated_metrics"]
    assert agg_metrics["impressions"] == 15000  # 10000 + 5000
    assert agg_metrics["clicks"] == 250  # 150 + 100
    assert agg_metrics["ctr"] == pytest.approx(1.67)  # 250/15000 * 100
    
    type_metrics = summary["metrics_by_type"]
    assert "DISPLAY" in type_metrics
    assert "VIDEO" in type_metrics
    assert type_metrics["VIDEO"]["completion_rate"] == pytest.approx(50.0)

@pytest.mark.asyncio
async def test_fetch_creative_data_error(mock_adapter, sample_config):
    """Test error handling when fetching creative data."""
    # Setup
    mock_adapter.registry.get_tool.return_value.return_value = {
        "status": "error",
        "message": "API Error"
    }
    report = CreativePerformanceReport(sample_config, mock_adapter)
    
    # Execute and Assert
    with pytest.raises(Exception) as exc_info:
        await report._fetch_creative_data()
    assert "Failed to fetch creative data: API Error" in str(exc_info.value)

def test_creative_metrics_calculation():
    """Test calculation of derived metrics in CreativeMetrics."""
    # Setup
    metrics = CreativeMetrics(
        impressions=1000,
        clicks=50,
        interactions=100
    )
    
    # Execute
    metrics.calculate_rates()
    
    # Assert
    assert metrics.ctr == pytest.approx(5.0)  # 50/1000 * 100
    assert metrics.interaction_rate == pytest.approx(10.0)  # 100/1000 * 100

@pytest.mark.asyncio
async def test_generate_report(mock_adapter, sample_config, sample_creative_data):
    """Test end-to-end report generation."""
    # Setup
    mock_adapter.registry.get_tool.return_value.return_value = sample_creative_data
    report = CreativePerformanceReport(sample_config, mock_adapter)
    
    # Execute
    result = await report.generate()
    
    # Assert
    assert result.metadata.report_type == "creative_performance"
    assert result.metadata.start_date == sample_config.start_date
    assert result.metadata.end_date == sample_config.end_date
    assert "creatives" in result.data
    assert "total_creatives" in result.summary
    assert result.summary["total_creatives"] == 2 