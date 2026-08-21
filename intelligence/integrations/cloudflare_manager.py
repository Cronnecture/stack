#!/usr/bin/env python3
"""
Cronnecture Advanced Cloudflare Manager
Automated DNS management, WAF configuration, Zero Trust access, performance optimization
"""

import os
import sys
import json
import asyncio
import aiohttp
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict
import ipaddress
import ssl
import socket
from urllib.parse import urlparse

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class DNSRecord:
    """DNS record configuration"""
    name: str
    type: str  # A, AAAA, CNAME, MX, TXT, etc.
    content: str
    ttl: int = 300
    proxied: bool = False
    priority: Optional[int] = None
    
@dataclass
class WAFRule:
    """WAF rule configuration"""
    id: str
    action: str  # block, challenge, allow, log
    expression: str
    description: str
    enabled: bool = True
    priority: int = 1

@dataclass
class ZeroTrustPolicy:
    """Zero Trust access policy"""
    name: str
    decision: str  # allow, deny, non_identity
    includes: List[Dict[str, Any]]
    excludes: List[Dict[str, Any]] = None
    requires: List[Dict[str, Any]] = None
    
@dataclass
class PerformanceConfig:
    """Performance optimization configuration"""
    minify: Dict[str, bool]
    compression: str  # gzip, brotli, off
    caching_level: str  # aggressive, basic, simplified, off
    browser_cache_ttl: int
    edge_cache_ttl: int
    always_use_https: bool = True
    automatic_https_rewrites: bool = True

class CloudflareAPIClient:
    """Cloudflare API client with intelligent retry and rate limiting"""
    
    def __init__(self, api_token: str, account_id: str, zone_id: str):
        self.api_token = api_token
        self.account_id = account_id
        self.zone_id = zone_id
        self.base_url = "https://api.cloudflare.com/client/v4"
        self.session = None
        self.rate_limit_remaining = 1000
        self.rate_limit_reset = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            headers={
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json"
            },
            timeout=aiohttp.ClientTimeout(total=30)
        )
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
            
    async def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict:
        """Make API request with intelligent retry and rate limiting"""
        if not self.session:
            raise RuntimeError("API client not initialized. Use 'async with' context.")
            
        # Check rate limits
        if self.rate_limit_remaining < 10:
            if self.rate_limit_reset:
                sleep_time = (self.rate_limit_reset - datetime.now()).total_seconds()
                if sleep_time > 0:
                    logger.info(f"Rate limit approaching, sleeping {sleep_time:.1f}s")
                    await asyncio.sleep(sleep_time)
                    
        url = f"{self.base_url}{endpoint}"
        
        for attempt in range(3):  # Retry up to 3 times
            try:
                if method.upper() == "GET":
                    async with self.session.get(url) as response:
                        return await self._handle_response(response)
                elif method.upper() == "POST":
                    async with self.session.post(url, json=data) as response:
                        return await self._handle_response(response)
                elif method.upper() == "PUT":
                    async with self.session.put(url, json=data) as response:
                        return await self._handle_response(response)
                elif method.upper() == "DELETE":
                    async with self.session.delete(url) as response:
                        return await self._handle_response(response)
                elif method.upper() == "PATCH":
                    async with self.session.patch(url, json=data) as response:
                        return await self._handle_response(response)
                        
            except aiohttp.ClientError as e:
                logger.warning(f"Request attempt {attempt + 1} failed: {e}")
                if attempt == 2:  # Last attempt
                    raise
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
                
    async def _handle_response(self, response: aiohttp.ClientResponse) -> Dict:
        """Handle API response and extract rate limit info"""
        # Update rate limit info
        self.rate_limit_remaining = int(response.headers.get('CF-RateLimit-Remaining', 1000))
        reset_timestamp = response.headers.get('CF-RateLimit-Reset')
        if reset_timestamp:
            self.rate_limit_reset = datetime.fromtimestamp(int(reset_timestamp))
            
        response_data = await response.json()
        
        if not response_data.get("success", False):
            errors = response_data.get("errors", [])
            error_msg = "; ".join([error.get("message", "Unknown error") for error in errors])
            raise Exception(f"Cloudflare API error: {error_msg}")
            
        return response_data
        
