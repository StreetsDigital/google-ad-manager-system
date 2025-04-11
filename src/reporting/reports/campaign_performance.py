"""
Campaign performance report generator implementation.
"""
from typing import Dict, Any, List
from datetime import datetime
from pydantic import BaseModel

from src.tools.soap_tools import SoapToolAdapter
from .base import BaseReportGenerator, ReportConfig

class CampaignMetrics(BaseModel):
    """Model for campaign performance metrics."""
    impressions: int = 0
    clicks: int = 0
    conversions: int = 0
    revenue: float = 0.0
    ctr: float = 0.0
    conversion_rate: float = 0.0
    
    def calculate_rates(self):
        """Calculate derived metrics."""
        self.ctr = (self.clicks / self.impressions * 100) if self.impressions > 0 else 0
        self.conversion_rate = (self.conversions / self.clicks * 100) if self.clicks > 0 else 0

class CampaignPerformanceReport(BaseReportGenerator):
    """Generate performance reports for campaigns."""
    
    def __init__(self, config: ReportConfig, adapter: SoapToolAdapter):
        """Initialize the report generator with configuration and SOAP adapter."""
        super().__init__(config)
        self.adapter = adapter

    async def _fetch_campaign_data(self) -> List[Dict[str, Any]]:
        """Fetch campaign data from Google Ad Manager.
        
        Returns:
            List[Dict[str, Any]]: List of campaign data from the API
        """
        try:
            # Prepare the query parameters
            params = {
                "dateRange": {
                    "startDate": self.config.start_date.strftime("%Y-%m-%dT%H:%M:%S"),
                    "endDate": self.config.end_date.strftime("%Y-%m-%dT%H:%M:%S")
                }
            }
            
            # Add any additional filters from config
            if self.config.filters:
                params.update(self.config.filters)
            
            # Get the SOAP tool from the adapter
            soap_tool = self.adapter.registry.get_tool("soap.execute")
            
            # Execute the report query
            result = await soap_tool(
                method="getReportsByStatement",
                params=params
            )
            
            if result["status"] != "success":
                raise Exception(f"Failed to fetch campaign data: {result.get('message', 'Unknown error')}")
            
            return result["data"]["results"]
        except Exception as e:
            raise Exception(f"Error fetching campaign data: {str(e)}") from e

    async def _generate_data(self) -> Dict[str, Any]:
        """Generate campaign performance data.
        
        Returns:
            Dict[str, Any]: Campaign performance metrics and analysis.
        """
        # Fetch campaign data from Ad Manager
        campaign_results = await self._fetch_campaign_data()
        
        # Process and format the campaign data
        campaigns = []
        for result in campaign_results:
            metrics = CampaignMetrics(
                impressions=result.get("impressions", 0),
                clicks=result.get("clicks", 0),
                conversions=result.get("conversions", 0),
                revenue=float(result.get("revenue", 0.0))
            )
            metrics.calculate_rates()
            
            campaigns.append({
                "id": result["id"],
                "name": result["name"],
                "metrics": metrics.dict()
            })
        
        return {"campaigns": campaigns}

    async def _generate_summary(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate summary metrics across all campaigns.
        
        Args:
            data (Dict[str, Any]): The campaign performance data.
            
        Returns:
            Dict[str, Any]: Aggregated performance metrics.
        """
        total_metrics = CampaignMetrics()
        
        # Aggregate metrics across all campaigns
        for campaign in data["campaigns"]:
            metrics = campaign["metrics"]
            total_metrics.impressions += metrics["impressions"]
            total_metrics.clicks += metrics["clicks"]
            total_metrics.conversions += metrics["conversions"]
            total_metrics.revenue += metrics["revenue"]
        
        # Calculate overall rates
        total_metrics.calculate_rates()
        
        return {
            "total_campaigns": len(data["campaigns"]),
            "aggregated_metrics": total_metrics.dict(),
            "date_range": {
                "start": self.config.start_date.isoformat(),
                "end": self.config.end_date.isoformat()
            }
        } 