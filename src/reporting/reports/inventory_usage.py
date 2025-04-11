"""
Inventory usage report generator implementation.
"""
from typing import Dict, Any, List, Optional, Set
from datetime import datetime
from pydantic import BaseModel, Field

from src.tools.soap_tools import SoapToolAdapter
from .base import BaseReportGenerator, ReportConfig

class KeyValueMetrics(BaseModel):
    """Model for key-value targeting metrics."""
    key: str
    value: str
    impressions: int = 0
    clicks: int = 0
    ctr: float = 0.0
    revenue: float = 0.0
    ecpm: float = 0.0

    def calculate_rates(self):
        """Calculate derived metrics."""
        if self.impressions > 0:
            self.ctr = (self.clicks / self.impressions * 100)
            self.ecpm = (self.revenue / self.impressions * 1000)

class InventoryReportConfig(ReportConfig):
    """Extended configuration for inventory reports with key-value targeting."""
    target_keys: Set[str] = Field(default_factory=set, description="Specific keys to include in the report")

class InventoryMetrics(BaseModel):
    """Model for inventory usage metrics."""
    available_impressions: int = 0
    delivered_impressions: int = 0
    forecasted_impressions: int = 0
    fill_rate: float = 0.0
    utilization_rate: float = 0.0
    key_value_metrics: Dict[str, List[KeyValueMetrics]] = Field(default_factory=dict)
    
    def calculate_rates(self):
        """Calculate derived metrics."""
        if self.available_impressions > 0:
            self.fill_rate = (self.delivered_impressions / self.available_impressions * 100)
            self.utilization_rate = (self.forecasted_impressions / self.available_impressions * 100)
        
        # Calculate rates for each key-value pair
        for metrics_list in self.key_value_metrics.values():
            for metrics in metrics_list:
                metrics.calculate_rates()