class IntelligentDNSManager:
    """Intelligent DNS management with automation and monitoring"""
    
    def __init__(self, api_client: CloudflareAPIClient):
        self.api = api_client
        self.dns_cache = {}
        self.health_checks = {}
        
    async def get_dns_records(self, record_type: Optional[str] = None) -> List[DNSRecord]:
        """Get all DNS records for the zone"""
        params = {}
        if record_type:
            params["type"] = record_type
            
        endpoint = f"/zones/{self.api.zone_id}/dns_records"
        if params:
            param_str = "&".join([f"{k}={v}" for k, v in params.items()])
            endpoint += f"?{param_str}"
            
        response = await self.api._make_request("GET", endpoint)
        
        records = []
        for record_data in response.get("result", []):
            records.append(DNSRecord(
                name=record_data["name"],
                type=record_data["type"],
                content=record_data["content"],
                ttl=record_data["ttl"],
                proxied=record_data.get("proxied", False),
                priority=record_data.get("priority")
            ))
            
        return records
        
    async def create_dns_record(self, record: DNSRecord) -> str:
        """Create DNS record"""
        data = {
            "type": record.type,
            "name": record.name,
            "content": record.content,
            "ttl": record.ttl,
            "proxied": record.proxied
        }
        
        if record.priority is not None:
            data["priority"] = record.priority
            
        endpoint = f"/zones/{self.api.zone_id}/dns_records"
        response = await self.api._make_request("POST", endpoint, data)
        
        record_id = response["result"]["id"]
        logger.info(f"Created DNS record: {record.name} -> {record.content}")
        return record_id
        
    async def update_dns_record(self, record_id: str, record: DNSRecord) -> bool:
        """Update existing DNS record"""
        data = {
            "type": record.type,
            "name": record.name,
            "content": record.content,
            "ttl": record.ttl,
            "proxied": record.proxied
        }
        
        if record.priority is not None:
            data["priority"] = record.priority
            
        endpoint = f"/zones/{self.api.zone_id}/dns_records/{record_id}"
        await self.api._make_request("PUT", endpoint, data)
        
        logger.info(f"Updated DNS record: {record.name} -> {record.content}")
        return True
        
    async def delete_dns_record(self, record_id: str) -> bool:
        """Delete DNS record"""
        endpoint = f"/zones/{self.api.zone_id}/dns_records/{record_id}"
        await self.api._make_request("DELETE", endpoint)
        
        logger.info(f"Deleted DNS record: {record_id}")
        return True
        
    async def intelligent_dns_sync(self, target_records: List[DNSRecord]) -> Dict[str, Any]:
        """Intelligently sync DNS records to match target configuration"""
        results = {
            "created": [],
            "updated": [],
            "deleted": [],
            "errors": []
        }
        
        # Get current records
        current_records = await self.get_dns_records()
        current_map = {f"{r.name}_{r.type}": r for r in current_records}
        target_map = {f"{r.name}_{r.type}": r for r in target_records}
        
        # Find records to create, update, or delete
        for key, target_record in target_map.items():
            if key not in current_map:
                # Create new record
                try:
                    record_id = await self.create_dns_record(target_record)
                    results["created"].append({"record": target_record.name, "id": record_id})
                except Exception as e:
                    results["errors"].append(f"Failed to create {target_record.name}: {e}")
                    
            else:
                # Check if update needed
                current_record = current_map[key]
                if (current_record.content != target_record.content or
                    current_record.ttl != target_record.ttl or
                    current_record.proxied != target_record.proxied):
                    
                    try:
                        # Need to find record ID first
                        records_response = await self.api._make_request(
                            "GET", 
                            f"/zones/{self.api.zone_id}/dns_records?name={target_record.name}&type={target_record.type}"
                        )
                        
                        if records_response["result"]:
                            record_id = records_response["result"][0]["id"]
                            await self.update_dns_record(record_id, target_record)
                            results["updated"].append({"record": target_record.name, "id": record_id})
                    except Exception as e:
                        results["errors"].append(f"Failed to update {target_record.name}: {e}")
                        
        # Find records to delete (exist in current but not in target)
        for key, current_record in current_map.items():
            if key not in target_map:
                try:
                    # Get record ID and delete
                    records_response = await self.api._make_request(
                        "GET",
                        f"/zones/{self.api.zone_id}/dns_records?name={current_record.name}&type={current_record.type}"
                    )
                    
                    if records_response["result"]:
                        record_id = records_response["result"][0]["id"]
                        await self.delete_dns_record(record_id)
                        results["deleted"].append({"record": current_record.name, "id": record_id})
                except Exception as e:
                    results["errors"].append(f"Failed to delete {current_record.name}: {e}")
                    
        return results

