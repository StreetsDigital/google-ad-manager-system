"""
Tests for inventory usage report generator.
"""
import pytest
from datetime import datetime, timedelta, UTC
from unittest.mock import Mock, AsyncMock

from src.reporting.reports.base import ReportConfig
from src.reporting.reports.inventory_usage import (
    InventoryUsageReport,
    InventoryMetrics,
    KeyValueMetrics,
    InventoryReportConfig
)
from src.tools.soap_tools import SoapToolAdapter

@pytest.fixture
def report_config():
    """Create a sample report configuration."""
    return InventoryReportConfig(
        start_date=datetime.now(UTC) - timedelta(days=30),
        end_date=datetime.now(UTC),
        filters={"status": "active"},
        format="json",
        include_metadata=True,
        target_keys={"genre", "device"}  # Specify keys we want to track
    )

@pytest.fixture
def report_config_no_keys():
    """Create a report configuration without specific target keys."""
    return InventoryReportConfig(
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
                    "adUnitId": "unit1",
                    "adUnitName": "Homepage Banner",
                    "availableImpressions": 100000,
                    "deliveredImpressions": 75000,
                    "forecastedImpressions": 85000,
                    "customTargetingKey": "genre",
                    "customTargetingValue": "sports",
                    "totalLineItemLevelImpressions": 50000,
                    "totalLineItemLevelClicks": 2500,
                    "totalLineItemLevelRevenue": 1500.50
                },
                {
                    "adUnitId": "unit1",
                    "adUnitName": "Homepage Banner",
                    "availableImpressions": 100000,
                    "deliveredImpressions": 75000,
                    "forecastedImpressions": 85000,
                    "customTargetingKey": "genre",
                    "customTargetingValue": "news",
                    "totalLineItemLevelImpressions": 25000,
                    "totalLineItemLevelClicks": 1000,
                    "totalLineItemLevelRevenue": 750.25
                },
                {
                    "adUnitId": "unit2",
                    "adUnitName": "Article Sidebar",
                    "availableImpressions": 50000,
                    "deliveredImpressions": 30000,
                    "forecastedImpressions": 40000,
                    "customTargetingKey": "device",
                    "customTargetingValue": "mobile",
                    "totalLineItemLevelImpressions": 20000,
                    "totalLineItemLevelClicks": 800,
                    "totalLineItemLevelRevenue": 400.00
                },
                {
                    "adUnitId": "unit2",
                    "adUnitName": "Article Sidebar",
                    "availableImpressions": 50000,
                    "deliveredImpressions": 30000,
                    "forecastedImpressions": 40000,
                    "customTargetingKey": "language",  # This key should be filtered out
                    "customTargetingValue": "en",
                    "totalLineItemLevelImpressions": 15000,
                    "totalLineItemLevelClicks": 600,
                    "totalLineItemLevelRevenue": 300.00
                }
            ]
        }
    }
    adapter.registry.get_tool.return_value = mock_soap_tool
    return adapter

@pytest.fixture
def inventory_metrics():
    """Create sample inventory metrics."""
    metrics = InventoryMetrics(
        available_impressions=100000,
        delivered_impressions=75000,
        forecasted_impressions=85000,
        key_value_metrics={
            "genre": [
                KeyValueMetrics(
                    key="genre",
                    value="sports",
                    impressions=50000,
                    clicks=2500,
                    revenue=1500.50
                ),
                KeyValueMetrics(
                    key="genre",
                    value="news",
                    impressions=25000,
                    clicks=1000,
                    revenue=750.25
                )
            ]
        }
    )
    metrics.calculate_rates()
    return metrics

async def test_key_value_metrics_calculation():
    """Test key-value metrics calculations."""
    metrics = KeyValueMetrics(
        key="genre",
        value="sports",
        impressions=50000,
        clicks=2500,
        revenue=1500.50
    )
    metrics.calculate_rates()
    
    assert metrics.ctr == 5.0  # 2500/50000 * 100
    assert metrics.ecpm == 30.01  # 1500.50/50000 * 1000

async def test_inventory_metrics_calculation():
    """Test inventory metrics calculations."""
    metrics = InventoryMetrics(
        available_impressions=100000,
        delivered_impressions=75000,
        forecasted_impressions=85000,
        key_value_metrics={
            "genre": [
                KeyValueMetrics(
                    key="genre",
                    value="sports",
                    impressions=50000,
                    clicks=2500,
                    revenue=1500.50
                )
            ]
        }
    )
    metrics.calculate_rates()
    
    assert metrics.fill_rate == 75.0  # 75000/100000 * 100
    assert metrics.utilization_rate == 85.0  # 85000/100000 * 100
    assert metrics.key_value_metrics["genre"][0].ctr == 5.0  # 2500/50000 * 100

