#!/usr/bin/env python3
"""
Cronnecture Master Intelligence Orchestrator
Autonomous system coordination with AI-driven decision making and enterprise management
"""

import os
import sys
import json
import asyncio
import logging
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
from pathlib import Path
import subprocess
import yaml
import kubernetes
from kubernetes import client, config
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
import signal

# Import our intelligence modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from core.credential_manager import IntelligentCredentialManager
from monitoring.intelligent_monitoring import IntelligentMonitoringSystem
from integrations.cloudflare_manager import CloudflareIntelligenceOrchestrator

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class ServiceHealth:
    """Service health status"""
    name: str
    status: str  # healthy, degraded, unhealthy, unknown
    last_check: datetime
    response_time_ms: Optional[float] = None
    error_message: Optional[str] = None
    
@dataclass
class InfrastructureState:
    """Current infrastructure state"""
    timestamp: datetime
    cluster_health: str
    node_count: int
    pod_count: int
    namespace_count: int
    cpu_usage_percent: float
    memory_usage_percent: float
    disk_usage_percent: float
    network_throughput_mbps: float
    
@dataclass
class IntelligenceDecision:
    """AI-driven decision with rationale"""
    id: str
    timestamp: datetime
    decision_type: str  # scaling, security, maintenance, optimization
    action: str
    rationale: str
    confidence: float  # 0.0 to 1.0
    expected_impact: str
    auto_execute: bool
    executed: bool = False
    
@dataclass
class ClientConfiguration:
    """Client hosting configuration"""
    client_id: str
    domain: str
    service_tier: str  # basic, standard, premium, enterprise
    resource_limits: Dict[str, Any]
    security_level: str
    backup_schedule: str
    monitoring_enabled: bool

