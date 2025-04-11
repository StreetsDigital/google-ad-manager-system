from typing import List, Dict, Any, Optional
from datetime import datetime
import pandas as pd

async def aggregate_performance_data(
    data: List[Dict[str, Any]],
    group_by: List[str],
    metrics: List[str],
    filters: Optional[Dict[str, Any]] = None,
    time_window: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Aggregate performance data based on specified metrics and dimensions.
    
    Args:
        data: List of performance data records
        group_by: List of dimensions to group by
        metrics: List of metrics to include
        filters: Optional filters to apply
        time_window: Optional time window for aggregation (hourly, daily, weekly, monthly)
    
    Returns:
        List[Dict[str, Any]]: Aggregated performance data
    """
    # Convert to DataFrame for easier manipulation
    df = pd.DataFrame(data)
    
    # Apply filters if provided
    if filters:
        for key, value in filters.items():
            if isinstance(value, dict):
                # Handle range filters
                if "min" in value:
                    df = df[df[key] >= value["min"]]
                if "max" in value:
                    df = df[df[key] <= value["max"]]
            else:
                # Handle exact match filters
                df = df[df[key] == value]
    
    # Calculate derived metrics before grouping
    if "ctr" in metrics:
        df["ctr"] = (df["clicks"] / df["impressions"]) * 100
    
    if "viewability_rate" in metrics:
        df["viewability_rate"] = (df["viewable_impressions"] / df["impressions"]) * 100
    
    # Handle time-based grouping
    if time_window:
        if "date" not in group_by:
            group_by.append("date")
        if time_window == "hourly":
            df["date"] = pd.to_datetime(df["date"]).dt.floor("H")
        elif time_window == "daily":
            df["date"] = pd.to_datetime(df["date"]).dt.floor("D")
        elif time_window == "weekly":
            df["date"] = pd.to_datetime(df["date"]).dt.floor("W")
        elif time_window == "monthly":
            df["date"] = pd.to_datetime(df["date"]).dt.floor("M")
    
    # Define aggregation functions for each metric
    agg_functions = {
        "impressions": "sum",
        "viewable_impressions": "sum",
        "clicks": "sum",
        "revenue": "sum",
        "ctr": "mean",
        "viewability_rate": "mean"
    }
    
    # Select only requested metrics
    metrics_to_agg = {
        metric: agg_functions[metric]
        for metric in metrics
        if metric in agg_functions
    }
    
    # Perform grouping and aggregation
    grouped_df = df.groupby(group_by, as_index=False).agg(metrics_to_agg)
    
    # Round percentage metrics to 2 decimal places
    if "ctr" in metrics:
        grouped_df["ctr"] = grouped_df["ctr"].round(2)
    if "viewability_rate" in metrics:
        grouped_df["viewability_rate"] = grouped_df["viewability_rate"].round(2)
    
    # Convert to list of dictionaries
    return grouped_df.to_dict("records") 