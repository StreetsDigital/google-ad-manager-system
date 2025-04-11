"""
Inventory management services.

This module provides services for managing ad units, placements, and targeting rules
in the Google Ad Manager system.
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

from src.tools.soap_tools import SoapToolAdapter
from src.campaigns.line_items.connection_pool import ConnectionPool
from .models import (
    AdUnit, AdUnitStatus, AdUnitType,
    Placement, PlacementStatus,
    TargetingRule, TargetingType, TargetingOperator, TargetingCriteria
)

logger = logging.getLogger(__name__)

class AdUnitService:
    """Service for managing ad units."""

    def __init__(self, connection_pool: ConnectionPool):
        """Initialize with connection pool."""
        self.connection_pool = connection_pool

    async def create_ad_unit(self, ad_unit: AdUnit) -> AdUnit:
        """
        Create a new ad unit.

        Args:
            ad_unit: Ad unit configuration

        Returns:
            AdUnit: Created ad unit with ID
        """
        async with self.connection_pool.get_connection() as conn:
            result = await conn.create_ad_unit({
                "name": ad_unit.name,
                "code": ad_unit.code,
                "parentId": ad_unit.parent_id,
                "type": ad_unit.type.value,
                "size": ad_unit.size,
                "status": ad_unit.status.value,
                "targeting": ad_unit.targeting
            })
            ad_unit.id = result["id"]
            return ad_unit

    async def get_ad_unit(self, ad_unit_id: str) -> Optional[AdUnit]:
        """
        Get an ad unit by ID.

        Args:
            ad_unit_id: ID of the ad unit

        Returns:
            Optional[AdUnit]: Ad unit if found, None otherwise
        """
        async with self.connection_pool.get_connection() as conn:
            result = await conn.get_ad_unit(ad_unit_id)
            if not result:
                return None
            return AdUnit(
                id=result["id"],
                name=result["name"],
                code=result["code"],
                parent_id=result.get("parentId"),
                type=AdUnitType(result["type"]),
                size=result["size"],
                status=AdUnitStatus(result["status"]),
                targeting=result.get("targeting", {}),
                created_at=datetime.fromisoformat(result["createdAt"]),
                updated_at=datetime.fromisoformat(result["updatedAt"])
            )

    async def update_ad_unit(self, ad_unit: AdUnit) -> AdUnit:
        """
        Update an existing ad unit.

        Args:
            ad_unit: Ad unit with updated configuration

        Returns:
            AdUnit: Updated ad unit
        """
        if not ad_unit.id:
            raise ValueError("Ad unit ID is required for update")

        async with self.connection_pool.get_connection() as conn:
            result = await conn.update_ad_unit({
                "id": ad_unit.id,
                "name": ad_unit.name,
                "code": ad_unit.code,
                "parentId": ad_unit.parent_id,
                "type": ad_unit.type.value,
                "size": ad_unit.size,
                "status": ad_unit.status.value,
                "targeting": ad_unit.targeting
            })
            ad_unit.updated_at = datetime.fromisoformat(result["updatedAt"])
            return ad_unit

    async def delete_ad_unit(self, ad_unit_id: str) -> bool:
        """
        Delete an ad unit.

        Args:
            ad_unit_id: ID of the ad unit to delete

        Returns:
            bool: True if deleted, False otherwise
        """
        async with self.connection_pool.get_connection() as conn:
            result = await conn.delete_ad_unit(ad_unit_id)
            return result.get("success", False)

class PlacementService:
    """Service for managing placements."""

    def __init__(self, connection_pool: ConnectionPool):
        """Initialize with connection pool."""
        self.connection_pool = connection_pool

    async def create_placement(self, placement: Placement) -> Placement:
        """
        Create a new placement.

        Args:
            placement: Placement configuration

        Returns:
            Placement: Created placement with ID
        """
        async with self.connection_pool.get_connection() as conn:
            result = await conn.create_placement({
                "name": placement.name,
                "description": placement.description,
                "adUnitIds": placement.ad_unit_ids,
                "targeting": placement.targeting,
                "status": placement.status.value
            })
            placement.id = result["id"]
            return placement

    async def get_placement(self, placement_id: str) -> Optional[Placement]:
        """
        Get a placement by ID.

        Args:
            placement_id: ID of the placement

        Returns:
            Optional[Placement]: Placement if found, None otherwise
        """
        async with self.connection_pool.get_connection() as conn:
            result = await conn.get_placement(placement_id)
            if not result:
                return None
            return Placement(
                id=result["id"],
                name=result["name"],
                description=result.get("description"),
                ad_unit_ids=result["adUnitIds"],
                targeting=result.get("targeting", {}),
                status=PlacementStatus(result["status"]),
                created_at=datetime.fromisoformat(result["createdAt"]),
                updated_at=datetime.fromisoformat(result["updatedAt"])
            )

    async def update_placement(self, placement: Placement) -> Placement:
        """
        Update an existing placement.

        Args:
            placement: Placement with updated configuration

        Returns:
            Placement: Updated placement
        """
        if not placement.id:
            raise ValueError("Placement ID is required for update")

        async with self.connection_pool.get_connection() as conn:
            result = await conn.update_placement({
                "id": placement.id,
                "name": placement.name,
                "description": placement.description,
                "adUnitIds": placement.ad_unit_ids,
                "targeting": placement.targeting,
                "status": placement.status.value
            })
            placement.updated_at = datetime.fromisoformat(result["updatedAt"])
            return placement

    async def delete_placement(self, placement_id: str) -> bool:
        """
        Delete a placement.

        Args:
            placement_id: ID of the placement to delete

        Returns:
            bool: True if deleted, False otherwise
        """
        async with self.connection_pool.get_connection() as conn:
            result = await conn.delete_placement(placement_id)
            return result.get("success", False)

class TargetingService:
    """Service for managing targeting rules."""

    def __init__(self, connection_pool: ConnectionPool):
        """Initialize with connection pool."""
        self.connection_pool = connection_pool

    async def create_targeting_rule(self, rule: TargetingRule) -> TargetingRule:
        """
        Create a new targeting rule.

        Args:
            rule: Targeting rule configuration

        Returns:
            TargetingRule: Created targeting rule with ID
        """
        async with self.connection_pool.get_connection() as conn:
            result = await conn.create_targeting_rule({
                "name": rule.name,
                "description": rule.description,
                "criteria": [
                    {
                        "type": c.type.value,
                        "operator": c.operator.value,
                        "values": c.values
                    }
                    for c in rule.criteria
                ]
            })
            rule.id = result["id"]
            return rule

    async def get_targeting_rule(self, rule_id: str) -> Optional[TargetingRule]:
        """
        Get a targeting rule by ID.

        Args:
            rule_id: ID of the targeting rule

        Returns:
            Optional[TargetingRule]: Targeting rule if found, None otherwise
        """
        async with self.connection_pool.get_connection() as conn:
            result = await conn.get_targeting_rule(rule_id)
            if not result:
                return None
            return TargetingRule(
                id=result["id"],
                name=result["name"],
                description=result.get("description"),
                criteria=[
                    TargetingCriteria(
                        type=TargetingType(c["type"]),
                        operator=TargetingOperator(c["operator"]),
                        values=c["values"]
                    )
                    for c in result["criteria"]
                ],
                created_at=datetime.fromisoformat(result["createdAt"]),
                updated_at=datetime.fromisoformat(result["updatedAt"])
            )

    async def update_targeting_rule(self, rule: TargetingRule) -> TargetingRule:
        """
        Update an existing targeting rule.

        Args:
            rule: Targeting rule with updated configuration

        Returns:
            TargetingRule: Updated targeting rule
        """
        if not rule.id:
            raise ValueError("Targeting rule ID is required for update")

        async with self.connection_pool.get_connection() as conn:
            result = await conn.update_targeting_rule({
                "id": rule.id,
                "name": rule.name,
                "description": rule.description,
                "criteria": [
                    {
                        "type": c.type.value,
                        "operator": c.operator.value,
                        "values": c.values
                    }
                    for c in rule.criteria
                ]
            })
            rule.updated_at = datetime.fromisoformat(result["updatedAt"])
            return rule

    async def delete_targeting_rule(self, rule_id: str) -> bool:
        """
        Delete a targeting rule.

        Args:
            rule_id: ID of the targeting rule to delete

        Returns:
            bool: True if deleted, False otherwise
        """
        async with self.connection_pool.get_connection() as conn:
            result = await conn.delete_targeting_rule(rule_id)
            return result.get("success", False) 