class IntelligentDecisionEngine:
    """AI-driven decision making for infrastructure management"""
    
    def __init__(self):
        self.decision_history = []
        self.learning_data = {}
        self.decision_rules = {
            "scaling": {
                "cpu_threshold_up": 80.0,
                "cpu_threshold_down": 20.0,
                "memory_threshold_up": 85.0,
                "memory_threshold_down": 30.0,
                "min_confidence": 0.7
            },
            "security": {
                "threat_threshold": 100,
                "anomaly_threshold": 0.5,
                "auto_block_threshold": 0.9
            },
            "maintenance": {
                "disk_threshold": 85.0,
                "restart_threshold": 10,
                "update_interval_hours": 24
            }
        }
        
    def analyze_infrastructure_state(self, state: InfrastructureState) -> List[IntelligenceDecision]:
        """Analyze infrastructure and generate intelligent decisions"""
        decisions = []
        now = datetime.now()
        
        # CPU-based scaling decisions
        if state.cpu_usage_percent > self.decision_rules["scaling"]["cpu_threshold_up"]:
            decision = IntelligenceDecision(
                id=f"scale_up_{int(now.timestamp())}",
                timestamp=now,
                decision_type="scaling",
                action="scale_up_cpu_intensive_workloads",
                rationale=f"CPU usage at {state.cpu_usage_percent:.1f}% exceeds threshold of {self.decision_rules['scaling']['cpu_threshold_up']}%",
                confidence=min(0.95, (state.cpu_usage_percent - 70) / 30),
                expected_impact="Improve response times and prevent CPU bottlenecks",
                auto_execute=False
            )
            decisions.append(decision)
            
        elif state.cpu_usage_percent < self.decision_rules["scaling"]["cpu_threshold_down"]:
            decision = IntelligenceDecision(
                id=f"scale_down_{int(now.timestamp())}",
                timestamp=now,
                decision_type="scaling",
                action="scale_down_excess_capacity",
                rationale=f"CPU usage at {state.cpu_usage_percent:.1f}% is below threshold of {self.decision_rules['scaling']['cpu_threshold_down']}%",
                confidence=0.8,
                expected_impact="Optimize resource costs while maintaining performance",
                auto_execute=False  # More conservative on scale-down
            )
            decisions.append(decision)
            
        # Memory-based decisions
        if state.memory_usage_percent > self.decision_rules["scaling"]["memory_threshold_up"]:
            decision = IntelligenceDecision(
                id=f"memory_scale_{int(now.timestamp())}",
                timestamp=now,
                decision_type="scaling",
                action="increase_memory_limits",
                rationale=f"Memory usage at {state.memory_usage_percent:.1f}% approaching capacity",
                confidence=0.9,
                expected_impact="Prevent OOM kills and improve application stability",
                auto_execute=False
            )
            decisions.append(decision)
            
        # Disk maintenance decisions
        if state.disk_usage_percent > self.decision_rules["maintenance"]["disk_threshold"]:
            decision = IntelligenceDecision(
                id=f"disk_cleanup_{int(now.timestamp())}",
                timestamp=now,
                decision_type="maintenance",
                action="cleanup_disk_space",
                rationale=f"Disk usage at {state.disk_usage_percent:.1f}% requires cleanup",
                confidence=0.95,
                expected_impact="Prevent disk space exhaustion and maintain system stability",
                auto_execute=False
            )
            decisions.append(decision)
            
        return decisions
        
    def learn_from_decision_outcome(self, decision: IntelligenceDecision, outcome: Dict[str, Any]):
        """Learn from decision outcomes to improve future decisions"""
        learning_key = f"{decision.decision_type}_{decision.action}"
        
        if learning_key not in self.learning_data:
            self.learning_data[learning_key] = {
                "total_decisions": 0,
                "successful_outcomes": 0,
                "avg_impact": 0.0,
                "confidence_accuracy": []
            }
            
        data = self.learning_data[learning_key]
        data["total_decisions"] += 1
        
        if outcome.get("success", False):
            data["successful_outcomes"] += 1
            
        # Track confidence vs actual outcome for calibration
        actual_success = 1.0 if outcome.get("success", False) else 0.0
        data["confidence_accuracy"].append({
            "predicted_confidence": decision.confidence,
            "actual_success": actual_success
        })
        
        # Adjust decision rules based on learning
        self._adjust_decision_thresholds(decision.decision_type, outcome)
        
    def _adjust_decision_thresholds(self, decision_type: str, outcome: Dict[str, Any]):
        """Dynamically adjust decision thresholds based on outcomes"""
        if decision_type == "scaling" and not outcome.get("success", False):
            # If scaling decision failed, be more conservative
            if "cpu" in outcome.get("error", ""):
                self.decision_rules["scaling"]["cpu_threshold_up"] += 2.0
                
        elif decision_type == "scaling" and outcome.get("success", False):
            # If successful, can be slightly more aggressive
            self.decision_rules["scaling"]["cpu_threshold_up"] = max(75.0, 
                self.decision_rules["scaling"]["cpu_threshold_up"] - 0.5)