class AdvancedWAFManager:
    """Advanced WAF management with intelligent rule generation"""
    
    def __init__(self, api_client: CloudflareAPIClient):
        self.api = api_client
        self.rule_templates = {
            "sql_injection": {
                "expression": '(http.request.uri.query contains "union select") or (http.request.body contains "union select")',
                "action": "block",
                "description": "Block SQL injection attempts"
            },
            "xss_protection": {
                "expression": '(http.request.uri.query contains "<script") or (http.request.body contains "<script")',
                "action": "block", 
                "description": "Block XSS attempts"
            },
            "rate_limiting": {
                "expression": "true",
                "action": "challenge",
                "description": "Rate limiting for excessive requests"
            },
            "bot_protection": {
                "expression": 'cf.bot_management.score < 30',
                "action": "challenge",
                "description": "Challenge suspicious bots"
            },
            "geoblocking": {
                "expression": 'ip.geoip.country in {"CN" "RU" "KP"}',
                "action": "block",
                "description": "Block high-risk countries"
            }
        }
        
    async def get_waf_rules(self) -> List[WAFRule]:
        """Get current WAF rules"""
        endpoint = f"/zones/{self.api.zone_id}/firewall/rules"
        response = await self.api._make_request("GET", endpoint)
        
        rules = []
        for rule_data in response.get("result", []):
            rules.append(WAFRule(
                id=rule_data["id"],
                action=rule_data["action"],
                expression=rule_data["filter"]["expression"],
                description=rule_data.get("description", ""),
                enabled=rule_data.get("paused", False) == False,
                priority=rule_data.get("priority", 1)
            ))
            
        return rules
        
    async def create_waf_rule(self, rule: WAFRule) -> str:
        """Create WAF rule"""
        data = {
            "filter": {
                "expression": rule.expression,
                "paused": not rule.enabled
            },
            "action": rule.action,
            "priority": rule.priority,
            "description": rule.description
        }
        
        endpoint = f"/zones/{self.api.zone_id}/firewall/rules"
        response = await self.api._make_request("POST", endpoint, data)
        
        rule_id = response["result"][0]["id"]
        logger.info(f"Created WAF rule: {rule.description}")
        return rule_id
        
    async def update_waf_rule(self, rule_id: str, rule: WAFRule) -> bool:
        """Update WAF rule"""
        data = {
            "filter": {
                "expression": rule.expression,
                "paused": not rule.enabled
            },
            "action": rule.action,
            "priority": rule.priority,
            "description": rule.description
        }
        
        endpoint = f"/zones/{self.api.zone_id}/firewall/rules/{rule_id}"
        await self.api._make_request("PUT", endpoint, data)
        
        logger.info(f"Updated WAF rule: {rule.description}")
        return True
        
    async def deploy_security_ruleset(self, security_level: str = "high") -> Dict[str, Any]:
        """Deploy intelligent security ruleset based on security level"""
        results = {
            "deployed_rules": [],
            "errors": []
        }
        
        # Define security levels
        security_configs = {
            "basic": ["sql_injection", "xss_protection"],
            "medium": ["sql_injection", "xss_protection", "rate_limiting"],
            "high": ["sql_injection", "xss_protection", "rate_limiting", "bot_protection"],
            "maximum": ["sql_injection", "xss_protection", "rate_limiting", "bot_protection", "geoblocking"]
        }
        
        rules_to_deploy = security_configs.get(security_level, security_configs["high"])
        
        for rule_name in rules_to_deploy:
            if rule_name in self.rule_templates:
                template = self.rule_templates[rule_name]
                
                rule = WAFRule(
                    id="",  # Will be set after creation
                    action=template["action"],
                    expression=template["expression"],
                    description=template["description"],
                    enabled=True,
                    priority=len(results["deployed_rules"]) + 1
                )
                
                try:
                    rule_id = await self.create_waf_rule(rule)
                    results["deployed_rules"].append({
                        "name": rule_name,
                        "id": rule_id,
                        "description": rule.description
                    })
                except Exception as e:
                    results["errors"].append(f"Failed to deploy {rule_name}: {e}")
                    
        return results

