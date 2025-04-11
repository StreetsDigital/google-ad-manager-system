"""
Campaign management service.

This module provides the high-level service for managing campaigns, including
orders, line items, and creatives in the Google Ad Manager system.
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

from src.campaigns.models import Order, LineItem, Creative
from src.campaigns.batch.processors import CampaignProcessor
from src.campaigns.line_items.processor import LineItemProcessor
from src.campaigns.batch.validators import BatchValidator
from src.campaigns.line_items.connection_pool import ConnectionPool

logger = logging.getLogger(__name__)

class CampaignService:
    """Service for managing advertising campaigns."""

    def __init__(self, connection_pool: ConnectionPool):
        """Initialize with connection pool."""
        self.connection_pool = connection_pool
        self.campaign_processor = CampaignProcessor()
        self.line_item_processor = LineItemProcessor()
        self.validator = BatchValidator()

    async def create_campaign(
        self,
        order: Order,
        line_items: List[LineItem],
        creatives: Optional[List[Creative]] = None
    ) -> Dict[str, Any]:
        """
        Create a complete campaign with order, line items, and creatives.

        Args:
            order: Campaign order
            line_items: Line items for the campaign
            creatives: Optional creatives to create

        Returns:
            Dict containing creation status and results
        """
        # Prepare batch operations
        try:
            operations = self.campaign_processor.prepare_campaign_create(
                order=order,
                line_items=line_items,
                creatives=creatives
            )
        except Exception as e:
            logger.error(f"Error preparing campaign operations: {e}")
            return {
                "status": "error",
                "message": f"Failed to prepare campaign: {str(e)}"
            }

        # Execute batch operations
        async with self.connection_pool.get_connection() as conn:
            try:
                result = await conn.execute_batch(operations)
                return {
                    "status": "success",
                    "data": result
                }
            except Exception as e:
                logger.error(f"Error executing campaign operations: {e}")
                return {
                    "status": "error",
                    "message": f"Failed to create campaign: {str(e)}"
                }

    async def update_campaign(
        self,
        order_updates: Optional[Dict[str, Any]] = None,
        line_item_updates: Optional[Dict[str, Dict[str, Any]]] = None,
        creative_updates: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Update campaign components.

        Args:
            order_updates: Updates for the order
            line_item_updates: Updates for line items, keyed by ID
            creative_updates: Updates for creatives, keyed by ID

        Returns:
            Dict containing update status and results
        """
        # Prepare batch operations
        try:
            operations = self.campaign_processor.prepare_campaign_update(
                order_updates=order_updates,
                line_item_updates=line_item_updates,
                creative_updates=creative_updates
            )
        except Exception as e:
            logger.error(f"Error preparing update operations: {e}")
            return {
                "status": "error",
                "message": f"Failed to prepare updates: {str(e)}"
            }

        # Execute batch operations
        async with self.connection_pool.get_connection() as conn:
            try:
                result = await conn.execute_batch(operations)
                return {
                    "status": "success",
                    "data": result
                }
            except Exception as e:
                logger.error(f"Error executing update operations: {e}")
                return {
                    "status": "error",
                    "message": f"Failed to update campaign: {str(e)}"
                }

    async def get_campaign(self, order_id: str) -> Dict[str, Any]:
        """
        Get a complete campaign by order ID.

        Args:
            order_id: ID of the campaign order

        Returns:
            Dict containing campaign details
        """
        async with self.connection_pool.get_connection() as conn:
            try:
                # Get order details
                order = await conn.get_order(order_id)
                if not order:
                    return {
                        "status": "error",
                        "message": f"Order {order_id} not found"
                    }

                # Get line items
                line_items = await self.line_item_processor.get_line_items_by_order(order_id)
                if line_items.get("status") != "success":
                    return {
                        "status": "error",
                        "message": "Failed to fetch line items"
                    }

                # Get creatives for each line item
                creative_ids = set()
                for line_item in line_items["data"]["results"]:
                    creative_ids.update(line_item.get("creative_ids", []))

                creatives = []
                if creative_ids:
                    creative_result = await conn.get_creatives(list(creative_ids))
                    if creative_result.get("status") == "success":
                        creatives = creative_result["creatives"]

                return {
                    "status": "success",
                    "data": {
                        "order": order,
                        "line_items": line_items["data"]["results"],
                        "creatives": creatives
                    }
                }

            except Exception as e:
                logger.error(f"Error fetching campaign: {e}")
                return {
                    "status": "error",
                    "message": f"Failed to fetch campaign: {str(e)}"
                }

    async def pause_campaign(self, order_id: str) -> Dict[str, Any]:
        """
        Pause a campaign by pausing its order and line items.

        Args:
            order_id: ID of the campaign order

        Returns:
            Dict containing pause status and results
        """
        try:
            # Get current campaign state
            campaign = await self.get_campaign(order_id)
            if campaign["status"] != "success":
                return campaign

            # Prepare updates
            order_updates = {
                "id": order_id,
                "status": "PAUSED"
            }

            line_item_updates = {
                item["id"]: {"status": "PAUSED"}
                for item in campaign["data"]["line_items"]
            }

            # Update campaign
            return await self.update_campaign(
                order_updates=order_updates,
                line_item_updates=line_item_updates
            )

        except Exception as e:
            logger.error(f"Error pausing campaign: {e}")
            return {
                "status": "error",
                "message": f"Failed to pause campaign: {str(e)}"
            }

    async def resume_campaign(self, order_id: str) -> Dict[str, Any]:
        """
        Resume a paused campaign.

        Args:
            order_id: ID of the campaign order

        Returns:
            Dict containing resume status and results
        """
        try:
            # Get current campaign state
            campaign = await self.get_campaign(order_id)
            if campaign["status"] != "success":
                return campaign

            # Prepare updates
            order_updates = {
                "id": order_id,
                "status": "ACTIVE"
            }

            line_item_updates = {
                item["id"]: {"status": "ACTIVE"}
                for item in campaign["data"]["line_items"]
                if item["status"] == "PAUSED"
            }

            # Update campaign
            return await self.update_campaign(
                order_updates=order_updates,
                line_item_updates=line_item_updates
            )

        except Exception as e:
            logger.error(f"Error resuming campaign: {e}")
            return {
                "status": "error",
                "message": f"Failed to resume campaign: {str(e)}"
            }

    async def archive_campaign(self, order_id: str) -> Dict[str, Any]:
        """
        Archive a campaign by archiving its order and line items.

        Args:
            order_id: ID of the campaign order

        Returns:
            Dict containing archive status and results
        """
        try:
            # Get current campaign state
            campaign = await self.get_campaign(order_id)
            if campaign["status"] != "success":
                return campaign

            # Prepare updates
            order_updates = {
                "id": order_id,
                "status": "ARCHIVED"
            }

            line_item_updates = {
                item["id"]: {"status": "ARCHIVED"}
                for item in campaign["data"]["line_items"]
            }

            # Update campaign
            return await self.update_campaign(
                order_updates=order_updates,
                line_item_updates=line_item_updates
            )

        except Exception as e:
            logger.error(f"Error archiving campaign: {e}")
            return {
                "status": "error",
                "message": f"Failed to archive campaign: {str(e)}"
            } 