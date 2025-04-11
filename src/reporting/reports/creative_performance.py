"""
Creative performance report generator implementation.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime
from pydantic import BaseModel
from dataclasses import dataclass

from src.tools.soap_tools import SoapToolAdapter
from .base import BaseReportGenerator, ReportConfig

@dataclass
class CreativeMetrics:
    """Metrics for a creative."""
    impressions: int = 0
    clicks: int = 0
    interactions: int = 0
    video_completions: Optional[int] = None
    average_display_time: float = 0.0
    ctr: float = 0.0
    interaction_rate: float = 0.0
    completion_rate: Optional[float] = None

    def calculate_rates(self) -> None:
        """Calculate derived metrics."""
        if self.impressions > 0:
            self.ctr = (self.clicks / self.impressions) * 100
            self.interaction_rate = (self.interactions / self.impressions) * 100
            if self.video_completions is not None:
                self.completion_rate = (self.video_completions / self.impressions) * 100

class CreativePerformanceReport(BaseReportGenerator):
    """Generate performance reports for creatives."""
    
    def __init__(self, config: ReportConfig, adapter: SoapToolAdapter):
        """Initialize the report generator with configuration and SOAP adapter."""
        super().__init__(config)
        self.adapter = adapter
        self.report_type = "creative_performance"

    async def _fetch_creative_data(self) -> List[Dict[str, Any]]:
        """Fetch creative performance data from Google Ad Manager.
        
        Returns:
            List[Dict[str, Any]]: List of creative performance data from the API
        """
        try:
            # Prepare the query parameters
            params = {
                "dateRange": {
                    "startDate": self.config.start_date.strftime("%Y-%m-%d"),
                    "endDate": self.config.end_date.strftime("%Y-%m-%d")
                },
                "dimensions": ["CREATIVE_ID", "CREATIVE_NAME", "CREATIVE_TYPE"],
                "metrics": [
                    "TOTAL_IMPRESSIONS",
                    "TOTAL_CLICKS",
                    "TOTAL_INTERACTIONS",
                    "TOTAL_VIDEO_COMPLETIONS",
                    "AVERAGE_DISPLAY_TIME"
                ]
            }
            
            # Add any additional filters from config
            if self.config.filters:
                params.update(self.config.filters)
            
            # Get the SOAP tool from the adapter
            soap_tool = self.adapter.registry.get_tool("soap.execute")
            
            # Execute the report query
            result = await soap_tool(
                service="ReportService",
                method="getCreativeReport",
                params=params
            )
            
            if result["status"] != "success":
                raise Exception(f"Failed to fetch creative data: {result.get('message', 'Unknown error')}")
            
            return result["data"]["results"]
        except Exception as e:
            raise Exception(f"Error fetching creative data: {str(e)}") from e

    async def _generate_data(self) -> Dict[str, Any]:
        """Generate creative performance data.
        
        Returns:
            Dict[str, Any]: Creative performance metrics and analysis.
        """
        # Fetch creative data from Ad Manager
        creative_results = await self._fetch_creative_data()
        
        # Process and format the creative data
        creatives = []
        for result in creative_results:
            metrics = CreativeMetrics(
                impressions=result.get("totalImpressions", 0),
                clicks=result.get("totalClicks", 0),
                interactions=result.get("totalInteractions", 0),
                video_completions=result.get("totalVideoCompletions"),
                average_display_time=result.get("averageDisplayTime", 0)
            )
            metrics.calculate_rates()
            
            creative = {
                "id": result["creativeId"],
                "name": result["creativeName"],
                "type": result["creativeType"],
                "metrics": {
                    "impressions": metrics.impressions,
                    "clicks": metrics.clicks,
                    "interactions": metrics.interactions,
                    "ctr": metrics.ctr,
                    "interaction_rate": metrics.interaction_rate,
                    "average_display_time": metrics.average_display_time
                }
            }
            
            if metrics.completion_rate is not None:
                creative["metrics"]["completion_rate"] = metrics.completion_rate
            
            creatives.append(creative)
        
        return {"creatives": creatives}

    async def _generate_summary(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate summary metrics across all creatives.
        
        Args:
            data (Dict[str, Any]): The creative performance data.
            
        Returns:
            Dict[str, Any]: Aggregated performance metrics.
        """
        total_impressions = 0
        total_clicks = 0
        total_interactions = 0
        total_display_time = 0.0
        metrics_by_type: Dict[str, Dict[str, Any]] = {}
        
        # Aggregate metrics across all creatives
        for creative in data["creatives"]:
            metrics = creative["metrics"]
            total_impressions += metrics["impressions"]
            total_clicks += metrics["clicks"]
            total_interactions += metrics["interactions"]
            total_display_time += metrics["average_display_time"]
            
            # Track metrics by creative type
            creative_type = creative["type"]
            if creative_type not in metrics_by_type:
                metrics_by_type[creative_type] = {
                    "impressions": 0,
                    "clicks": 0,
                    "interactions": 0,
                    "video_completions": 0,
                    "total_display_time": 0.0
                }
            
            type_metrics = metrics_by_type[creative_type]
            type_metrics["impressions"] += metrics["impressions"]
            type_metrics["clicks"] += metrics["clicks"]
            type_metrics["interactions"] += metrics["interactions"]
            type_metrics["total_display_time"] += metrics["average_display_time"]
            
            if "completion_rate" in metrics:
                type_metrics["video_completions"] = metrics["completion_rate"]
        
        # Calculate overall rates
        avg_display_time = total_display_time / len(data["creatives"]) if data["creatives"] else 0
        aggregated_metrics = {
            "impressions": total_impressions,
            "clicks": total_clicks,
            "interactions": total_interactions,
            "ctr": (total_clicks / total_impressions * 100) if total_impressions > 0 else 0,
            "interaction_rate": (total_interactions / total_impressions * 100) if total_impressions > 0 else 0,
            "average_display_time": avg_display_time
        }
        
        # Calculate rates for each creative type
        for type_metrics in metrics_by_type.values():
            impressions = type_metrics["impressions"]
            if impressions > 0:
                type_metrics["ctr"] = (type_metrics["clicks"] / impressions) * 100
                type_metrics["interaction_rate"] = (type_metrics["interactions"] / impressions) * 100
                type_metrics["average_display_time"] = type_metrics["total_display_time"] / len(data["creatives"])
            del type_metrics["total_display_time"]
        
        return {
            "total_creatives": len(data["creatives"]),
            "aggregated_metrics": aggregated_metrics,
            "metrics_by_type": metrics_by_type,
            "date_range": {
                "start": self.config.start_date.isoformat(),
                "end": self.config.end_date.isoformat()
            }
        } 