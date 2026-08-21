"""
Pydantic models for API requests and responses.
"""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field


class ServiceTier(str, Enum):
    """Available service tiers."""
    WEBSITE = "website"
    WEBSHOP = "webshop" 
    PORTAL = "portal"


class OnboardingRequest(BaseModel):
    """Client onboarding request model."""
    
    client_name: str = Field(..., description="Client business name")
    email: str = Field(..., description="Client contact email")
    phone: str = Field("", description="Client WhatsApp number")
    domain: str = Field(..., description="Desired domain name")
    service_tier: ServiceTier = Field(..., description="Service level required")
    template: str = Field(..., description="Template type (business, restaurant, etc.)")
    requirements: Dict[str, Any] = Field(default_factory=dict, description="Additional requirements")
    
    class Config:
        json_schema_extra = {
            "example": {
                "client_name": "Atelier Linde",
                "email": "linde@atelierlinde.nl", 
                "phone": "+31612345678",
                "domain": "atelierlinde.nl",
                "service_tier": "website",
                "template": "salon",
                "requirements": {
                    "booking_system": True,
                    "payment_integration": False
                }
            }
        }


class ApprovalResponse(BaseModel):
    """Human approval response model."""
    
    approved: bool = Field(..., description="Whether the request is approved")
    comments: Optional[str] = Field(None, description="Additional comments")
    modifications: Optional[Dict[str, Any]] = Field(None, description="Requested modifications")


class ClientStatus(BaseModel):
    """Client service status model."""
    
    client_id: str
    client_name: str
    service_tier: ServiceTier
    domain: str
    status: str = Field(..., description="Overall service status")
    uptime_percentage: float = Field(..., description="30-day uptime %")
    last_deployment: datetime
    ssl_expiry: datetime
    resource_usage: Dict[str, Any]
    billing_status: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "client_id": "atelier-linde",
                "client_name": "Atelier Linde", 
                "service_tier": "website",
                "domain": "atelierlinde.nl",
                "status": "healthy",
                "uptime_percentage": 99.9,
                "last_deployment": "2026-08-20T10:30:00Z",
                "ssl_expiry": "2026-11-20T00:00:00Z",
                "resource_usage": {
                    "cpu": "15%",
                    "memory": "128MB",
                    "storage": "850MB"
                },
                "billing_status": "current"
            }
        }


class StripeWebhook(BaseModel):
    """Stripe webhook event model."""
    
    event_type: str = Field(..., description="Stripe event type")
    customer_id: str = Field(..., description="Stripe customer ID")
    data: Dict[str, Any] = Field(..., description="Event payload")
    created: datetime = Field(..., description="Event timestamp")


class AlertWebhook(BaseModel):
    """Prometheus alert webhook model."""
    
    alert_name: str = Field(..., description="Alert rule name")
    severity: str = Field(..., description="Alert severity level")
    client_id: Optional[str] = Field(None, description="Affected client")
    namespace: Optional[str] = Field(None, description="Kubernetes namespace")
    description: str = Field(..., description="Alert description")
    labels: Dict[str, str] = Field(default_factory=dict, description="Alert labels")
    annotations: Dict[str, str] = Field(default_factory=dict, description="Alert annotations")
    starts_at: datetime = Field(..., description="Alert start time")
    
    class Config:
        json_schema_extra = {
            "example": {
                "alert_name": "HighErrorRate",
                "severity": "warning",
                "client_id": "atelier-linde", 
                "namespace": "client-atelier-linde",
                "description": "Error rate above 5% for 2 minutes",
                "labels": {
                    "app": "atelier-linde",
                    "tier": "website"
                },
                "annotations": {
                    "runbook_url": "https://docs.cronnecture.com/runbooks/high-error-rate"
                },
                "starts_at": "2026-08-21T18:45:00Z"
            }
        }


class DeploymentPlan(BaseModel):
    """Generated deployment plan model."""
    
    plan_id: str
    client_name: str
    service_tier: ServiceTier
    estimated_cost: Dict[str, float]
    resources_required: Dict[str, Any]
    deployment_steps: List[str]
    estimated_time: int = Field(..., description="Estimated completion time in minutes")
    requires_approval: bool = Field(default=True)
    risk_level: str = Field(..., description="Low, Medium, or High")
    
    class Config:
        json_schema_extra = {
            "example": {
                "plan_id": "plan_2026082118_atelier_linde",
                "client_name": "Atelier Linde",
                "service_tier": "website", 
                "estimated_cost": {
                    "setup_fee": 899.0,
                    "monthly_fee": 49.99,
                    "first_year_total": 1498.88
                },
                "resources_required": {
                    "cpu": "500m",
                    "memory": "512Mi",
                    "storage": "1Gi"
                },
                "deployment_steps": [
                    "Create Kubernetes namespace",
                    "Deploy salon template",
                    "Configure SSL certificate",
                    "Setup monitoring",
                    "Configure billing"
                ],
                "estimated_time": 15,
                "requires_approval": True,
                "risk_level": "Low"
            }
        }