class AutonomousServiceManager:
    """Manage services with autonomous decision making"""
    
    def __init__(self):
        self.service_registry = {}
        self.health_checks = {}
        self.auto_healing_enabled = False
        
        # Initialize Kubernetes client
        try:
            config.load_incluster_config()
        except:
            try:
                config.load_kube_config()
            except:
                pass
                
        try:
            self.k8s_client = client.CoreV1Api()
            self.apps_client = client.AppsV1Api()
        except:
            self.k8s_client = None
            self.apps_client = None
            logger.warning("Kubernetes client not available")
            
    async def register_service(self, name: str, namespace: str, health_check_url: str = None):
        """Register service for autonomous management"""
        self.service_registry[name] = {
            "namespace": namespace,
            "health_check_url": health_check_url,
            "last_health_check": None,
            "consecutive_failures": 0,
            "auto_restart_enabled": True
        }
        
        logger.info(f"Registered service for autonomous management: {name}")
        
    async def check_service_health(self, service_name: str) -> ServiceHealth:
        """Check individual service health"""
        if service_name not in self.service_registry:
            return ServiceHealth(
                name=service_name,
                status="unknown",
                last_check=datetime.now(),
                error_message="Service not registered"
            )
            
        service_info = self.service_registry[service_name]
        now = datetime.now()
        
        try:
            if self.k8s_client:
                # Check Kubernetes pod status
                pods = self.k8s_client.list_namespaced_pod(
                    namespace=service_info["namespace"],
                    label_selector=f"app={service_name}"
                )
                
                running_pods = 0
                total_pods = len(pods.items)
                
                for pod in pods.items:
                    if pod.status.phase == "Running":
                        running_pods += 1
                        
                if total_pods == 0:
                    status = "unknown"
                    error_msg = "No pods found"
                elif running_pods == total_pods:
                    status = "healthy"
                    error_msg = None
                elif running_pods > 0:
                    status = "degraded"
                    error_msg = f"Only {running_pods}/{total_pods} pods running"
                else:
                    status = "unhealthy"
                    error_msg = "All pods down"
                    
                return ServiceHealth(
                    name=service_name,
                    status=status,
                    last_check=now,
                    error_message=error_msg
                )
                
        except Exception as e:
            return ServiceHealth(
                name=service_name,
                status="unknown",
                last_check=now,
                error_message=f"Health check error: {e}"
            )
            
    async def auto_heal_service(self, service_name: str, health: ServiceHealth) -> bool:
        """Autonomously heal unhealthy services — disabled for mail/identity overlay."""
        protected = {"mail", "identity", "kube-system", "cert-manager", "platform"}
        service_info = self.service_registry.get(service_name)
        namespace = (service_info or {}).get("namespace", "")
        if namespace in protected:
            logger.info(f"Refusing to heal protected namespace {namespace} ({service_name})")
            return False
        if not self.auto_healing_enabled or health.status == "healthy":
            return True
        logger.info(f"Auto-healing disabled; not mutating {service_name} ({health.status})")
        return False

class ClientProvisioningEngine:
    """Autonomous client provisioning and management"""
    
    def __init__(self, credential_manager: IntelligentCredentialManager):
        self.credential_manager = credential_manager
        self.client_configs = {}
        self.provisioning_templates = {
            "basic": {
                "cpu_request": "100m",
                "cpu_limit": "500m",
                "memory_request": "128Mi",
                "memory_limit": "512Mi",
                "storage": "1Gi",
                "replicas": 1
            },
            "standard": {
                "cpu_request": "250m",
                "cpu_limit": "1000m",
                "memory_request": "256Mi",
                "memory_limit": "1Gi",
                "storage": "5Gi",
                "replicas": 2
            },
            "premium": {
                "cpu_request": "500m",
                "cpu_limit": "2000m",
                "memory_request": "512Mi",
                "memory_limit": "2Gi",
                "storage": "10Gi",
                "replicas": 3
            },
            "enterprise": {
                "cpu_request": "1000m",
                "cpu_limit": "4000m",
                "memory_request": "1Gi",
                "memory_limit": "4Gi",
                "storage": "20Gi",
                "replicas": 5
            }
        }
        
    async def provision_client(self, config: ClientConfiguration) -> Dict[str, Any]:
        """Autonomously provision new client infrastructure"""
        results = {
            "client_id": config.client_id,
            "provisioning_steps": [],
            "resources_created": [],
            "credentials_generated": [],
            "errors": []
        }
        
        try:
            # 1. Create namespace
            namespace_name = f"client-{config.client_id}"
            namespace_manifest = {
                "apiVersion": "v1",
                "kind": "Namespace",
                "metadata": {
                    "name": namespace_name,
                    "labels": {
                        "cronnecture.com/client": config.client_id,
                        "cronnecture.com/tier": config.service_tier,
                        "cronnecture.com/managed": "true"
                    }
                }
            }
            
            # Apply namespace
            k8s_client = client.CoreV1Api()
            try:
                k8s_client.create_namespace(body=namespace_manifest)
                results["provisioning_steps"].append("Created client namespace")
                results["resources_created"].append(f"namespace/{namespace_name}")
            except kubernetes.client.ApiException as e:
                if e.status != 409:  # Already exists is OK
                    raise
                    
            # 2. Generate credentials
            db_password_id = self.credential_manager.create_credential(
                name="database_password",
                service_type="database",
                namespace=namespace_name,
                tags={"client_id": config.client_id, "service": "database"}
            )
            
            api_key_id = self.credential_manager.create_credential(
                name="api_key",
                service_type="api_key", 
                namespace=namespace_name,
                tags={"client_id": config.client_id, "service": "api"}
            )
            
            results["credentials_generated"].extend([db_password_id, api_key_id])
            results["provisioning_steps"].append("Generated security credentials")
            
            # 3. Create resource quota
            template = self.provisioning_templates.get(config.service_tier, self.provisioning_templates["basic"])
            
            quota_manifest = {
                "apiVersion": "v1",
                "kind": "ResourceQuota",
                "metadata": {
                    "name": "client-quota",
                    "namespace": namespace_name
                },
                "spec": {
                    "hard": {
                        "requests.cpu": template["cpu_request"],
                        "requests.memory": template["memory_request"],
                        "limits.cpu": template["cpu_limit"],
                        "limits.memory": template["memory_limit"],
                        "persistentvolumeclaims": "3",
                        "pods": str(template["replicas"] * 2)
                    }
                }
            }
            
            k8s_client.create_namespaced_resource_quota(
                namespace=namespace_name,
                body=quota_manifest
            )
            
            results["provisioning_steps"].append("Applied resource quotas")
            results["resources_created"].append(f"resourcequota/{namespace_name}/client-quota")
            
            # 4. Store client configuration
            self.client_configs[config.client_id] = config
            
            logger.info(f"Successfully provisioned client: {config.client_id}")
            
        except Exception as e:
            error_msg = f"Client provisioning failed: {e}"
            results["errors"].append(error_msg)
            logger.error(error_msg)
            
        return results

