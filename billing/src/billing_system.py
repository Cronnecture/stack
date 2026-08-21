"""
Stripe billing integration for automated payment processing.

Handles subscription management, usage tracking, invoicing,
and payment failure workflows with grace periods.
"""

import stripe
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import structlog

logger = structlog.get_logger()


class BillingSystem:
    """
    Automated billing system with Stripe integration.
    
    Manages subscriptions, tracks usage, processes payments,
    and handles payment failures with appropriate workflows.
    """
    
    def __init__(self, stripe_api_key: str):
        stripe.api_key = stripe_api_key
        self.client_stripe_mapping: Dict[str, str] = {}
        
    async def initialize(self):
        """Initialize billing system."""
        logger.info("Initializing billing system")
        
    async def shutdown(self):
        """Cleanup billing system."""
        logger.info("Shutting down billing system")
        
    async def setup_client_billing(
        self, 
        client_name: str, 
        email: str, 
        service_tier: str,
        setup_fee: float
    ) -> Dict[str, Any]:
        """
        Setup billing for new client.
        
        Creates Stripe customer, charges setup fee,
        and creates subscription for monthly billing.
        """
        logger.info("Setting up client billing",
                   client_name=client_name,
                   service_tier=service_tier)
        
        try:
            # Create Stripe customer
            customer = stripe.Customer.create(
                email=email,
                name=client_name,
                metadata={
                    "client_name": client_name,
                    "service_tier": service_tier,
                    "setup_date": datetime.now().isoformat()
                }
            )
            
            # Store mapping
            client_id = client_name.lower().replace(" ", "-").replace("_", "-")
            self.client_stripe_mapping[client_id] = customer.id
            
            # Charge setup fee immediately
            if setup_fee > 0:
                setup_payment = stripe.PaymentIntent.create(
                    amount=int(setup_fee * 100),  # Convert to cents
                    currency="eur",
                    customer=customer.id,
                    description=f"Setup fee for {client_name} ({service_tier})",
                    metadata={
                        "client_name": client_name,
                        "service_tier": service_tier,
                        "fee_type": "setup"
                    },
                    automatic_payment_methods={
                        "enabled": True
                    }
                )
                
                logger.info("Setup fee payment created",
                           client_name=client_name,
                           amount=setup_fee,
                           payment_intent=setup_payment.id)
            
            # Create monthly subscription
            monthly_fees = {
                "website": 49.99,
                "webshop": 119.99,
                "portal": 129.99
            }
            
            monthly_fee = monthly_fees.get(service_tier, 49.99)
            
            # Create product if it doesn't exist
            try:
                product = stripe.Product.retrieve(f"cronnecture-{service_tier}")
            except stripe.error.InvalidRequestError:
                product = stripe.Product.create(
                    id=f"cronnecture-{service_tier}",
                    name=f"Cronnecture {service_tier.title()} Service",
                    description=f"Monthly {service_tier} hosting and management"
                )
            
            # Create price if it doesn't exist
            try:
                price = stripe.Price.retrieve(f"price-{service_tier}-monthly")
            except stripe.error.InvalidRequestError:
                price = stripe.Price.create(
                    id=f"price-{service_tier}-monthly",
                    product=product.id,
                    unit_amount=int(monthly_fee * 100),
                    currency="eur",
                    recurring={"interval": "month"}
                )
            
            # Create subscription
            subscription = stripe.Subscription.create(
                customer=customer.id,
                items=[{"price": price.id}],
                metadata={
                    "client_name": client_name,
                    "service_tier": service_tier
                }
            )
            
            logger.info("Billing setup completed",
                       client_name=client_name,
                       customer_id=customer.id,
                       subscription_id=subscription.id)
            
            return {
                "customer_id": customer.id,
                "subscription_id": subscription.id,
                "monthly_amount": monthly_fee,
                "setup_fee": setup_fee,
                "status": "active"
            }
            
        except Exception as e:
            logger.error("Billing setup failed",
                        client_name=client_name,
                        error=str(e))
            raise
    
    async def process_webhook(self, webhook_data: Dict[str, Any]):
        """
        Process Stripe webhook events.
        
        Handles payment successes, failures, subscription changes,
        and other billing-related events.
        """
        event_type = webhook_data.get("type")
        data = webhook_data.get("data", {}).get("object", {})
        
        logger.info("Processing Stripe webhook",
                   event_type=event_type,
                   object_id=data.get("id"))
        
        if event_type == "invoice.payment_succeeded":
            await self._handle_payment_success(data)
        elif event_type == "invoice.payment_failed":
            await self._handle_payment_failure(data)
        elif event_type == "customer.subscription.updated":
            await self._handle_subscription_update(data)
        elif event_type == "customer.subscription.deleted":
            await self._handle_subscription_cancellation(data)
        else:
            logger.info("Unhandled webhook event", event_type=event_type)
    
    async def get_client_status(self, client_id: str) -> Dict[str, Any]:
        """Get billing status for client."""
        stripe_customer_id = self.client_stripe_mapping.get(client_id)
        
        if not stripe_customer_id:
            return {"status": "not_found"}
        
        try:
            # Get customer and subscription info
            customer = stripe.Customer.retrieve(stripe_customer_id)
            subscriptions = stripe.Subscription.list(customer=stripe_customer_id)
            
            if subscriptions.data:
                subscription = subscriptions.data[0]
                return {
                    "status": subscription.status,
                    "current_period_end": datetime.fromtimestamp(
                        subscription.current_period_end
                    ).isoformat(),
                    "amount_due": subscription.latest_invoice,
                    "payment_method": customer.default_source
                }
            else:
                return {"status": "no_subscription"}
                
        except Exception as e:
            logger.error("Failed to get billing status",
                        client_id=client_id,
                        error=str(e))
            return {"status": "error", "error": str(e)}
    
    async def get_client_by_stripe_id(self, stripe_customer_id: str) -> Optional[str]:
        """Get client ID by Stripe customer ID."""
        for client_id, customer_id in self.client_stripe_mapping.items():
            if customer_id == stripe_customer_id:
                return client_id
        return None
    
    async def start_payment_grace_period(self, client_id: str):
        """Start payment grace period workflow."""
        logger.warning("Starting payment grace period",
                      client_id=client_id)
        
        # In a real implementation, this would:
        # 1. Schedule retry attempts
        # 2. Send notification emails
        # 3. Set service restrictions after certain periods
        # 4. Schedule service suspension
        
        # For now, just log the action
        logger.info("Grace period workflow started", client_id=client_id)
    
    async def _handle_payment_success(self, invoice_data: Dict[str, Any]):
        """Handle successful payment."""
        customer_id = invoice_data.get("customer")
        amount_paid = invoice_data.get("amount_paid", 0) / 100  # Convert from cents
        
        logger.info("Payment succeeded",
                   customer_id=customer_id,
                   amount=amount_paid)
        
        # Update client status to active if suspended
        client_id = await self.get_client_by_stripe_id(customer_id)
        if client_id:
            # Here you would update client status in your database
            # and potentially re-enable services if they were suspended
            logger.info("Payment processed for client", client_id=client_id)
    
    async def _handle_payment_failure(self, invoice_data: Dict[str, Any]):
        """Handle failed payment."""
        customer_id = invoice_data.get("customer")
        amount_due = invoice_data.get("amount_due", 0) / 100
        attempt_count = invoice_data.get("attempt_count", 0)
        
        logger.warning("Payment failed",
                      customer_id=customer_id,
                      amount_due=amount_due,
                      attempt_count=attempt_count)
        
        client_id = await self.get_client_by_stripe_id(customer_id)
        if client_id:
            await self.start_payment_grace_period(client_id)
    
    async def _handle_subscription_update(self, subscription_data: Dict[str, Any]):
        """Handle subscription changes."""
        customer_id = subscription_data.get("customer")
        status = subscription_data.get("status")
        
        logger.info("Subscription updated",
                   customer_id=customer_id,
                   status=status)
    
    async def _handle_subscription_cancellation(self, subscription_data: Dict[str, Any]):
        """Handle subscription cancellation."""
        customer_id = subscription_data.get("customer")
        
        logger.info("Subscription cancelled",
                   customer_id=customer_id)
        
        client_id = await self.get_client_by_stripe_id(customer_id)
        if client_id:
            # Schedule service suspension with grace period
            logger.info("Scheduling service suspension", client_id=client_id)