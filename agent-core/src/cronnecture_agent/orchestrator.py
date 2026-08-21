"""
Core orchestration engine that coordinates all business workflows.

Manages client onboarding, infrastructure provisioning, billing,
monitoring alerts, and human approval processes.
"""

import asyncio
import uuid
from typing import Dict, Optional, Any
import structlog
from datetime import datetime, timedelta

from .models import (
    OnboardingRequest, 
    ApprovalResponse, 
    ClientStatus,
    StripeWebhook,
    AlertWebhook,
    DeploymentPlan,
    ServiceTier
)
from .approval_gateway import ApprovalGateway
from .infrastructure_manager import InfrastructureManager
from .billing_system import BillingSystem
from .monitoring import MonitoringSystem

logger = structlog.get_logger()


class AgentOrchestrator:
    """
    Central orchestration engine for all Cronnecture business processes.
    
    Coordinates between subsystems and manages workflow execution
    with appropriate human approval gates.
    """
    
    def __init__(self):
        self.approval_gateway = ApprovalGateway()
        self.infrastructure_manager = InfrastructureManager()
        self.billing_system = BillingSystem()
        self.monitoring = MonitoringSystem()
        
        # In-memory storage for demo (replace with Redis/DB in production)
        self.active_workflows: Dict[str, Dict[str, Any]] = {}
        self.client_registry: Dict[str, Dict[str, Any]] = {}
        
    async def initialize(self):
        """Initialize all subsystems."""
        logger.info("Initializing Agent Orchestrator")
        
        await self.approval_gateway.initialize()
        await self.infrastructure_manager.initialize()
        await self.billing_system.initialize()
        await self.monitoring.initialize()
        
        logger.info("Agent Orchestrator initialized successfully")
        
    async def shutdown(self):
        """Cleanup all subsystems."""
        logger.info("Shutting down Agent Orchestrator")
        
        await self.monitoring.shutdown()
        await self.billing_system.shutdown()
        await self.infrastructure_manager.shutdown()
        await self.approval_gateway.shutdown()
        
    async def process_onboarding(self, request: OnboardingRequest) -> Dict[str, Any]:
        """
        Process client onboarding request with human approval.
        
        Steps:
        1. Validate request and generate deployment plan
        2. Request human approval via WhatsApp
        3. If approved, execute deployment
        4. Setup billing and monitoring
        """
        workflow_id = f"onboard_{datetime.now().strftime('%Y%m%d%H%M%S')}_{request.client_name.lower().replace(' ', '_')}"
        
        logger.info("Starting onboarding workflow", 
                   workflow_id=workflow_id, 
                   client=request.client_name)
        
        try:
            # Generate deployment plan
            plan = await self._generate_deployment_plan(request)
            
            # Store workflow state
            dump = request.model_dump() if hasattr(request, "model_dump") else request.dict()
            self.active_workflows[workflow_id] = {
                "type": "onboarding",
                "request": dump,
                "plan": plan.model_dump() if hasattr(plan, "model_dump") else plan.dict(),
                "status": "awaiting_approval",
                "created_at": datetime.now()
            }
            
            # Request human approval
            if plan.requires_approval:
                approval_id = await self.approval_gateway.request_approval(
                    plan=plan,
                    contact_phone=request.phone,
                    workflow_id=workflow_id
                )
                self.active_workflows[workflow_id]["approval_id"] = approval_id
                
                logger.info("Approval requested", 
                           workflow_id=workflow_id,
                           approval_id=approval_id)
                
                return {"status": "awaiting_approval", "workflow_id": workflow_id, "approval_id": approval_id}
            else:
                result = await self._execute_deployment(workflow_id, approved=True)
                result["workflow_id"] = workflow_id
                return result
                
        except Exception as e:
            logger.error("Onboarding workflow failed",
                        workflow_id=workflow_id,
                        error=str(e))
            
            # Update workflow status
            if workflow_id in self.active_workflows:
                self.active_workflows[workflow_id]["status"] = "failed"
                self.active_workflows[workflow_id]["error"] = str(e)
            
            raise
    
    async def process_approval(self, approval_id: str, response: ApprovalResponse) -> Dict[str, Any]:
        """
        Process human approval response and continue workflow.
        """
        logger.info("Processing approval response",
                   approval_id=approval_id,
                   approved=response.approved)
        
        # Find associated workflow
        workflow_id = None
        for wf_id, workflow in self.active_workflows.items():
            if workflow.get("approval_id") == approval_id:
                workflow_id = wf_id
                break
                
        if not workflow_id:
            raise ValueError(f"No workflow found for approval {approval_id}")
        
        workflow = self.active_workflows[workflow_id]
        
        if response.approved:
            # Execute approved deployment
            result = await self._execute_deployment(workflow_id, approved=True, comments=response.comments)
            
            # Notify approval gateway of completion
            await self.approval_gateway.notify_completion(
                approval_id=approval_id,
                success=True,
                result=result
            )
            
            return result
        else:
            # Handle rejection
            workflow["status"] = "rejected"
            workflow["rejection_reason"] = response.comments
            
            # Notify client of rejection
            await self.approval_gateway.notify_rejection(
                approval_id=approval_id,
                reason=response.comments,
                phone=workflow["request"]["phone"]
            )
            
            return {"status": "rejected", "reason": response.comments}
    
    async def get_client_status(self, client_id: str) -> ClientStatus:
        """Get comprehensive client service status."""
        client_data = self.client_registry.get(client_id)
        infra_status = await self.infrastructure_manager.get_client_status(client_id)
        billing_status = await self.billing_system.get_client_status(client_id)
        monitoring_stats = await self.monitoring.get_client_metrics(client_id)

        name = (client_data or {}).get("name", client_id)
        domain = (client_data or {}).get("domain", "")
        tier_raw = (client_data or {}).get("service_tier", "website")
        try:
            tier = ServiceTier(tier_raw)
        except Exception:
            tier = ServiceTier.WEBSITE

        last_dep = infra_status.get("last_deployment") or datetime.now().isoformat()
        ssl = infra_status.get("ssl_expiry") or datetime.now().isoformat()

        return ClientStatus(
            client_id=client_id,
            client_name=name,
            service_tier=tier,
            domain=domain,
            status=infra_status.get("overall_status", "unknown"),
            uptime_percentage=monitoring_stats.get("uptime_30d", 0.0),
            last_deployment=datetime.fromisoformat(last_dep.replace("Z", "+00:00")) if isinstance(last_dep, str) else last_dep,
            ssl_expiry=datetime.fromisoformat(ssl.replace("Z", "+00:00")) if isinstance(ssl, str) else ssl,
            resource_usage=monitoring_stats.get("resource_usage", {}),
            billing_status=billing_status.get("status", "unknown"),
        )
    
    async def process_stripe_webhook(self, webhook: StripeWebhook):
        """Process Stripe payment webhooks."""
        logger.info("Processing Stripe webhook",
                   event_type=webhook.event_type,
                   customer_id=webhook.customer_id)
        
        await self.billing_system.process_webhook(webhook)
        
        # Handle payment-related actions
        if webhook.event_type == "invoice.payment_failed":
            await self._handle_payment_failure(webhook)
        elif webhook.event_type == "customer.subscription.deleted":
            await self._handle_subscription_cancellation(webhook)
    
    async def process_monitoring_alert(self, alert: AlertWebhook):
        """Process monitoring alerts with auto-remediation."""
        logger.info("Processing monitoring alert",
                   alert_name=alert.alert_name,
                   severity=alert.severity,
                   client_id=alert.client_id)
        
        # Attempt auto-remediation for known issues
        remediation_result = await self.monitoring.attempt_auto_remediation(alert)
        
        if remediation_result.success:
            logger.info("Alert auto-remediated successfully",
                       alert_name=alert.alert_name,
                       action=remediation_result.action)
        else:
            # Escalate to human operator
            await self.approval_gateway.escalate_alert(
                alert=alert,
                remediation_attempts=remediation_result.attempts
            )
    
    async def _generate_deployment_plan(self, request: OnboardingRequest) -> DeploymentPlan:
        """Generate comprehensive deployment plan."""
        plan_id = f"plan_{datetime.now().strftime('%Y%m%d%H%M%S')}_{request.client_name.lower().replace(' ', '_')}"
        
        # Calculate costs based on service tier
        tier_costs = {
            ServiceTier.WEBSITE: {"setup": 899.0, "monthly": 49.99},
            ServiceTier.WEBSHOP: {"setup": 1699.0, "monthly": 119.99}, 
            ServiceTier.PORTAL: {"setup": 4999.0, "monthly": 129.99}
        }
        
        costs = tier_costs[request.service_tier]
        
        # Determine resource requirements
        tier_resources = {
            ServiceTier.WEBSITE: {"cpu": "500m", "memory": "512Mi", "storage": "1Gi"},
            ServiceTier.WEBSHOP: {"cpu": "1000m", "memory": "1Gi", "storage": "5Gi"},
            ServiceTier.PORTAL: {"cpu": "2000m", "memory": "4Gi", "storage": "20Gi"}
        }
        
        resources = tier_resources[request.service_tier]
        
        # Generate deployment steps
        steps = [
            f"Create Kubernetes namespace for {request.client_name}",
            f"Deploy {request.template} template",
            f"Configure SSL certificate for {request.domain}",
            f"Setup {request.service_tier} monitoring",
            "Configure automated backups",
            "Initialize billing subscription"
        ]
        
        return DeploymentPlan(
            plan_id=plan_id,
            client_name=request.client_name,
            service_tier=request.service_tier,
            estimated_cost={
                "setup_fee": costs["setup"],
                "monthly_fee": costs["monthly"],
                "first_year_total": costs["setup"] + (costs["monthly"] * 12)
            },
            resources_required=resources,
            deployment_steps=steps,
            estimated_time=15 if request.service_tier == ServiceTier.WEBSITE else 30,
            requires_approval=costs["setup"] > 1000,  # Auto-approve websites
            risk_level="Low" if request.service_tier == ServiceTier.WEBSITE else "Medium"
        )
    
    async def _execute_deployment(self, workflow_id: str, approved: bool, comments: Optional[str] = None) -> Dict[str, Any]:
        """Execute approved deployment plan."""
        workflow = self.active_workflows[workflow_id]
        request_data = workflow["request"]
        plan_data = workflow["plan"]
        
        if not approved:
            workflow["status"] = "cancelled"
            return {"status": "cancelled"}
        
        logger.info("Executing deployment", workflow_id=workflow_id)
        
        try:
            # Update workflow status
            workflow["status"] = "deploying"
            
            # Execute infrastructure deployment
            deployment_result = await self.infrastructure_manager.deploy_client(
                client_name=request_data["client_name"],
                domain=request_data["domain"],
                service_tier=ServiceTier(request_data["service_tier"]),
                template=request_data["template"],
                resources=plan_data["resources_required"]
            )
            
            # Setup billing
            billing_result = await self.billing_system.setup_client_billing(
                client_name=request_data["client_name"],
                email=request_data["email"],
                service_tier=ServiceTier(request_data["service_tier"]),
                setup_fee=plan_data["estimated_cost"]["setup_fee"]
            )
            
            # Configure monitoring
            monitoring_result = await self.monitoring.setup_client_monitoring(
                client_id=deployment_result["client_id"],
                namespace=deployment_result["namespace"],
                service_tier=ServiceTier(request_data["service_tier"])
            )
            
            # Register client
            client_id = deployment_result["client_id"]
            self.client_registry[client_id] = {
                "name": request_data["client_name"],
                "email": request_data["email"],
                "phone": request_data["phone"],
                "domain": request_data["domain"],
                "service_tier": request_data["service_tier"],
                "template": request_data["template"],
                "created_at": datetime.now().isoformat(),
                "status": "active"
            }
            
            # Update workflow
            workflow["status"] = "completed"
            workflow["client_id"] = client_id
            workflow["deployment_result"] = deployment_result
            
            logger.info("Deployment completed successfully",
                       workflow_id=workflow_id,
                       client_id=client_id)
            
            return {
                "status": "completed",
                "client_id": client_id,
                "domain": request_data["domain"],
                "access_url": deployment_result["access_url"],
                "admin_credentials": deployment_result["admin_credentials"]
            }
            
        except Exception as e:
            logger.error("Deployment failed",
                        workflow_id=workflow_id,
                        error=str(e))
            
            workflow["status"] = "failed"
            workflow["error"] = str(e)
            
            raise
    
    async def _handle_payment_failure(self, webhook: StripeWebhook):
        """Handle failed payments with grace period."""
        logger.warning("Payment failure detected",
                      customer_id=webhook.customer_id)
        
        # Find client by Stripe customer ID
        client_id = await self.billing_system.get_client_by_stripe_id(webhook.customer_id)
        
        if client_id:
            # Start grace period workflow
            await self.billing_system.start_payment_grace_period(client_id)
            
            # Notify via WhatsApp
            client_data = self.client_registry.get(client_id)
            if client_data:
                await self.approval_gateway.notify_payment_issue(
                    phone=client_data["phone"],
                    client_name=client_data["name"],
                    amount=webhook.data.get("amount_due", 0)
                )
    
    async def _handle_subscription_cancellation(self, webhook: StripeWebhook):
        """Handle subscription cancellations."""
        logger.info("Subscription cancelled",
                   customer_id=webhook.customer_id)
        
        client_id = await self.billing_system.get_client_by_stripe_id(webhook.customer_id)
        
        if client_id:
            # Schedule service suspension
            await self.infrastructure_manager.schedule_service_suspension(
                client_id=client_id,
                suspend_at=datetime.now() + timedelta(days=7)  # 7-day grace period
            )