class MasterIntelligenceOrchestrator:
    """Main orchestrator coordinating all intelligence services"""
    
    def __init__(self, config_path: str = "/etc/cronnecture/config.yaml"):
        self.config_path = config_path
        self.config = self._load_config()
        
        # Initialize core components
        self.credential_manager = IntelligentCredentialManager()
        self.monitoring_system = IntelligentMonitoringSystem()
        self.decision_engine = IntelligentDecisionEngine()
        self.service_manager = AutonomousServiceManager()
        self.service_manager.auto_healing_enabled = bool(
            self.config.get("monitoring", {}).get("auto_healing", False)
        )
        self.provisioning_engine = ClientProvisioningEngine(self.credential_manager)
        
        # Initialize Cloudflare if configured
        self.cloudflare_orchestrator = None
        if all(k in self.config.get("cloudflare", {}) for k in ["api_token", "account_id", "zone_id"]):
            cf_config = self.config["cloudflare"]
            self.cloudflare_orchestrator = CloudflareIntelligenceOrchestrator(
                cf_config["api_token"],
                cf_config["account_id"],
                cf_config["zone_id"]
            )
            
        # State tracking
        self.running = False
        self.last_decision_cycle = None
        self.system_state = {}
        
        # Initialize database
        self.db_path = "/var/lib/cronnecture/orchestrator.db"
        self._init_database()
        
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file or environment"""
        config = {
            "monitoring": {
                "cycle_interval": 300,  # 5 minutes
                "decision_interval": 600,  # 10 minutes
                "auto_healing": False
            },
            "security": {
                "auto_rotation": False,
                "compliance_monitoring": True
            },
            "scaling": {
                "auto_scaling": False,
                "max_replicas": 10
            }
        }
        
        # Load from file if exists
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    file_config = yaml.safe_load(f)
                    config.update(file_config)
            except Exception as e:
                logger.warning(f"Could not load config file: {e}")
                
        # Cloudflare stays off unless explicitly enabled. Do not pick up
        # CLOUDFLARE_* env vars by default — DNS/WAF mutation is out of scope.
        if os.environ.get("CLOUDFLARE_ENABLED", "").lower() in ("1", "true", "yes"):
            if "CLOUDFLARE_API_TOKEN" in os.environ:
                config.setdefault("cloudflare", {})["api_token"] = os.environ["CLOUDFLARE_API_TOKEN"]
            if "CLOUDFLARE_ACCOUNT_ID" in os.environ:
                config.setdefault("cloudflare", {})["account_id"] = os.environ["CLOUDFLARE_ACCOUNT_ID"]
            if "CLOUDFLARE_ZONE_ID" in os.environ:
                config.setdefault("cloudflare", {})["zone_id"] = os.environ["CLOUDFLARE_ZONE_ID"]

        return config
        
    def _init_database(self):
        """Initialize orchestrator database"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS decisions (
                id TEXT PRIMARY KEY,
                timestamp DATETIME,
                decision_type TEXT,
                action TEXT,
                rationale TEXT,
                confidence REAL,
                auto_execute BOOLEAN,
                executed BOOLEAN,
                outcome TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS system_state (
                timestamp DATETIME PRIMARY KEY,
                cluster_health TEXT,
                node_count INTEGER,
                pod_count INTEGER,
                cpu_usage REAL,
                memory_usage REAL,
                disk_usage REAL
            )
        ''')
        
        conn.commit()
        conn.close()
        
    async def run_decision_cycle(self) -> Dict[str, Any]:
        """Run one intelligence decision cycle"""
        logger.info("Starting intelligence decision cycle")
        
        cycle_results = {
            "timestamp": datetime.now().isoformat(),
            "decisions_made": [],
            "actions_executed": [],
            "system_state": {},
            "errors": []
        }
        
        try:
            # 1. Collect current system state
            system_state = await self._collect_system_state()
            cycle_results["system_state"] = asdict(system_state)
            
            # 2. Run monitoring cycle
            monitoring_results = await self.monitoring_system.monitoring_cycle()
            
            # 3. Generate intelligent decisions
            decisions = self.decision_engine.analyze_infrastructure_state(system_state)
            
            for decision in decisions:
                cycle_results["decisions_made"].append(asdict(decision))
                
                # Auto-execute is disabled for production overlay (mail/identity stay untouched).
                if decision.auto_execute and self.config.get("scaling", {}).get("auto_scaling"):
                    success = await self._execute_decision(decision)
                    if success:
                        decision.executed = True
                        cycle_results["actions_executed"].append(decision.action)
                elif decision.auto_execute:
                    logger.info(f"Skipping auto-execute for {decision.action} (auto_scaling disabled)")
                        
                # Store decision
                self._store_decision(decision)
                
            # 4. Run autonomous service management
            await self._run_service_management()
            
            # 5. Update Cloudflare if configured
            if self.cloudflare_orchestrator:
                cf_results = await self.cloudflare_orchestrator.run_intelligent_monitoring()
                cycle_results["cloudflare_monitoring"] = cf_results
                
            # 6. Run credential management cycle
            cred_results = self.credential_manager.run_intelligence_cycle()
            cycle_results["credential_management"] = cred_results
            
            self.last_decision_cycle = datetime.now()
            
        except Exception as e:
            error_msg = f"Decision cycle error: {e}"
            cycle_results["errors"].append(error_msg)
            logger.error(error_msg)
            
        logger.info(f"Decision cycle completed: {len(cycle_results['decisions_made'])} decisions, {len(cycle_results['actions_executed'])} actions executed")
        return cycle_results
        
    async def _collect_system_state(self) -> InfrastructureState:
        """Collect current infrastructure state"""
        try:
            # Get system metrics (simplified - in real implementation would integrate with monitoring)
            import psutil
            
            cpu_usage = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # Get Kubernetes state
            node_count = 0
            pod_count = 0
            namespace_count = 0
            
            try:
                k8s_client = client.CoreV1Api()
                
                nodes = k8s_client.list_node()
                node_count = len(nodes.items)
                
                pods = k8s_client.list_pod_for_all_namespaces()
                pod_count = len(pods.items)
                
                namespaces = k8s_client.list_namespace()
                namespace_count = len(namespaces.items)
                
            except:
                pass
                
            return InfrastructureState(
                timestamp=datetime.now(),
                cluster_health="healthy",  # Simplified
                node_count=node_count,
                pod_count=pod_count,
                namespace_count=namespace_count,
                cpu_usage_percent=cpu_usage,
                memory_usage_percent=memory.percent,
                disk_usage_percent=(disk.used / disk.total) * 100,
                network_throughput_mbps=0.0  # Would integrate with network monitoring
            )
            
        except Exception as e:
            logger.error(f"Error collecting system state: {e}")
            return InfrastructureState(
                timestamp=datetime.now(),
                cluster_health="unknown",
                node_count=0,
                pod_count=0,
                namespace_count=0,
                cpu_usage_percent=0.0,
                memory_usage_percent=0.0,
                disk_usage_percent=0.0,
                network_throughput_mbps=0.0
            )
            
    async def _execute_decision(self, decision: IntelligenceDecision) -> bool:
        """Execute autonomous decision. Scaling/healing of cluster workloads is disabled."""
        logger.info(f"Evaluating decision: {decision.action}")

        if decision.decision_type == "scaling" or "scale" in decision.action:
            logger.warning(f"Refusing to execute scaling decision: {decision.action}")
            return False

        try:
            if decision.action == "cleanup_disk_space":
                subprocess.run(["find", "/tmp", "-type", "f", "-mtime", "+7", "-delete"],
                             capture_output=True, check=False)
                return True

            elif decision.action == "increase_memory_limits":
                logger.info("Memory-limit changes are advisory only")
                return True

        except Exception as e:
            logger.error(f"Failed to execute decision {decision.action}: {e}")
            return False

        return False

    async def _scale_workloads(self, scale_up: bool) -> bool:
        """Cluster-wide scaling is disabled to protect mail and identity."""
        logger.warning("Refusing cluster-wide scale operation")
        return False

    async def _run_service_management(self):
        """Run autonomous service management"""
        await self.service_manager.register_service("stalwart-mail", "mail")
        await self.service_manager.register_service("vaultwarden", "identity")

        for service_name in self.service_manager.service_registry:
            health = await self.service_manager.check_service_health(service_name)
            logger.info(f"Service {service_name} health: {health.status}")
            if self.service_manager.auto_healing_enabled:
                await self.service_manager.auto_heal_service(service_name, health)
            else:
                logger.info(f"Auto-heal disabled; not mutating {service_name}")
            
    def _store_decision(self, decision: IntelligenceDecision):
        """Store decision in database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO decisions 
            (id, timestamp, decision_type, action, rationale, confidence, auto_execute, executed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            decision.id,
            decision.timestamp.isoformat(),
            decision.decision_type,
            decision.action,
            decision.rationale,
            decision.confidence,
            decision.auto_execute,
            decision.executed
        ))
        
        conn.commit()
        conn.close()
        
    async def run_continuous_orchestration(self):
        """Run continuous orchestration loop"""
        self.running = True
        logger.info("Starting Cronnecture Master Intelligence Orchestrator")
        
        cycle_count = 0
        
        while self.running:
            try:
                cycle_count += 1
                logger.info(f"=== Master Orchestration Cycle #{cycle_count} ===")
                
                # Run decision cycle
                results = await self.run_decision_cycle()
                
                # Sleep between cycles
                await asyncio.sleep(self.config["monitoring"]["decision_interval"])
                
            except KeyboardInterrupt:
                logger.info("Orchestrator interrupted by user")
                break
            except Exception as e:
                logger.error(f"Error in orchestration cycle: {e}")
                await asyncio.sleep(60)  # Wait 1 minute on error
                
        self.running = False
        logger.info("Master orchestrator stopped")
        
    def stop_orchestration(self):
        """Stop orchestration gracefully"""
        self.running = False

def main():
    """Main entry point for master orchestrator"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Cronnecture Master Intelligence Orchestrator")
    parser.add_argument("--config", default="/etc/cronnecture/config.yaml", 
                       help="Configuration file path")
    parser.add_argument("--daemon", action="store_true",
                       help="Run as daemon")
    args = parser.parse_args()
    
    # Initialize orchestrator
    orchestrator = MasterIntelligenceOrchestrator(config_path=args.config)
    
    # Handle signals for graceful shutdown
    def signal_handler(signum, frame):
        logger.info("Received shutdown signal")
        orchestrator.stop_orchestration()
        
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        if args.daemon:
            logger.info("Starting master orchestrator as daemon")
            asyncio.run(orchestrator.run_continuous_orchestration())
        else:
            logger.info("Running single orchestration cycle")
            results = asyncio.run(orchestrator.run_decision_cycle())
            print(json.dumps(results, indent=2))
            
    except KeyboardInterrupt:
        logger.info("Orchestrator interrupted")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()