async def test_inventory_usage_report_generation_with_target_keys(report_config, mock_adapter):
    """Test inventory usage report generation with specific target keys."""
    report_generator = InventoryUsageReport(report_config, mock_adapter)
    result = await report_generator.generate()
    
    # Verify report structure and basic data
    assert result.metadata is not None
    assert result.data is not None
    assert result.summary is not None
    assert result.metadata.report_type == "inventory_usage"
    
    # Verify data filtering
    ad_unit = result.data["ad_units"][0]
    metrics = ad_unit["metrics"]
    
    # Should only include specified keys
    assert set(metrics["key_value_metrics"].keys()) <= report_config.target_keys
    assert "language" not in metrics["key_value_metrics"]
    
    # Verify key-value metrics for included keys
    genre_metrics = metrics["key_value_metrics"]["genre"]
    assert len(genre_metrics) == 2
    
    sports_metrics = next(m for m in genre_metrics if m["value"] == "sports")
    assert sports_metrics["impressions"] == 50000
    assert sports_metrics["ctr"] == 5.0
    
    # Verify summary includes only target keys
    kv_summary = result.summary["key_value_summary"]
    assert set(kv_summary.keys()) <= report_config.target_keys
    assert "language" not in kv_summary

async def test_inventory_usage_report_generation_without_target_keys(report_config_no_keys, mock_adapter):
    """Test inventory usage report generation without specific target keys."""
    report_generator = InventoryUsageReport(report_config_no_keys, mock_adapter)
    result = await report_generator.generate()
    
    # Verify all keys are included
    ad_unit = result.data["ad_units"][1]  # Article Sidebar
    metrics = ad_unit["metrics"]
    
    # Should include all keys from the data
    assert "device" in metrics["key_value_metrics"]
    assert "language" in metrics["key_value_metrics"]
    
    # Verify summary includes all keys
    kv_summary = result.summary["key_value_summary"]
    assert "device" in kv_summary
    assert "language" in kv_summary

async def test_inventory_usage_report_soap_error(report_config, mock_adapter):
    """Test handling of SOAP client errors."""
    # Mock SOAP tool to return an error
    mock_soap_tool = AsyncMock()
    mock_soap_tool.return_value = {
        "status": "error",
        "message": "Failed to fetch inventory data"
    }
    mock_adapter.registry.get_tool.return_value = mock_soap_tool
    
    report_generator = InventoryUsageReport(report_config, mock_adapter)
    
    with pytest.raises(Exception) as exc_info:
        await report_generator.generate()
    
    assert "Failed to fetch inventory data" in str(exc_info.value)

async def test_inventory_usage_report_empty_data(report_config, mock_adapter):
    """Test report generation with empty inventory data."""
    # Mock SOAP tool to return empty results
    mock_soap_tool = AsyncMock()
    mock_soap_tool.return_value = {
        "status": "success",
        "data": {
            "results": []
        }
    }
    mock_adapter.registry.get_tool.return_value = mock_soap_tool
    
    report_generator = InventoryUsageReport(report_config, mock_adapter)
    result = await report_generator.generate()
    
    assert len(result.data["ad_units"]) == 0
    assert result.summary["total_ad_units"] == 0
    assert result.summary["aggregated_metrics"]["available_impressions"] == 0
    assert len(result.summary["key_value_summary"]) == 0

async def test_inventory_usage_report_date_range(report_config, mock_adapter):
    """Test proper date range formatting in SOAP request."""
    report_generator = InventoryUsageReport(report_config, mock_adapter)
    await report_generator.generate()
    
    # Verify the SOAP tool was called with correct date range
    mock_soap_tool = mock_adapter.registry.get_tool.return_value
    call_args = mock_soap_tool.call_args[1]
    
    assert "params" in call_args
    assert "dateRange" in call_args["params"]
    date_range = call_args["params"]["dateRange"]
    
    # Verify date format
    start_date = datetime.strptime(date_range["startDate"], "%Y-%m-%d").replace(tzinfo=UTC)
    end_date = datetime.strptime(date_range["endDate"], "%Y-%m-%d").replace(tzinfo=UTC)
    
    assert start_date.date() == report_config.start_date.date()
    assert end_date.date() == report_config.end_date.date()

async def test_inventory_usage_report_target_keys_parameter(report_config, mock_adapter):
    """Test that target keys are properly included in the SOAP request."""
    report_generator = InventoryUsageReport(report_config, mock_adapter)
    await report_generator.generate()
    
    # Verify the SOAP tool was called with target keys
    mock_soap_tool = mock_adapter.registry.get_tool.return_value
    call_args = mock_soap_tool.call_args[1]
    
    assert "params" in call_args
    assert "customTargetingKeyIds" in call_args["params"]
    assert set(call_args["params"]["customTargetingKeyIds"]) == report_config.target_keys 