class InventoryUsageReport(BaseReportGenerator):
    """Generate inventory usage reports."""
    
    def __init__(self, config: InventoryReportConfig, adapter: SoapToolAdapter):
        """Initialize the report generator with configuration and SOAP adapter."""
        super().__init__(config)
        self.adapter = adapter
        self.report_type = "inventory_usage"
        self.config: InventoryReportConfig = config  # Type hint for specific config

    async def _fetch_inventory_data(self) -> List[Dict[str, Any]]:
        """Fetch inventory data from Google Ad Manager.
        
        Returns:
            List[Dict[str, Any]]: List of inventory data from the API
        """
        try:
            # Prepare the query parameters
            params = {
                "dateRange": {
                    "startDate": self.config.start_date.strftime("%Y-%m-%d"),
                    "endDate": self.config.end_date.strftime("%Y-%m-%d")
                },
                "dimensions": [
                    "AD_UNIT_ID",
                    "AD_UNIT_NAME",
                    "CUSTOM_TARGETING_KEY_ID",
                    "CUSTOM_TARGETING_KEY",
                    "CUSTOM_TARGETING_VALUE_ID",
                    "CUSTOM_TARGETING_VALUE"
                ],
                "metrics": [
                    "AVAILABLE_IMPRESSIONS",
                    "DELIVERED_IMPRESSIONS",
                    "FORECASTED_IMPRESSIONS",
                    "TOTAL_LINE_ITEM_LEVEL_IMPRESSIONS",
                    "TOTAL_LINE_ITEM_LEVEL_CLICKS",
                    "TOTAL_LINE_ITEM_LEVEL_REVENUE"
                ]
            }
            
            # Add targeting key filter if specific keys are requested
            if self.config.target_keys:
                params["customTargetingKeyIds"] = list(self.config.target_keys)
            
            # Add any additional filters from config
            if self.config.filters:
                params.update(self.config.filters)
            
            # Get the SOAP tool from the adapter
            soap_tool = self.adapter.registry.get_tool("soap.execute")
            
            # Execute the report query
            result = await soap_tool(
                service="InventoryService",
                method="getInventoryReport",
                params=params
            )
            
            if result["status"] != "success":
                raise Exception(f"Failed to fetch inventory data: {result.get('message', 'Unknown error')}")
            
            return result["data"]["results"]
        except Exception as e:
            raise Exception(f"Error fetching inventory data: {str(e)}") from e

    def _process_key_value_data(self, result: Dict[str, Any]) -> Dict[str, List[KeyValueMetrics]]:
        """Process key-value targeting data from a result row.
        
        Args:
            result: Raw result row from the API
            
        Returns:
            Dict[str, List[KeyValueMetrics]]: Processed key-value metrics
        """
        kv_metrics: Dict[str, List[KeyValueMetrics]] = {}
        
        if "customTargetingKey" in result and "customTargetingValue" in result:
            key = result["customTargetingKey"]
            
            # Skip if we have specific target keys and this key isn't one of them
            if self.config.target_keys and key not in self.config.target_keys:
                return kv_metrics
                
            value = result["customTargetingValue"]
            
            if key not in kv_metrics:
                kv_metrics[key] = []
            
            metrics = KeyValueMetrics(
                key=key,
                value=value,
                impressions=result.get("totalLineItemLevelImpressions", 0),
                clicks=result.get("totalLineItemLevelClicks", 0),
                revenue=float(result.get("totalLineItemLevelRevenue", 0.0))
            )
            metrics.calculate_rates()
            kv_metrics[key].append(metrics)
        
        return kv_metrics

    async def _generate_data(self) -> Dict[str, Any]:
        """Generate inventory usage data.
        
        Returns:
            Dict[str, Any]: Inventory usage metrics and analysis.
        """
        # Fetch inventory data from Ad Manager
        inventory_results = await self._fetch_inventory_data()
        
        # Process and format the inventory data
        ad_units = []
        ad_unit_data: Dict[str, Dict[str, Any]] = {}
        
        for result in inventory_results:
            ad_unit_id = result["adUnitId"]
            
            # Initialize or get existing ad unit data
            if ad_unit_id not in ad_unit_data:
                ad_unit_data[ad_unit_id] = {
                    "id": ad_unit_id,
                    "name": result["adUnitName"],
                    "metrics": InventoryMetrics(
                        available_impressions=result.get("availableImpressions", 0),
                        delivered_impressions=result.get("deliveredImpressions", 0),
                        forecasted_impressions=result.get("forecastedImpressions", 0)
                    )
                }
            
            # Process key-value data
            kv_metrics = self._process_key_value_data(result)
            for key, metrics_list in kv_metrics.items():
                if key not in ad_unit_data[ad_unit_id]["metrics"].key_value_metrics:
                    ad_unit_data[ad_unit_id]["metrics"].key_value_metrics[key] = []
                ad_unit_data[ad_unit_id]["metrics"].key_value_metrics[key].extend(metrics_list)
        
        # Calculate rates and format final output
        for ad_unit in ad_unit_data.values():
            ad_unit["metrics"].calculate_rates()
            ad_units.append({
                "id": ad_unit["id"],
                "name": ad_unit["name"],
                "metrics": ad_unit["metrics"].dict()
            })
        
        return {"ad_units": ad_units}

    async def _generate_summary(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate summary metrics across all ad units.
        
        Args:
            data (Dict[str, Any]): The inventory usage data.
            
        Returns:
            Dict[str, Any]: Aggregated inventory metrics.
        """
        total_metrics = InventoryMetrics()
        kv_summary: Dict[str, Dict[str, KeyValueMetrics]] = {}
        
        # Aggregate metrics across all ad units
        for ad_unit in data["ad_units"]:
            metrics = ad_unit["metrics"]
            total_metrics.available_impressions += metrics["available_impressions"]
            total_metrics.delivered_impressions += metrics["delivered_impressions"]
            total_metrics.forecasted_impressions += metrics["forecasted_impressions"]
            
            # Aggregate key-value metrics
            for key, kv_list in metrics["key_value_metrics"].items():
                if key not in kv_summary:
                    kv_summary[key] = {}
                
                for kv in kv_list:
                    value = kv["value"]
                    if value not in kv_summary[key]:
                        kv_summary[key][value] = KeyValueMetrics(
                            key=key,
                            value=value,
                            impressions=0,
                            clicks=0,
                            revenue=0.0
                        )
                    
                    summary_metrics = kv_summary[key][value]
                    summary_metrics.impressions += kv["impressions"]
                    summary_metrics.clicks += kv["clicks"]
                    summary_metrics.revenue += kv["revenue"]
                    summary_metrics.calculate_rates()
        
        # Calculate overall rates
        total_metrics.calculate_rates()
        
        # Format key-value summary
        kv_summary_formatted = {
            key: [metrics.dict() for metrics in value.values()]
            for key, value in kv_summary.items()
        }
        
        return {
            "total_ad_units": len(data["ad_units"]),
            "aggregated_metrics": total_metrics.dict(),
            "key_value_summary": kv_summary_formatted,
            "date_range": {
                "start": self.config.start_date.isoformat(),
                "end": self.config.end_date.isoformat()
            }
        } 