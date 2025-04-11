"""
Base classes and interfaces for data aggregation engine.
"""
from typing import Dict, List, Any, Optional, Set, TypeVar, Generic
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from enum import Enum
from pydantic import BaseModel, Field

class TimeGranularity(str, Enum):
    """Time granularity options for aggregation."""
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    
class AggregationType(str, Enum):
    """Types of aggregation operations."""
    SUM = "sum"
    AVG = "avg"
    MIN = "min"
    MAX = "max"
    COUNT = "count"
    COUNT_DISTINCT = "count_distinct"
    WEIGHTED_AVG = "weighted_avg"

class AggregationDimension(str, Enum):
    """Available dimensions for grouping data."""
    TIME = "time"
    AD_UNIT = "ad_unit"
    CAMPAIGN = "campaign"
    CREATIVE = "creative"
    ORDER = "order"
    CUSTOM_KEY = "custom_key"
    CUSTOM_VALUE = "custom_value"
    GEOGRAPHY = "geography"
    DEVICE = "device"

class AggregationMetric(BaseModel):
    """Configuration for a metric to be aggregated."""
    name: str
    field: str
    agg_type: AggregationType
    weight_field: Optional[str] = None  # For weighted averages
    format: Optional[str] = None  # For formatting the result

class AggregationConfig(BaseModel):
    """Configuration for data aggregation."""
    time_granularity: Optional[TimeGranularity] = None
    dimensions: Set[AggregationDimension] = Field(default_factory=set)
    metrics: List[AggregationMetric]
    filters: Optional[Dict[str, Any]] = None
    sort_by: Optional[List[str]] = None
    limit: Optional[int] = None

T = TypeVar('T')
R = TypeVar('R')

class DataAggregator(ABC, Generic[T, R]):
    """Base class for data aggregators."""
    
    def __init__(self, config: AggregationConfig):
        """Initialize the aggregator with configuration.
        
        Args:
            config: Aggregation configuration
        """
        self.config = config
        self._validate_config()
    
    def _validate_config(self) -> None:
        """Validate the aggregation configuration."""
        if self.config.time_granularity and AggregationDimension.TIME not in self.config.dimensions:
            self.config.dimensions.add(AggregationDimension.TIME)
        
        for metric in self.config.metrics:
            if metric.agg_type == AggregationType.WEIGHTED_AVG and not metric.weight_field:
                raise ValueError(f"Weight field required for weighted average metric: {metric.name}")
    
    @abstractmethod
    async def aggregate(self, data: List[T]) -> List[R]:
        """Aggregate the input data according to configuration.
        
        Args:
            data: List of input data items to aggregate
            
        Returns:
            List of aggregated results
        """
        pass
    
    def _group_by_dimensions(self, data: List[T]) -> Dict[str, List[T]]:
        """Group data by configured dimensions.
        
        Args:
            data: List of data items to group
            
        Returns:
            Dictionary of grouped data
        """
        groups: Dict[str, List[T]] = {}
        
        for item in data:
            key_parts = []
            
            for dimension in self.config.dimensions:
                if dimension == AggregationDimension.TIME:
                    timestamp = self._get_timestamp(item)
                    if timestamp:
                        key_parts.append(self._format_timestamp(timestamp))
                else:
                    value = self._get_dimension_value(item, dimension)
                    if value:
                        key_parts.append(str(value))
            
            if key_parts:
                group_key = "|".join(key_parts)
                if group_key not in groups:
                    groups[group_key] = []
                groups[group_key].append(item)
        
        return groups
    
    def _format_timestamp(self, timestamp: datetime) -> str:
        """Format timestamp according to configured granularity.
        
        Args:
            timestamp: Datetime to format
            
        Returns:
            Formatted timestamp string
        """
        if not self.config.time_granularity:
            return timestamp.isoformat()
            
        if self.config.time_granularity == TimeGranularity.HOURLY:
            return timestamp.strftime("%Y-%m-%d %H:00:00")
        elif self.config.time_granularity == TimeGranularity.DAILY:
            return timestamp.strftime("%Y-%m-%d")
        elif self.config.time_granularity == TimeGranularity.WEEKLY:
            # Start of week (Monday)
            week_start = timestamp - timedelta(days=timestamp.weekday())
            return week_start.strftime("%Y-%m-%d")
        else:  # MONTHLY
            return timestamp.strftime("%Y-%m")
    
    @abstractmethod
    def _get_timestamp(self, item: T) -> Optional[datetime]:
        """Extract timestamp from data item.
        
        Args:
            item: Data item
            
        Returns:
            Timestamp if available
        """
        pass
    
    @abstractmethod
    def _get_dimension_value(self, item: T, dimension: AggregationDimension) -> Any:
        """Extract dimension value from data item.
        
        Args:
            item: Data item
            dimension: Dimension to extract
            
        Returns:
            Dimension value
        """
        pass
    
    def _calculate_metric(self, items: List[T], metric: AggregationMetric) -> Any:
        """Calculate metric value for a group of items.
        
        Args:
            items: List of items to calculate metric for
            metric: Metric configuration
            
        Returns:
            Calculated metric value
        """
        values = [self._get_metric_value(item, metric.field) for item in items]
        values = [v for v in values if v is not None]
        
        if not values:
            return None
            
        if metric.agg_type == AggregationType.SUM:
            return sum(values)
        elif metric.agg_type == AggregationType.AVG:
            return sum(values) / len(values)
        elif metric.agg_type == AggregationType.MIN:
            return min(values)
        elif metric.agg_type == AggregationType.MAX:
            return max(values)
        elif metric.agg_type == AggregationType.COUNT:
            return len(values)
        elif metric.agg_type == AggregationType.COUNT_DISTINCT:
            return len(set(values))
        elif metric.agg_type == AggregationType.WEIGHTED_AVG:
            weights = [self._get_metric_value(item, metric.weight_field) for item in items]
            weights = [w for w in weights if w is not None]
            if not weights:
                return None
            return sum(v * w for v, w in zip(values, weights)) / sum(weights)
        
        return None
    
    @abstractmethod
    def _get_metric_value(self, item: T, field: str) -> Any:
        """Extract metric value from data item.
        
        Args:
            item: Data item
            field: Field to extract
            
        Returns:
            Metric value
        """
        pass 