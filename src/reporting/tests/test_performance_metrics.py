import pytest
from datetime import datetime, timedelta
from typing import List, Dict, Any

from src.reporting.aggregation import aggregate_performance_data

@pytest.fixture
def sample_performance_data() -> List[Dict[str, Any]]:
    """
    Fixture providing sample performance data for testing.
    
    Returns:
        List[Dict[str, Any]]: List of performance data records
    """
    base_date = datetime(2023, 1, 1)
    data = []
    
    # Generate sample data across multiple dimensions
    for day in range(3):  # 3 days of data
        date = base_date + timedelta(days=day)
        for ad_unit in ["banner_1", "video_1", "native_1"]:
            for device in ["mobile", "desktop", "tablet"]:
                data.append({
                    "date": date,
                    "ad_unit": ad_unit,
                    "device": device,
                    "impressions": 10000 + (day * 1000),
                    "viewable_impressions": 8000 + (day * 800),  # ~80% viewability
                    "clicks": 200 + (day * 20),  # ~2% CTR
                    "revenue": 500.0 + (day * 50.0)
                })
    return data

@pytest.mark.asyncio
async def test_click_metrics(sample_performance_data):
    """Test click-related metrics aggregation."""
    result = await aggregate_performance_data(
        data=sample_performance_data,
        group_by=["date"],
        metrics=["clicks", "ctr", "total_impressions"]
    )
    
    assert len(result) == 3  # 3 days of data
    for row in result:
        assert "clicks" in row
        assert "ctr" in row
        assert row["ctr"] == (row["clicks"] / row["total_impressions"]) * 100  # CTR as percentage

@pytest.mark.asyncio
async def test_viewability_metrics(sample_performance_data):
    """Test viewability metrics aggregation."""
    result = await aggregate_performance_data(
        data=sample_performance_data,
        group_by=["ad_unit"],
        metrics=["viewable_impressions", "viewability_rate"]
    )
    
    assert len(result) == 3  # 3 ad units
    for row in result:
        assert "viewable_impressions" in row
        assert "viewability_rate" in row
        # Viewability rate should be between 0 and 100%
        assert 0 <= row["viewability_rate"] <= 100

@pytest.mark.asyncio
async def test_combined_performance_metrics(sample_performance_data):
    """Test combination of all performance metrics."""
    result = await aggregate_performance_data(
        data=sample_performance_data,
        group_by=["ad_unit", "device"],
        metrics=[
            "impressions",
            "viewable_impressions",
            "clicks",
            "ctr",
            "viewability_rate",
            "revenue"
        ]
    )
    
    assert len(result) == 9  # 3 ad units * 3 devices
    for row in result:
        # Verify all metrics are present
        assert all(metric in row for metric in [
            "impressions",
            "viewable_impressions",
            "clicks",
            "ctr",
            "viewability_rate",
            "revenue"
        ])
        
        # Verify metric calculations
        assert row["ctr"] == (row["clicks"] / row["impressions"]) * 100
        assert row["viewability_rate"] == (row["viewable_impressions"] / row["impressions"]) * 100

@pytest.mark.asyncio
async def test_metric_filtering(sample_performance_data):
    """Test filtering of performance metrics."""
    result = await aggregate_performance_data(
        data=sample_performance_data,
        group_by=["ad_unit"],
        metrics=["clicks", "ctr"],
        filters={
            "ctr": {"min": 2.0},  # Only show entries with CTR >= 2%
            "device": "mobile"  # Filter by device type
        }
    )
    
    for row in result:
        assert row["ctr"] >= 2.0  # Verify CTR filter
        
@pytest.mark.asyncio
async def test_time_based_performance(sample_performance_data):
    """Test time-based aggregation of performance metrics."""
    result = await aggregate_performance_data(
        data=sample_performance_data,
        group_by=["date"],
        metrics=[
            "impressions",
            "viewable_impressions",
            "clicks",
            "ctr",
            "viewability_rate"
        ],
        time_window="daily"
    )
    
    assert len(result) == 3  # 3 days
    dates = [row["date"] for row in result]
    assert dates == sorted(dates)  # Verify chronological order 