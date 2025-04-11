"""
Tests for inventory data aggregation.
"""
import pytest
from datetime import datetime, timedelta, UTC
from typing import List

from src.reporting.aggregation.base import (
    TimeGranularity,
    AggregationDimension,
    AggregationType,
    AggregationMetric
)
from src.reporting.aggregation.inventory import (
    InventoryDataPoint,
    AggregatedInventoryData,
    create_inventory_aggregator
)

@pytest.fixture
def sample_data() -> List[InventoryDataPoint]:
    """Create sample inventory data points."""
    base_time = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    
    return [
        # Homepage Banner - Day 1
        InventoryDataPoint(
            timestamp=base_time,
            ad_unit_id="unit1",
            ad_unit_name="Homepage Banner",
            available_impressions=100000,
            delivered_impressions=75000,
            forecasted_impressions=85000,
            revenue=1500.50,
            custom_targeting={"genre": "sports"},
            geography="US",
            device="desktop"
        ),
        InventoryDataPoint(
            timestamp=base_time + timedelta(hours=1),
            ad_unit_id="unit1",
            ad_unit_name="Homepage Banner",
            available_impressions=100000,
            delivered_impressions=80000,
            forecasted_impressions=85000,
            revenue=1600.75,
            custom_targeting={"genre": "news"},
            geography="US",
            device="mobile"
        ),
        # Article Sidebar - Day 1
        InventoryDataPoint(
            timestamp=base_time,
            ad_unit_id="unit2",
            ad_unit_name="Article Sidebar",
            available_impressions=50000,
            delivered_impressions=30000,
            forecasted_impressions=40000,
            revenue=750.25,
            custom_targeting={"genre": "sports"},
            geography="UK",
            device="desktop"
        ),
        # Homepage Banner - Day 2
        InventoryDataPoint(
            timestamp=base_time + timedelta(days=1),
            ad_unit_id="unit1",
            ad_unit_name="Homepage Banner",
            available_impressions=100000,
            delivered_impressions=70000,
            forecasted_impressions=85000,
            revenue=1400.00,
            custom_targeting={"genre": "sports"},
            geography="US",
            device="desktop"
        )
    ]

async def test_time_based_aggregation(sample_data):
    """Test aggregation by time granularity."""
    aggregator = create_inventory_aggregator(
        time_granularity=TimeGranularity.DAILY,
        dimensions={AggregationDimension.TIME}
    )
    
    results = await aggregator.aggregate(sample_data)
    
    assert len(results) == 2  # Two distinct days
    
    day1_data = next(r for r in results if r.dimensions["time"].endswith(sample_data[0].timestamp.strftime("%Y-%m-%d")))
    assert day1_data.metrics["available_impressions"] == 250000  # 100k + 100k + 50k
    assert day1_data.metrics["delivered_impressions"] == 185000  # 75k + 80k + 30k
    assert day1_data.metrics["revenue"] == "$3,851.50"  # 1500.50 + 1600.75 + 750.25

async def test_dimension_based_aggregation(sample_data):
    """Test aggregation by dimensions."""
    aggregator = create_inventory_aggregator(
        dimensions={AggregationDimension.AD_UNIT, AggregationDimension.DEVICE}
    )
    
    results = await aggregator.aggregate(sample_data)
    
    # Should have 3 combinations: Homepage/desktop, Homepage/mobile, Sidebar/desktop
    assert len(results) == 3
    
    # Check Homepage Banner desktop metrics
    homepage_desktop = next(
        r for r in results 
        if r.dimensions["ad_unit"] == "unit1" and r.dimensions["device"] == "desktop"
    )
    assert homepage_desktop.metrics["available_impressions"] == 200000  # Two entries
    assert homepage_desktop.metrics["delivered_impressions"] == 145000  # 75k + 70k
    assert homepage_desktop.metrics["fill_rate"] == "72.5%"  # (75k + 70k) / (100k + 100k) * 100

async def test_filtered_aggregation(sample_data):
    """Test aggregation with filters."""
    aggregator = create_inventory_aggregator(
        dimensions={AggregationDimension.AD_UNIT},
        filters={"geography": "US"}
    )
    
    results = await aggregator.aggregate(sample_data)
    
    assert len(results) == 1  # Only Homepage Banner has US traffic
    assert results[0].dimensions["ad_unit"] == "unit1"
    assert results[0].metrics["available_impressions"] == 300000  # Three entries
    assert results[0].metrics["revenue"] == "$4,501.25"  # Sum of US revenue

async def test_sorted_aggregation(sample_data):
    """Test aggregation with sorting."""
    aggregator = create_inventory_aggregator(
        dimensions={AggregationDimension.AD_UNIT},
        sort_by=["-revenue"]  # Sort by revenue descending
    )
    
    results = await aggregator.aggregate(sample_data)
    
    assert len(results) == 2  # Two ad units
    assert results[0].dimensions["ad_unit"] == "unit1"  # Higher revenue
    assert results[1].dimensions["ad_unit"] == "unit2"  # Lower revenue

async def test_limited_aggregation(sample_data):
    """Test aggregation with result limiting."""
    aggregator = create_inventory_aggregator(
        dimensions={AggregationDimension.AD_UNIT},
        sort_by=["-revenue"],
        limit=1
    )
    
    results = await aggregator.aggregate(sample_data)
    
    assert len(results) == 1  # Limited to 1 result
    assert results[0].dimensions["ad_unit"] == "unit1"  # Highest revenue unit

async def test_custom_metrics(sample_data):
    """Test aggregation with custom metrics."""
    metrics = [
        AggregationMetric(
            name="total_impressions",
            field="delivered_impressions",
            agg_type=AggregationType.SUM
        ),
        AggregationMetric(
            name="avg_revenue",
            field="revenue",
            agg_type=AggregationType.AVG,
            format="${:.2f}"
        ),
        AggregationMetric(
            name="max_fill_rate",
            field="delivered_impressions",
            agg_type=AggregationType.MAX
        )
    ]
    
    aggregator = create_inventory_aggregator(
        dimensions={AggregationDimension.AD_UNIT},
        metrics=metrics
    )
    
    results = await aggregator.aggregate(sample_data)
    
    homepage = next(r for r in results if r.dimensions["ad_unit"] == "unit1")
    assert homepage.metrics["total_impressions"] == 225000  # 75k + 80k + 70k
    assert homepage.metrics["avg_revenue"] == "$1,500.42"  # (1500.50 + 1600.75 + 1400.00) / 3
    assert homepage.metrics["max_fill_rate"] == 80000  # Highest delivered impressions

async def test_weighted_average_calculation(sample_data):
    """Test weighted average calculations."""
    metrics = [
        AggregationMetric(
            name="weighted_fill_rate",
            field="delivered_impressions",
            agg_type=AggregationType.WEIGHTED_AVG,
            weight_field="available_impressions",
            format="{:.1f}%"
        )
    ]
    
    aggregator = create_inventory_aggregator(
        dimensions={AggregationDimension.GEOGRAPHY},
        metrics=metrics
    )
    
    results = await aggregator.aggregate(sample_data)
    
    us_data = next(r for r in results if r.dimensions["geography"] == "US")
    # (75k + 80k + 70k) / (100k + 100k + 100k) * 100 = 75%
    assert us_data.metrics["weighted_fill_rate"] == "75.0%" 