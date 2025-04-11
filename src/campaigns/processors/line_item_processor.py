from typing import Dict, Any
from pydantic import BaseModel

from src.campaigns.models import LineItem
from src.campaigns.errors import ValidationError, ProcessingError

class LineItemProcessor:
    async def update_line_item(self, line_item: LineItem) -> Dict[str, Any]:
        """
        Update an existing line item.
        
        Args:
            line_item (LineItem): The line item object with updated values
            
        Returns:
            Dict[str, Any]: Response containing status and updated line item data
            
        Raises:
            ValidationError: If the line item data is invalid
            ProcessingError: If the update operation fails
        """
        # Validate creatives first
        creative_response = await self.creative_tool("getCreatives", 
            creative_ids=line_item.creative_ids
        )
        
        if creative_response["status"] != "success":
            raise ProcessingError("Failed to validate creatives")
            
        for creative in creative_response["creatives"]:
            if creative["status"] != "ACTIVE":
                raise ValidationError(f"Creative {creative['id']} is not active")
                
            if not (creative["size"]["width"] > 0 and creative["size"]["height"] > 0):
                raise ValidationError(f"Creative {creative['id']} has invalid dimensions")

        # Update the line item
        response = await self.line_item_tool(
            "updateLineItem",
            line_item=line_item.model_dump()
        )
        
        if response["status"] != "success":
            raise ProcessingError("Failed to update line item")
            
        return response 