"""
Base report generator module providing core reporting functionality.
"""
from typing import Dict, List, Optional, Any
from datetime import datetime, UTC
from abc import ABC, abstractmethod
from pydantic import BaseModel

class ReportConfig(BaseModel):
    """Report configuration model."""
    start_date: datetime
    end_date: datetime
    filters: Optional[Dict[str, Any]] = None
    format: str = "json"
    include_metadata: bool = True

class ReportMetadata(BaseModel):
    """Report metadata model."""
    report_type: str
    generated_at: datetime
    parameters: Dict[str, Any]
    format: str = "json"

class ReportResult(BaseModel):
    """Report result model."""
    metadata: Optional[ReportMetadata] = None
    data: Dict[str, Any]
    summary: Optional[Dict[str, Any]] = None

class BaseReportGenerator(ABC):
    """Abstract base class for report generators."""
    
    def __init__(self, config: ReportConfig):
        """Initialize report generator with configuration."""
        self.config = config
        self.report_type = self.__class__.__name__

    def _build_metadata(self) -> ReportMetadata:
        """Build report metadata."""
        return ReportMetadata(
            report_type=self.report_type,
            generated_at=datetime.now(UTC),
            parameters=self.config.model_dump(),
            format=self.config.format
        )

    async def generate(self) -> ReportResult:
        """Generate report. Must be implemented by subclasses."""
        try:
            # Generate the report data
            data = await self._generate_data()
            
            # Generate summary if needed
            summary = await self._generate_summary(data) if self.config.include_metadata else None
            
            # Create metadata
            metadata = self._build_metadata() if self.config.include_metadata else None
            
            return ReportResult(
                metadata=metadata,
                data=data,
                summary=summary
            )
        except Exception as e:
            # Log the error and re-raise with more context
            raise Exception(f"Failed to generate report: {str(e)}") from e

    @abstractmethod
    async def _generate_data(self) -> Dict[str, Any]:
        """Generate report data. Must be implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement _generate_data()")

    async def _generate_summary(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate report summary. Can be overridden by subclasses."""
        return {
            "total_records": len(data.get("results", [])),
            "generated_at": datetime.now(UTC).isoformat()
        } 