class ZeroTrustManager:
    """Zero Trust access policy management"""
    
    def __init__(self, api_client: CloudflareAPIClient):
        self.api = api_client
        
    async def create_access_application(self, name: str, domain: str, 
                                      session_duration: str = "24h") -> str:
        """Create Zero Trust access application"""
        data = {
            "name": name,
            "domain": domain,
            "type": "self_hosted",
            "session_duration": session_duration,
            "auto_redirect_to_identity": True,
            "enable_binding_cookie": True
        }
        
        endpoint = f"/accounts/{self.api.account_id}/access/apps"
        response = await self.api._make_request("POST", endpoint, data)
        
        app_id = response["result"]["id"]
        logger.info(f"Created Zero Trust application: {name} -> {domain}")
        return app_id
        
    async def create_access_policy(self, app_id: str, policy: ZeroTrustPolicy) -> str:
        """Create access policy for application"""
        data = {
            "name": policy.name,
            "decision": policy.decision,
            "include": policy.includes,
            "precedence": 1
        }
        
        if policy.excludes:
            data["exclude"] = policy.excludes
        if policy.requires:
            data["require"] = policy.requires
            
        endpoint = f"/accounts/{self.api.account_id}/access/apps/{app_id}/policies"
        response = await self.api._make_request("POST", endpoint, data)
        
        policy_id = response["result"]["id"]
        logger.info(f"Created Zero Trust policy: {policy.name}")
        return policy_id
        
    async def setup_enterprise_zero_trust(self, domains: List[str]) -> Dict[str, Any]:
        """Setup comprehensive Zero Trust access for enterprise domains"""
        results = {
            "applications": [],
            "policies": [],
            "errors": []
        }
        
        # Standard enterprise access rules
        admin_policy = ZeroTrustPolicy(
            name="Admin Access",
            decision="allow",
            includes=[
                {"email_domain": {"domain": "cronnecture.com"}},
                {"group": {"id": "admin_group"}}
            ],
            requires=[
                {"mfa": True}
            ]
        )
        
        dev_policy = ZeroTrustPolicy(
            name="Developer Access",
            decision="allow", 
            includes=[
                {"email_domain": {"domain": "cronnecture.com"}},
                {"group": {"id": "dev_group"}}
            ]
        )
        
        for domain in domains:
            try:
                # Create application
                app_id = await self.create_access_application(
                    name=f"Cronnecture {domain.split('.')[0].title()}",
                    domain=domain
                )
                results["applications"].append({"domain": domain, "app_id": app_id})
                
                # Create policies
                admin_policy_id = await self.create_access_policy(app_id, admin_policy)
                dev_policy_id = await self.create_access_policy(app_id, dev_policy)
                
                results["policies"].extend([
                    {"app_id": app_id, "policy_id": admin_policy_id, "type": "admin"},
                    {"app_id": app_id, "policy_id": dev_policy_id, "type": "developer"}
                ])
                
            except Exception as e:
                results["errors"].append(f"Failed to setup Zero Trust for {domain}: {e}")
                
        return results

