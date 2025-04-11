import pytest
from datetime import datetime, timedelta
from typing import List, Dict, Any

from src.reporting.aggregation import aggregate_inventory_data

@pytest.fixture
def sample_data() -> List[Dict[str, Any]]:
    """
    Fixture providing sample inventory data for testing.
    
    Returns:
        List[Dict[str, Any]]: List of inventory data records
    """
    base_date = datetime(2023, 1, 1)
    data = []
    
    # Generate sample data across multiple dimensions
    for day in range(3):  # 3 days of data
        date = base_date + timedelta(days=day)
        for ad_unit in ["banner_1", "video_1", "native_1"]:
            for device in ["mobile", "desktop", "tablet"]:
                for geo in ["US", "UK", "CA"]:
                    data.append({
                        "date": date,
                        "ad_unit": ad_unit,
                        "device": device,
                        "geo": geo,
                        "impressions": 1000 + (day * 100),
                        "revenue": 500.0 + (day * 50.0),
                        "requests": 2000 + (day * 200),
                        "fill_rate": 0.5 + (day * 0.1)
                    })
    return data

@pytest.mark.asyncio
async def test_time_based_aggregation(sample_data):
    """Test daily aggregation of inventory data."""
    result = await aggregate_inventory_data(
        data=sample_data,
        group_by=["date"],
        metrics=["impressions", "revenue"]
    )
    
    assert len(result) == 3  # 3 days of data
    assert all("date" in row for row in result)
    assert all("impressions" in row and "revenue" in row for row in result)
    
    # Verify ascending date order
    dates = [row["date"] for row in result]
    assert dates == sorted(dates)

@pytest.mark.asyncio
async def test_dimension_based_aggregation(sample_data):
    """Test aggregation by ad unit and device."""
    result = await aggregate_inventory_data(
        data=sample_data,
        group_by=["ad_unit", "device"],
        metrics=["impressions", "revenue"]
    )
    
    assert len(result) == 9  # 3 ad units * 3 devices
    assert all({"ad_unit", "device"}.issubset(row.keys()) for row in result)

@pytest.mark.asyncio
async def test_filtered_aggregation(sample_data):
    """Test aggregation with geographic filter."""
    result = await aggregate_inventory_data(
        data=sample_data,
        group_by=["date"],
        metrics=["impressions", "revenue"],
        filters={"geo": "US"}
    )
    
    assert len(result) == 3  # 3 days
    # Verify only US data is included
    total_records = sum(len([r for r in sample_data if r["geo"] == "US"]))
    assert total_records == sum(r["impressions"] for r in result)

@pytest.mark.asyncio
async def test_sorted_aggregation(sample_data):
    """Test sorting results by revenue."""
    result = await aggregate_inventory_data(
        data=sample_data,
        group_by=["ad_unit"],
        metrics=["revenue"],
        sort_by={"revenue": "desc"}
    )
    
    revenues = [row["revenue"] for row in result]
    assert revenues == sorted(revenues, reverse=True)

@pytest.mark.asyncio
async def test_limited_aggregation(sample_data):
    """Test limiting number of results."""
    limit = 2
    result = await aggregate_inventory_data(
        data=sample_data,
        group_by=["ad_unit"],
        metrics=["revenue"],
        limit=limit
    )
    
    assert len(result) == limit

@pytest.mark.asyncio
async def test_custom_metrics(sample_data):
    """Test calculation of custom metrics."""
    result = await aggregate_inventory_data(
        data=sample_data,
        group_by=["ad_unit"],
        metrics=["total_impressions", "avg_revenue", "max_fill_rate"]
    )
    
    assert all({"total_impressions", "avg_revenue", "max_fill_rate"}.issubset(row.keys()) 
              for row in result)
    
    # Verify calculations for first row
    first_ad_unit = result[0]["ad_unit"]
    ad_unit_data = [r for r in sample_data if r["ad_unit"] == first_ad_unit]
    
    expected_impressions = sum(r["impressions"] for r in ad_unit_data)
    expected_avg_revenue = sum(r["revenue"] for r in ad_unit_data) / len(ad_unit_data)
    expected_max_fill_rate = max(r["fill_rate"] for r in ad_unit_data)
    
    assert abs(result[0]["total_impressions"] - expected_impressions) < 0.01
    assert abs(result[0]["avg_revenue"] - expected_avg_revenue) < 0.01
    assert abs(result[0]["max_fill_rate"] - expected_max_fill_rate) < 0.01

@pytest.mark.asyncio
async def test_weighted_average(sample_data):
    """Test weighted average calculation for fill rates."""
    result = await aggregate_inventory_data(
        data=sample_data,
        group_by=["ad_unit"],
        metrics=["weighted_fill_rate"],
        weight_by="impressions"
    )
    
    assert all("weighted_fill_rate" in row for row in result)
    
    # Verify weighted average calculation for first row
    first_ad_unit = result[0]["ad_unit"]
    ad_unit_data = [r for r in sample_data if r["ad_unit"] == first_ad_unit]
    
    total_impressions = sum(r["impressions"] for r in ad_unit_data)
    expected_weighted_fill_rate = sum(
        r["fill_rate"] * r["impressions"] for r in ad_unit_data
    ) / total_impressions
    
    assert abs(result[0]["weighted_fill_rate"] - expected_weighted_fill_rate) < 0.01

@pytest.mark.asyncio
async def test_edge_case_empty_data():
    """Test aggregation with empty dataset."""
    result = await aggregate_inventory_data(
        data=[],
        group_by=["date"],
        metrics=["impressions"]
    )
    assert len(result) == 0

@pytest.mark.asyncio
async def test_edge_case_null_values(sample_data):
    """Test handling of null values in the dataset."""
    # Add a record with null values
    sample_data.append({
        "date": datetime(2023, 1, 1),
        "ad_unit": "banner_1",
        "device": "mobile",
        "geo": "US",
        "impressions": None,
        "revenue": None,
        "requests": None,
        "fill_rate": None
    })
    
    result = await aggregate_inventory_data(
        data=sample_data,
        group_by=["ad_unit"],
        metrics=["impressions", "revenue"]
    )
    
    # Verify null values are handled gracefully
    assert all(isinstance(row["impressions"], (int, float)) for row in result)
    assert all(isinstance(row["revenue"], (int, float)) for row in result) 