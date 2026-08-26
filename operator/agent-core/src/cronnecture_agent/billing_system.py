"""Stripe billing with dry-run when no API key is configured."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

import structlog
from datetime import datetime

logger = structlog.get_logger()


class BillingSystem:
    """Stripe-backed billing; no-ops when STRIPE_SECRET_KEY is unset."""

    def __init__(self, stripe_api_key: Optional[str] = None):
        self.stripe_api_key = stripe_api_key or os.environ.get("STRIPE_SECRET_KEY", "")
        self.client_stripe_mapping: Dict[str, str] = {}
        self._stripe = None
        if self.stripe_api_key:
            import stripe

            stripe.api_key = self.stripe_api_key
            self._stripe = stripe

    async def initialize(self):
        mode = "stripe" if self._stripe else "dry-run"
        logger.info("Initializing billing system", mode=mode)

    async def shutdown(self):
        logger.info("Shutting down billing system")

    async def setup_client_billing(
        self,
        client_name: str,
        email: str,
        service_tier,
        setup_fee: float,
    ) -> Dict[str, Any]:
        client_id = client_name.lower().replace(" ", "-").replace("_", "-")
        monthly = {"website": 49.99, "webshop": 119.99, "portal": 129.99}
        tier = service_tier.value if hasattr(service_tier, "value") else str(service_tier)
        monthly_fee = monthly.get(tier, 49.99)

        if not self._stripe:
            logger.info(
                "Billing dry-run (no STRIPE_SECRET_KEY)",
                client_name=client_name,
                monthly_fee=monthly_fee,
            )
            self.client_stripe_mapping[client_id] = f"dryrun_{client_id}"
            return {
                "customer_id": f"dryrun_{client_id}",
                "subscription_id": None,
                "monthly_amount": monthly_fee,
                "setup_fee": setup_fee,
                "status": "dry-run",
            }

        stripe = self._stripe
        customer = stripe.Customer.create(
            email=email,
            name=client_name,
            metadata={"client_name": client_name, "service_tier": tier},
        )
        self.client_stripe_mapping[client_id] = customer.id
        return {
            "customer_id": customer.id,
            "subscription_id": None,
            "monthly_amount": monthly_fee,
            "setup_fee": setup_fee,
            "status": "active",
        }

    async def process_webhook(self, webhook_data: Any):
        if hasattr(webhook_data, "event_type"):
            event_type = webhook_data.event_type
            data = webhook_data.data if isinstance(webhook_data.data, dict) else {}
        else:
            event_type = webhook_data.get("type")
            data = webhook_data.get("data", {}).get("object", {})
        logger.info("Processing Stripe webhook", event_type=event_type, object_id=data.get("id"))

    async def get_client_status(self, client_id: str) -> Dict[str, Any]:
        stripe_customer_id = self.client_stripe_mapping.get(client_id)
        if not stripe_customer_id:
            return {"status": "not_found"}
        if stripe_customer_id.startswith("dryrun_"):
            return {"status": "dry-run"}
        return {"status": "active"}

    async def get_client_by_stripe_id(self, stripe_customer_id: str) -> Optional[str]:
        for client_id, customer_id in self.client_stripe_mapping.items():
            if customer_id == stripe_customer_id:
                return client_id
        return None

    async def start_payment_grace_period(self, client_id: str):
        logger.warning("Starting payment grace period", client_id=client_id)