class PerformanceOptimizer:
    """Intelligent performance optimization"""
    
    def __init__(self, api_client: CloudflareAPIClient):
        self.api = api_client
        
    async def get_zone_settings(self) -> Dict[str, Any]:
        """Get current zone settings"""
        endpoint = f"/zones/{self.api.zone_id}/settings"
        response = await self.api._make_request("GET", endpoint)
        
        settings = {}
        for setting in response.get("result", []):
            settings[setting["id"]] = setting["value"]
            
        return settings
        
    async def update_zone_setting(self, setting_name: str, value: Any) -> bool:
        """Update zone setting"""
        data = {"value": value}
        
        endpoint = f"/zones/{self.api.zone_id}/settings/{setting_name}"
        await self.api._make_request("PATCH", endpoint, data)
        
        logger.info(f"Updated zone setting: {setting_name} = {value}")
        return True
        
    async def apply_performance_config(self, config: PerformanceConfig) -> Dict[str, Any]:
        """Apply comprehensive performance configuration"""
        results = {
            "updated_settings": [],
            "errors": []
        }
        
        # Performance settings mapping
        settings_map = {
            "minify": config.minify,
            "brotli": "on" if config.compression == "brotli" else "off",
            "cache_level": config.caching_level,
            "browser_cache_ttl": config.browser_cache_ttl,
            "edge_cache_ttl": config.edge_cache_ttl,
            "always_use_https": "on" if config.always_use_https else "off",
            "automatic_https_rewrites": "on" if config.automatic_https_rewrites else "off"
        }
        
        for setting_name, value in settings_map.items():
            try:
                if setting_name == "minify":
                    # Minify is a complex setting
                    await self.update_zone_setting("minify", value)
                else:
                    await self.update_zone_setting(setting_name, value)
                    
                results["updated_settings"].append(setting_name)
                
            except Exception as e:
                results["errors"].append(f"Failed to update {setting_name}: {e}")
                
        return results
        
    async def optimize_for_hosting_platform(self) -> Dict[str, Any]:
        """Apply optimal settings for hosting platform"""
        config = PerformanceConfig(
            minify={
                "css": True,
                "html": True,
                "js": True
            },
            compression="brotli",
            caching_level="aggressive",
            browser_cache_ttl=31536000,  # 1 year
            edge_cache_ttl=86400,        # 1 day
            always_use_https=True,
            automatic_https_rewrites=True
        )
        
        results = await self.apply_performance_config(config)
        
        # Additional hosting platform optimizations
        additional_settings = {
            "rocket_loader": "on",
            "mirage2": "on",
            "polish": "lossless",
            "webp": "on",
            "http2": "on",
            "http3": "on",
            "0rtt": "on",
            "ipv6": "on"
        }
        
        for setting_name, value in additional_settings.items():
            try:
                await self.update_zone_setting(setting_name, value)
                results["updated_settings"].append(setting_name)
            except Exception as e:
                results["errors"].append(f"Failed to update {setting_name}: {e}")
                
        return results

