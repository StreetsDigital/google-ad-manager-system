"""
Inventory data aggregation implementation.
"""
from typing import Dict, List, Any, Optional
from datetime import datetime
from pydantic import BaseModel

from .base import (
    DataAggregator,
    AggregationConfig,
    AggregationDimension,
    AggregationType,
    AggregationMetric
)

class InventoryDataPoint(BaseModel):
    """Model for inventory data points."""
    timestamp: datetime
    ad_unit_id: str
    ad_unit_name: str
    available_impressions: int
    delivered_impressions: int
    forecasted_impressions: int
    revenue: float
    custom_targeting: Dict[str, str] = {}
    geography: Optional[str] = None
    device: Optional[str] = None

class AggregatedInventoryData(BaseModel):
    """Model for aggregated inventory data."""
    dimensions: Dict[str, Any]
    metrics: Dict[str, Any]

class InventoryAggregator(DataAggregator[InventoryDataPoint, AggregatedInventoryData]):
    """Aggregator for inventory data."""
    
    def _get_timestamp(self, item: InventoryDataPoint) -> Optional[datetime]:
        """Get timestamp from inventory data point."""
        return item.timestamp
    
    def _get_dimension_value(self, item: InventoryDataPoint, dimension: AggregationDimension) -> Any:
        """Get dimension value from inventory data point."""
        if dimension == AggregationDimension.AD_UNIT:
            return item.ad_unit_id
        elif dimension == AggregationDimension.CUSTOM_KEY:
            return list(item.custom_targeting.keys())[0] if item.custom_targeting else None
        elif dimension == AggregationDimension.CUSTOM_VALUE:
            return list(item.custom_targeting.values())[0] if item.custom_targeting else None
        elif dimension == AggregationDimension.GEOGRAPHY:
            return item.geography
        elif dimension == AggregationDimension.DEVICE:
            return item.device
        return None
    
    def _get_metric_value(self, item: InventoryDataPoint, field: str) -> Any:
        """Get metric value from inventory data point."""
        return getattr(item, field, None)
    
    async def aggregate(self, data: List[InventoryDataPoint]) -> List[AggregatedInventoryData]:
        """Aggregate inventory data according to configuration."""
        # Apply filters if configured
        if self.config.filters:
            data = [
                item for item in data
                if all(
                    self._get_metric_value(item, field) == value
                    for field, value in self.config.filters.items()
                )
            ]
        
        # Group data by dimensions
        groups = self._group_by_dimensions(data)
        
        # Calculate metrics for each group
        results = []
        for group_key, group_items in groups.items():
            # Parse dimension values from group key
            dimension_values = dict(zip(
                [d.value for d in self.config.dimensions],
                group_key.split("|")
            ))
            
            # Calculate configured metrics
            metric_values = {}
            for metric in self.config.metrics:
                value = self._calculate_metric(group_items, metric)
                if value is not None:
                    if metric.format:
                        try:
                            value = metric.format.format(value)
                        except (ValueError, KeyError):
                            pass  # Keep original value if formatting fails
                    metric_values[metric.name] = value
            
            results.append(AggregatedInventoryData(
                dimensions=dimension_values,
                metrics=metric_values
            ))
        
        # Sort results if configured
        if self.config.sort_by:
            for sort_field in reversed(self.config.sort_by):
                descending = sort_field.startswith("-")
                field = sort_field[1:] if descending else sort_field
                
                def sort_key(item: AggregatedInventoryData) -> Any:
                    if field in item.dimensions:
                        return item.dimensions[field]
                    return item.metrics.get(field)
                
                results.sort(
                    key=sort_key,
                    reverse=descending
                )
        
        # Apply limit if configured
        if self.config.limit is not None:
            results = results[:self.config.limit]
        
        return results

def create_inventory_aggregator(
    time_granularity=None,
    dimensions=None,
    metrics=None,
    filters=None,
    sort_by=None,
    limit=None
) -> InventoryAggregator:
    """Create an inventory aggregator with common defaults.
    
    Args:
        time_granularity: Optional time granularity for aggregation
        dimensions: Optional set of dimensions to group by
        metrics: Optional list of metrics to calculate
        filters: Optional filters to apply
        sort_by: Optional fields to sort by
        limit: Optional limit on number of results
        
    Returns:
        Configured InventoryAggregator
    """
    if metrics is None:
        metrics = [
            AggregationMetric(
                name="available_impressions",
                field="available_impressions",
                agg_type=AggregationType.SUM
            ),
            AggregationMetric(
                name="delivered_impressions",
                field="delivered_impressions",
                agg_type=AggregationType.SUM
            ),
            AggregationMetric(
                name="forecasted_impressions",
                field="forecasted_impressions",
                agg_type=AggregationType.SUM
            ),
            AggregationMetric(
                name="revenue",
                field="revenue",
                agg_type=AggregationType.SUM,
                format="${:,.2f}"
            ),
            AggregationMetric(
                name="fill_rate",
                field="delivered_impressions",
                agg_type=AggregationType.WEIGHTED_AVG,
                weight_field="available_impressions",
                format="{:.1f}%"
            )
        ]
    
    config = AggregationConfig(
        time_granularity=time_granularity,
        dimensions=set(dimensions) if dimensions else set(),
        metrics=metrics,
        filters=filters,
        sort_by=sort_by,
        limit=limit
    )
    
    return InventoryAggregator(config) 