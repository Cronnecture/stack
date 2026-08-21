# Agent Core - Orchestration System

## Overview
Central decision engine that coordinates all business processes with human oversight.

## Architecture

```python
class AgentOrchestrator:
    def __init__(self):
        self.workflows = {
            'client_onboarding': ClientOnboardingFlow(),
            'site_deployment': DeploymentFlow(), 
            'incident_response': IncidentFlow(),
            'billing_cycle': BillingFlow()
        }
        self.approval_gateway = ApprovalGateway()
        
    async def process_request(self, request_type, payload):
        workflow = self.workflows[request_type]
        
        # Generate execution plan
        plan = await workflow.generate_plan(payload)
        
        # Require human approval for critical actions
        if plan.requires_approval:
            approved = await self.approval_gateway.request_approval(plan)
            if not approved:
                return self.notify_rejection(plan)
        
        # Execute approved plan
        result = await workflow.execute(plan)
        return result
```

## Key Workflows

### Client Onboarding
1. Parse client requirements (Website/Webshop/Portal)
2. Generate deployment plan with pricing
3. Request human approval
4. Create infrastructure resources
5. Deploy initial template
6. Setup monitoring and billing

### Incident Response  
1. Receive alert from monitoring
2. Analyze issue severity and scope
3. Auto-fix if low-risk, else request approval
4. Execute remediation
5. Notify client of resolution

### Billing Automation
1. Track resource usage
2. Generate invoices via Stripe
3. Handle payment failures
4. Manage service suspensions

## Decision Matrix

| Action Type | Auto-Execute | Requires Approval | Examples |
|-------------|--------------|-------------------|----------|
| SSL Renewal | ✅ | ❌ | Cert expiry < 30 days |
| Site Backup | ✅ | ❌ | Daily automated backups |
| New Deployment | ❌ | ✅ | Client project creation |
| Service Suspension | ❌ | ✅ | Payment failure > 7 days |
| Security Patch | ✅ | ❌ | OS/framework updates |
| Custom Code Deploy | ❌ | ✅ | Client code changes |

## Integration Points

- **Approval Gateway**: WhatsApp/Slack notifications
- **Infrastructure**: Kubernetes API calls  
- **Monitoring**: Prometheus/Grafana alerts
- **Billing**: Stripe webhook processing
- **Templates**: Git-based template deployment