class CloudflareIntelligenceOrchestrator:
    """Main orchestrator for Cloudflare intelligence services"""
    
    def __init__(self, api_token: str, account_id: str, zone_id: str):
        self.api_token = api_token
        self.account_id = account_id
        self.zone_id = zone_id
        
        self.dns_manager = None
        self.waf_manager = None
        self.zerotrust_manager = None
        self.performance_optimizer = None
        
    async def initialize(self):
        """Initialize all managers"""
        api_client = CloudflareAPIClient(self.api_token, self.account_id, self.zone_id)
        
        self.dns_manager = IntelligentDNSManager(api_client)
        self.waf_manager = AdvancedWAFManager(api_client)
        self.zerotrust_manager = ZeroTrustManager(api_client)
        self.performance_optimizer = PerformanceOptimizer(api_client)
        
        logger.info("Cloudflare Intelligence Orchestrator initialized")
        
    async def deploy_hosting_infrastructure(self, 
                                          domains: List[str],
                                          server_ips: List[str],
                                          security_level: str = "high") -> Dict[str, Any]:
        """Deploy complete hosting infrastructure on Cloudflare"""
        results = {
            "dns_sync": {},
            "waf_deployment": {},
            "zerotrust_setup": {},
            "performance_optimization": {},
            "errors": []
        }
        
        try:
            async with CloudflareAPIClient(self.api_token, self.account_id, self.zone_id) as api:
                self.dns_manager = IntelligentDNSManager(api)
                self.waf_manager = AdvancedWAFManager(api)
                self.zerotrust_manager = ZeroTrustManager(api)
                self.performance_optimizer = PerformanceOptimizer(api)
                
                # 1. Setup DNS records
                dns_records = []
                for domain in domains:
                    for ip in server_ips:
                        dns_records.append(DNSRecord(
                            name=domain,
                            type="A",
                            content=ip,
                            ttl=300,
                            proxied=True
                        ))
                        
                results["dns_sync"] = await self.dns_manager.intelligent_dns_sync(dns_records)
                
                # 2. Deploy WAF security
                results["waf_deployment"] = await self.waf_manager.deploy_security_ruleset(security_level)
                
                # 3. Setup Zero Trust access
                results["zerotrust_setup"] = await self.zerotrust_manager.setup_enterprise_zero_trust(domains)
                
                # 4. Optimize performance
                results["performance_optimization"] = await self.performance_optimizer.optimize_for_hosting_platform()
                
        except Exception as e:
            results["errors"].append(f"Infrastructure deployment failed: {e}")
            logger.error(f"Failed to deploy hosting infrastructure: {e}")
            
        return results
        
    async def run_intelligent_monitoring(self) -> Dict[str, Any]:
        """Run intelligent monitoring and optimization cycle"""
        results = {
            "timestamp": datetime.now().isoformat(),
            "health_checks": [],
            "security_analysis": {},
            "performance_metrics": {},
            "recommendations": []
        }
        
        try:
            async with CloudflareAPIClient(self.api_token, self.account_id, self.zone_id) as api:
                # Check zone analytics
                endpoint = f"/zones/{self.zone_id}/analytics/dashboard"
                analytics = await api._make_request("GET", endpoint + "?since=-1440")  # Last 24h
                
                if analytics.get("result"):
                    results["performance_metrics"] = {
                        "requests": analytics["result"]["totals"]["requests"]["all"],
                        "bandwidth": analytics["result"]["totals"]["bandwidth"]["all"],
                        "threats": analytics["result"]["totals"]["threats"]["all"],
                        "pageviews": analytics["result"]["totals"]["pageviews"]["all"]
                    }
                    
                # Security analysis
                firewall_endpoint = f"/zones/{self.zone_id}/firewall/events"
                security_events = await api._make_request("GET", firewall_endpoint + "?since=-1440")
                
                threat_count = len(security_events.get("result", []))
                results["security_analysis"] = {
                    "threats_blocked": threat_count,
                    "security_status": "healthy" if threat_count < 100 else "elevated"
                }
                
                # Generate intelligent recommendations
                recommendations = []
                
                if threat_count > 1000:
                    recommendations.append("High threat activity detected - consider increasing WAF security level")
                    
                if results["performance_metrics"].get("requests", 0) > 1000000:
                    recommendations.append("High traffic volume - consider enabling additional caching optimizations")
                    
                results["recommendations"] = recommendations
                
        except Exception as e:
            results["errors"] = [f"Monitoring cycle failed: {e}"]
            logger.error(f"Monitoring cycle error: {e}")
            
        return results

def main():
    """Main entry point for Cloudflare manager"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Cronnecture Advanced Cloudflare Manager")
    parser.add_argument("--api-token", required=True, help="Cloudflare API token")
    parser.add_argument("--account-id", required=True, help="Cloudflare account ID")
    parser.add_argument("--zone-id", required=True, help="Cloudflare zone ID")
    parser.add_argument("--action", required=True, choices=["deploy", "monitor"], 
                       help="Action to perform")
    parser.add_argument("--domains", nargs="+", help="Domains to configure")
    parser.add_argument("--server-ips", nargs="+", help="Server IP addresses")
    parser.add_argument("--security-level", default="high", 
                       choices=["basic", "medium", "high", "maximum"],
                       help="Security level")
    
    args = parser.parse_args()
    
    # Initialize orchestrator
    orchestrator = CloudflareIntelligenceOrchestrator(
        api_token=args.api_token,
        account_id=args.account_id,
        zone_id=args.zone_id
    )
    
    async def run_action():
        if args.action == "deploy":
            if not args.domains or not args.server_ips:
                logger.error("Domains and server IPs required for deployment")
                return
                
            results = await orchestrator.deploy_hosting_infrastructure(
                domains=args.domains,
                server_ips=args.server_ips,
                security_level=args.security_level
            )
            
            print(json.dumps(results, indent=2))
            
        elif args.action == "monitor":
            results = await orchestrator.run_intelligent_monitoring()
            print(json.dumps(results, indent=2))
            
    try:
        asyncio.run(run_action())
    except KeyboardInterrupt:
        logger.info("Cloudflare manager interrupted")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()