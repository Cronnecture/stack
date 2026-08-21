#!/usr/bin/env python3
"""
Cronnecture Intelligent Monitoring System
ML-based anomaly detection, predictive scaling, self-healing, compliance monitoring
"""

import os
import sys
import json
import time
import asyncio
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import DBSCAN
import kubernetes
from kubernetes import client, config, watch
import psutil
import logging
import aiohttp
import sqlite3
from concurrent.futures import ThreadPoolExecutor
import threading

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class MetricPoint:
    """Single metric observation"""
    timestamp: datetime
    metric_name: str
    value: float
    labels: Dict[str, str]
    node_name: str = ""
    namespace: str = ""
    pod_name: str = ""

@dataclass
class Anomaly:
    """Detected anomaly"""
    id: str
    timestamp: datetime
    metric_name: str
    severity: str  # low, medium, high, critical
    anomaly_score: float
    description: str
    affected_resource: str
    suggested_actions: List[str]
    auto_remediation: bool = False

@dataclass
class PredictionResult:
    """ML prediction result"""
    metric_name: str
    current_value: float
    predicted_value: float
    confidence: float
    trend: str  # increasing, decreasing, stable
    recommendation: str

class MetricsCollector:
    """Collect metrics from multiple sources"""
    
    def __init__(self):
        self.k8s_client = None
        self.metrics_client = None
        
        # Initialize Kubernetes clients
        try:
            config.load_incluster_config()
        except:
            try:
                config.load_kube_config()
            except Exception as e:
                logger.warning(f"Could not load K8s config: {e}")
                
        if kubernetes.config.KUBE_CONFIG_DEFAULT_LOCATION:
            self.k8s_client = client.CoreV1Api()
            self.apps_client = client.AppsV1Api()
            
    async def collect_system_metrics(self) -> List[MetricPoint]:
        """Collect system-level metrics"""
        metrics = []
        now = datetime.now()
        
        # CPU metrics
        cpu_percent = psutil.cpu_percent(interval=1)
        metrics.append(MetricPoint(
            timestamp=now,
            metric_name="system_cpu_usage_percent",
            value=cpu_percent,
            labels={"type": "system"}
        ))
        
        # Memory metrics
        memory = psutil.virtual_memory()
        metrics.append(MetricPoint(
            timestamp=now,
            metric_name="system_memory_usage_percent",
            value=memory.percent,
            labels={"type": "system"}
        ))
        
        metrics.append(MetricPoint(
            timestamp=now,
            metric_name="system_memory_available_gb",
            value=memory.available / (1024**3),
            labels={"type": "system"}
        ))
        
        # Disk metrics
        disk = psutil.disk_usage('/')
        metrics.append(MetricPoint(
            timestamp=now,
            metric_name="system_disk_usage_percent",
            value=(disk.used / disk.total) * 100,
            labels={"type": "system", "mount": "/"}
        ))
        
        # Network metrics
        net_io = psutil.net_io_counters()
        metrics.append(MetricPoint(
            timestamp=now,
            metric_name="system_network_bytes_sent",
            value=net_io.bytes_sent,
            labels={"type": "system", "direction": "sent"}
        ))
        
        metrics.append(MetricPoint(
            timestamp=now,
            metric_name="system_network_bytes_recv",
            value=net_io.bytes_recv,
            labels={"type": "system", "direction": "received"}
        ))
        
        # Load average
        load1, load5, load15 = os.getloadavg()
        metrics.append(MetricPoint(
            timestamp=now,
            metric_name="system_load_average_1m",
            value=load1,
            labels={"type": "system", "interval": "1m"}
        ))
        
        return metrics
        
    async def collect_kubernetes_metrics(self) -> List[MetricPoint]:
        """Collect Kubernetes cluster metrics"""
        if not self.k8s_client:
            return []
            
        metrics = []
        now = datetime.now()
        
        try:
            # Node metrics
            nodes = self.k8s_client.list_node()
            for node in nodes.items:
                node_name = node.metadata.name
                
                # Node status
                node_ready = False
                for condition in node.status.conditions:
                    if condition.type == "Ready":
                        node_ready = condition.status == "True"
                        break
                        
                metrics.append(MetricPoint(
                    timestamp=now,
                    metric_name="kubernetes_node_ready",
                    value=1.0 if node_ready else 0.0,
                    labels={"type": "node", "node": node_name},
                    node_name=node_name
                ))
                
            # Pod metrics
            pods = self.k8s_client.list_pod_for_all_namespaces()
            namespace_pod_counts = {}
            pod_phase_counts = {"Running": 0, "Pending": 0, "Failed": 0, "Succeeded": 0}
            
            for pod in pods.items:
                namespace = pod.metadata.namespace
                namespace_pod_counts[namespace] = namespace_pod_counts.get(namespace, 0) + 1
                
                if pod.status.phase in pod_phase_counts:
                    pod_phase_counts[pod.status.phase] += 1
                    
                # Pod restart count
                restart_count = 0
                if pod.status.container_statuses:
                    restart_count = sum(container.restart_count for container in pod.status.container_statuses)
                    
                metrics.append(MetricPoint(
                    timestamp=now,
                    metric_name="kubernetes_pod_restart_count",
                    value=restart_count,
                    labels={"type": "pod", "namespace": namespace, "pod": pod.metadata.name},
                    namespace=namespace,
                    pod_name=pod.metadata.name
                ))
                
            # Namespace metrics
            for namespace, count in namespace_pod_counts.items():
                metrics.append(MetricPoint(
                    timestamp=now,
                    metric_name="kubernetes_namespace_pod_count",
                    value=count,
                    labels={"type": "namespace", "namespace": namespace},
                    namespace=namespace
                ))
                
            # Phase metrics
            for phase, count in pod_phase_counts.items():
                metrics.append(MetricPoint(
                    timestamp=now,
                    metric_name="kubernetes_pods_by_phase",
                    value=count,
                    labels={"type": "cluster", "phase": phase.lower()}
                ))
                
        except Exception as e:
            logger.error(f"Error collecting Kubernetes metrics: {e}")
            
        return metrics

class AnomalyDetector:
    """ML-based anomaly detection"""
    
    def __init__(self, window_size: int = 100):
        self.window_size = window_size
        self.metric_history = {}
        self.models = {}
        self.scalers = {}
        self.last_training = {}
        
    def add_metric_point(self, metric: MetricPoint):
        """Add metric point to history"""
        key = f"{metric.metric_name}_{metric.node_name}_{metric.namespace}"
        
        if key not in self.metric_history:
            self.metric_history[key] = []
            
        self.metric_history[key].append((metric.timestamp, metric.value))
        
        # Keep only recent points
        if len(self.metric_history[key]) > self.window_size:
            self.metric_history[key] = self.metric_history[key][-self.window_size:]
            
    def train_model(self, metric_key: str) -> bool:
        """Train anomaly detection model for metric"""
        if metric_key not in self.metric_history:
            return False
            
        history = self.metric_history[metric_key]
        if len(history) < 20:  # Need minimum data points
            return False
            
        # Prepare data
        values = [point[1] for point in history]
        X = np.array(values).reshape(-1, 1)
        
        # Scale data
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        
        # Train Isolation Forest
        model = IsolationForest(
            contamination=0.1,  # Expect 10% anomalies
            random_state=42,
            n_estimators=100
        )
        model.fit(X_scaled)
        
        # Store model and scaler
        self.models[metric_key] = model
        self.scalers[metric_key] = scaler
        self.last_training[metric_key] = datetime.now()
        
        logger.info(f"Trained anomaly detection model for {metric_key}")
        return True
        
    def detect_anomaly(self, metric: MetricPoint) -> Optional[Anomaly]:
        """Detect anomaly in metric"""
        key = f"{metric.metric_name}_{metric.node_name}_{metric.namespace}"
        
        # Train model if needed
        if key not in self.models or len(self.metric_history.get(key, [])) >= self.window_size:
            if not self.train_model(key):
                return None
                
        model = self.models.get(key)
        scaler = self.scalers.get(key)
        
        if not model or not scaler:
            return None
            
        # Predict anomaly
        X = np.array([[metric.value]])
        X_scaled = scaler.transform(X)
        anomaly_score = model.decision_function(X_scaled)[0]
        is_anomaly = model.predict(X_scaled)[0] == -1
        
        if is_anomaly:
            # Calculate severity based on anomaly score
            severity = "low"
            if anomaly_score < -0.5:
                severity = "high"
            elif anomaly_score < -0.3:
                severity = "medium"
                
            # Generate anomaly
            anomaly_id = f"anom_{int(time.time())}_{hash(key) % 10000}"
            
            description = f"Anomalous {metric.metric_name}: {metric.value:.2f}"
            if metric.node_name:
                description += f" on node {metric.node_name}"
            if metric.namespace:
                description += f" in namespace {metric.namespace}"
                
            # Generate suggested actions
            suggested_actions = self._generate_suggested_actions(metric, severity)
            
            return Anomaly(
                id=anomaly_id,
                timestamp=metric.timestamp,
                metric_name=metric.metric_name,
                severity=severity,
                anomaly_score=anomaly_score,
                description=description,
                affected_resource=f"{metric.node_name or 'cluster'}:{metric.namespace or 'all'}",
                suggested_actions=suggested_actions,
                auto_remediation=severity in ["low", "medium"]
            )
            
        return None
        
    def _generate_suggested_actions(self, metric: MetricPoint, severity: str) -> List[str]:
        """Generate contextual suggested actions"""
        actions = []
        
        if "cpu" in metric.metric_name.lower():
            actions.extend([
                "Check CPU-intensive processes",
                "Consider horizontal pod autoscaling",
                "Review resource requests and limits"
            ])
            if severity == "high":
                actions.append("Consider immediate pod eviction or node scaling")
                
        elif "memory" in metric.metric_name.lower():
            actions.extend([
                "Check memory usage patterns",
                "Review memory limits and requests",
                "Look for memory leaks in applications"
            ])
            if severity == "high":
                actions.append("Consider immediate pod restart or OOM handling")
                
        elif "disk" in metric.metric_name.lower():
            actions.extend([
                "Clean up temporary files",
                "Review log rotation policies",
                "Check for large files or directories"
            ])
            
        elif "network" in metric.metric_name.lower():
            actions.extend([
                "Check network traffic patterns",
                "Review network policies",
                "Monitor for DDoS or unusual traffic"
            ])
            
        elif "pod_restart" in metric.metric_name:
            actions.extend([
                "Check pod logs for crash reasons",
                "Review health check configurations",
                "Investigate application stability"
            ])
            
        return actions

class PredictiveScaler:
    """Predictive autoscaling based on ML models"""
    
    def __init__(self):
        self.prediction_models = {}
        self.scaling_history = {}
        
    def predict_resource_needs(self, metrics: List[MetricPoint]) -> List[PredictionResult]:
        """Predict future resource needs"""
        predictions = []
        
        # Group metrics by type
        metric_groups = {}
        for metric in metrics:
            if metric.metric_name not in metric_groups:
                metric_groups[metric.metric_name] = []
            metric_groups[metric.metric_name].append(metric)
            
        for metric_name, metric_list in metric_groups.items():
            if len(metric_list) < 10:  # Need minimum data
                continue
                
            # Simple trend analysis (can be enhanced with more sophisticated ML)
            values = [m.value for m in sorted(metric_list, key=lambda x: x.timestamp)]
            
            if len(values) >= 3:
                # Calculate trend
                recent_avg = np.mean(values[-3:])
                older_avg = np.mean(values[:-3]) if len(values) > 3 else values[0]
                
                trend_direction = "stable"
                if recent_avg > older_avg * 1.1:
                    trend_direction = "increasing"
                elif recent_avg < older_avg * 0.9:
                    trend_direction = "decreasing"
                    
                # Predict next value (simple linear extrapolation)
                if len(values) >= 5:
                    x = np.arange(len(values))
                    y = np.array(values)
                    slope, intercept = np.polyfit(x, y, 1)
                    predicted_value = slope * len(values) + intercept
                else:
                    predicted_value = recent_avg
                    
                # Calculate confidence based on variance
                variance = np.var(values)
                confidence = max(0.1, min(1.0, 1.0 - (variance / (recent_avg + 0.001))))
                
                # Generate recommendation
                recommendation = self._generate_scaling_recommendation(
                    metric_name, values[-1], predicted_value, trend_direction, confidence
                )
                
                predictions.append(PredictionResult(
                    metric_name=metric_name,
                    current_value=values[-1],
                    predicted_value=predicted_value,
                    confidence=confidence,
                    trend=trend_direction,
                    recommendation=recommendation
                ))
                
        return predictions
        
    def _generate_scaling_recommendation(self, metric_name: str, current: float, 
                                       predicted: float, trend: str, confidence: float) -> str:
        """Generate scaling recommendations"""
        if confidence < 0.5:
            return "Insufficient data for reliable prediction"
            
        change_pct = ((predicted - current) / current) * 100 if current > 0 else 0
        
        if "cpu" in metric_name.lower() or "memory" in metric_name.lower():
            if trend == "increasing" and change_pct > 20:
                return f"Scale up recommended: {change_pct:.1f}% increase predicted"
            elif trend == "decreasing" and change_pct < -30:
                return f"Scale down possible: {abs(change_pct):.1f}% decrease predicted"
            else:
                return "Current scaling appears adequate"
                
        elif "pod_count" in metric_name:
            if trend == "increasing":
                return "Increased pod deployment may be needed"
            elif trend == "decreasing":
                return "Consider pod consolidation opportunities"
                
        return "Monitor trends, no immediate action required"

class SelfHealingEngine:
    """Automated remediation engine"""
    
    def __init__(self, k8s_client, apps_client):
        self.k8s_client = k8s_client
        self.apps_client = apps_client
        self.remediation_history = {}
        self.enabled_remediations = {
            "pod_restart": True,
            "pod_scaling": True,
            "resource_cleanup": True,
            "config_adjustment": False  # Disabled by default for safety
        }
        
    async def execute_remediation(self, anomaly: Anomaly) -> bool:
        """Execute automated remediation"""
        if not anomaly.auto_remediation:
            logger.info(f"Auto-remediation disabled for anomaly {anomaly.id}")
            return False
            
        # Track remediation attempts
        resource_key = anomaly.affected_resource
        now = datetime.now()
        
        if resource_key not in self.remediation_history:
            self.remediation_history[resource_key] = []
            
        # Check cooldown period (prevent too frequent remediations)
        recent_remediations = [
            r for r in self.remediation_history[resource_key] 
            if (now - r).total_seconds() < 1800  # 30 minutes
        ]
        
        if len(recent_remediations) >= 3:
            logger.warning(f"Too many recent remediations for {resource_key}, skipping")
            return False
            
        # Execute remediation based on anomaly type
        success = False
        
        if "pod_restart" in anomaly.metric_name and self.enabled_remediations["pod_restart"]:
            success = await self._restart_problematic_pods(anomaly)
            
        elif "cpu" in anomaly.metric_name or "memory" in anomaly.metric_name:
            if self.enabled_remediations["pod_scaling"]:
                success = await self._scale_resources(anomaly)
                
        elif "disk" in anomaly.metric_name and self.enabled_remediations["resource_cleanup"]:
            success = await self._cleanup_disk_space(anomaly)
            
        if success:
            self.remediation_history[resource_key].append(now)
            logger.info(f"Successfully executed remediation for anomaly {anomaly.id}")
        else:
            logger.warning(f"Failed to execute remediation for anomaly {anomaly.id}")
            
        return success
        
    async def _restart_problematic_pods(self, anomaly: Anomaly) -> bool:
        """Restart pods with high restart counts"""
        try:
            namespace = anomaly.affected_resource.split(':')[1]
            if namespace == "all":
                return False  # Too broad, skip
                
            # Find pods with high restart counts
            pods = self.k8s_client.list_namespaced_pod(namespace=namespace)
            
            for pod in pods.items:
                if pod.status.container_statuses:
                    total_restarts = sum(
                        container.restart_count for container in pod.status.container_statuses
                    )
                    
                    if total_restarts > 10:  # High restart count
                        logger.info(f"Restarting pod {pod.metadata.name} with {total_restarts} restarts")
                        self.k8s_client.delete_namespaced_pod(
                            name=pod.metadata.name,
                            namespace=namespace
                        )
                        
            return True
            
        except Exception as e:
            logger.error(f"Error restarting pods: {e}")
            return False
            
    async def _scale_resources(self, anomaly: Anomaly) -> bool:
        """Scale resources based on anomaly"""
        try:
            namespace = anomaly.affected_resource.split(':')[1]
            if namespace == "all":
                return False
                
            # Find deployments to scale
            deployments = self.apps_client.list_namespaced_deployment(namespace=namespace)
            
            for deployment in deployments.items:
                current_replicas = deployment.spec.replicas
                
                if anomaly.severity == "high" and current_replicas < 5:
                    # Scale up for high severity
                    new_replicas = min(current_replicas + 1, 5)
                    deployment.spec.replicas = new_replicas
                    
                    self.apps_client.patch_namespaced_deployment(
                        name=deployment.metadata.name,
                        namespace=namespace,
                        body=deployment
                    )
                    
                    logger.info(f"Scaled deployment {deployment.metadata.name} to {new_replicas} replicas")
                    
            return True
            
        except Exception as e:
            logger.error(f"Error scaling resources: {e}")
            return False
            
    async def _cleanup_disk_space(self, anomaly: Anomaly) -> bool:
        """Clean up disk space"""
        try:
            # Simple cleanup - remove old log files
            os.system("find /tmp -type f -mtime +7 -delete")
            os.system("find /var/log -name '*.log.*' -mtime +30 -delete")
            
            logger.info("Executed disk cleanup")
            return True
            
        except Exception as e:
            logger.error(f"Error cleaning disk space: {e}")
            return False

class ComplianceMonitor:
    """Monitor security and compliance status"""
    
    def __init__(self):
        self.compliance_rules = {
            "security_contexts": True,
            "network_policies": True,
            "rbac_enabled": True,
            "pod_security_standards": True,
            "resource_quotas": True
        }
        
    async def check_compliance(self) -> Dict[str, Any]:
        """Check compliance status"""
        results = {
            "overall_score": 0.0,
            "checks": {},
            "violations": [],
            "recommendations": []
        }
        
        try:
            k8s_client = client.CoreV1Api()
            apps_client = client.AppsV1Api()
            
            # Check security contexts
            violations = 0
            total_pods = 0
            
            pods = k8s_client.list_pod_for_all_namespaces()
            for pod in pods.items:
                total_pods += 1
                
                # Check if pod has security context
                if not pod.spec.security_context:
                    violations += 1
                    results["violations"].append(
                        f"Pod {pod.metadata.name} in {pod.metadata.namespace} has no security context"
                    )
                    
            security_score = max(0, (total_pods - violations) / total_pods) if total_pods > 0 else 1.0
            results["checks"]["security_contexts"] = {
                "score": security_score,
                "violations": violations,
                "total": total_pods
            }
            
            # Check for resource quotas
            namespaces = k8s_client.list_namespace()
            quota_violations = 0
            
            for namespace in namespaces.items:
                try:
                    quotas = k8s_client.list_namespaced_resource_quota(namespace.metadata.name)
                    if len(quotas.items) == 0:
                        quota_violations += 1
                        results["violations"].append(
                            f"Namespace {namespace.metadata.name} has no resource quotas"
                        )
                except:
                    pass
                    
            quota_score = max(0, (len(namespaces.items) - quota_violations) / len(namespaces.items))
            results["checks"]["resource_quotas"] = {
                "score": quota_score,
                "violations": quota_violations,
                "total": len(namespaces.items)
            }
            
            # Calculate overall score
            scores = [check["score"] for check in results["checks"].values()]
            results["overall_score"] = np.mean(scores) if scores else 0.0
            
            # Generate recommendations
            if security_score < 0.8:
                results["recommendations"].append(
                    "Implement security contexts for all pods"
                )
            if quota_score < 0.8:
                results["recommendations"].append(
                    "Implement resource quotas for all namespaces"
                )
                
        except Exception as e:
            logger.error(f"Error checking compliance: {e}")
            
        return results

class IntelligentMonitoringSystem:
    """Main monitoring system orchestrator"""
    
    def __init__(self, db_path: str = "/var/lib/cronnecture/monitoring.db"):
        self.db_path = db_path
        self.metrics_collector = MetricsCollector()
        self.anomaly_detector = AnomalyDetector()
        self.predictive_scaler = PredictiveScaler()
        self.compliance_monitor = ComplianceMonitor()
        
        # Initialize database
        self._init_database()
        
        # Initialize Kubernetes clients for self-healing
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
            self.self_healing = SelfHealingEngine(self.k8s_client, self.apps_client)
        except:
            self.self_healing = None
            logger.warning("Self-healing disabled - no Kubernetes access")
            
        self.running = False
        self.executor = ThreadPoolExecutor(max_workers=4)
        
    def _init_database(self):
        """Initialize SQLite database for metrics storage"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Metrics table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME,
                metric_name TEXT,
                value REAL,
                labels TEXT,
                node_name TEXT,
                namespace TEXT,
                pod_name TEXT
            )
        ''')
        
        # Anomalies table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS anomalies (
                id TEXT PRIMARY KEY,
                timestamp DATETIME,
                metric_name TEXT,
                severity TEXT,
                anomaly_score REAL,
                description TEXT,
                affected_resource TEXT,
                suggested_actions TEXT,
                auto_remediation BOOLEAN,
                resolved BOOLEAN DEFAULT FALSE
            )
        ''')
        
        # Predictions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME,
                metric_name TEXT,
                current_value REAL,
                predicted_value REAL,
                confidence REAL,
                trend TEXT,
                recommendation TEXT
            )
        ''')
        
        conn.commit()
        conn.close()
        
    def store_metric(self, metric: MetricPoint):
        """Store metric in database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO metrics 
            (timestamp, metric_name, value, labels, node_name, namespace, pod_name)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            metric.timestamp.isoformat(),
            metric.metric_name,
            metric.value,
            json.dumps(metric.labels),
            metric.node_name,
            metric.namespace,
            metric.pod_name
        ))
        
        conn.commit()
        conn.close()
        
    def store_anomaly(self, anomaly: Anomaly):
        """Store anomaly in database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO anomalies 
            (id, timestamp, metric_name, severity, anomaly_score, description, 
             affected_resource, suggested_actions, auto_remediation)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            anomaly.id,
            anomaly.timestamp.isoformat(),
            anomaly.metric_name,
            anomaly.severity,
            anomaly.anomaly_score,
            anomaly.description,
            anomaly.affected_resource,
            json.dumps(anomaly.suggested_actions),
            anomaly.auto_remediation
        ))
        
        conn.commit()
        conn.close()
        
    async def monitoring_cycle(self):
        """Execute one monitoring cycle"""
        logger.info("Starting monitoring cycle")
        
        # Collect metrics
        system_metrics = await self.metrics_collector.collect_system_metrics()
        k8s_metrics = await self.metrics_collector.collect_kubernetes_metrics()
        
        all_metrics = system_metrics + k8s_metrics
        logger.info(f"Collected {len(all_metrics)} metrics")
        
        # Store and process metrics
        anomalies_detected = []
        
        for metric in all_metrics:
            # Store metric
            self.store_metric(metric)
            
            # Add to anomaly detector
            self.anomaly_detector.add_metric_point(metric)
            
            # Check for anomalies
            anomaly = self.anomaly_detector.detect_anomaly(metric)
            if anomaly:
                anomalies_detected.append(anomaly)
                self.store_anomaly(anomaly)
                logger.warning(f"Anomaly detected: {anomaly.description}")
                
                # Execute auto-remediation if enabled
                if self.self_healing and anomaly.auto_remediation:
                    await self.self_healing.execute_remediation(anomaly)
                    
        # Generate predictions
        predictions = self.predictive_scaler.predict_resource_needs(all_metrics)
        for prediction in predictions:
            logger.info(f"Prediction: {prediction.metric_name} - {prediction.recommendation}")
            
        # Check compliance
        compliance_results = await self.compliance_monitor.check_compliance()
        logger.info(f"Compliance score: {compliance_results['overall_score']:.2f}")
        
        # Generate cycle summary
        cycle_summary = {
            "timestamp": datetime.now().isoformat(),
            "metrics_collected": len(all_metrics),
            "anomalies_detected": len(anomalies_detected),
            "predictions_generated": len(predictions),
            "compliance_score": compliance_results['overall_score'],
            "violations": len(compliance_results['violations'])
        }
        
        logger.info(f"Monitoring cycle completed: {cycle_summary}")
        return cycle_summary
        
    async def run_continuous_monitoring(self):
        """Run continuous monitoring loop"""
        self.running = True
        logger.info("Starting continuous monitoring...")
        
        cycle_count = 0
        
        while self.running:
            try:
                cycle_count += 1
                logger.info(f"=== Monitoring Cycle #{cycle_count} ===")
                
                # Execute monitoring cycle
                await self.monitoring_cycle()
                
                # Sleep between cycles (5 minutes)
                await asyncio.sleep(300)
                
            except KeyboardInterrupt:
                logger.info("Monitoring interrupted by user")
                break
            except Exception as e:
                logger.error(f"Error in monitoring cycle: {e}")
                await asyncio.sleep(60)  # Wait 1 minute on error
                
        self.running = False
        logger.info("Monitoring stopped")
        
    def stop_monitoring(self):
        """Stop monitoring gracefully"""
        self.running = False
        
def main():
    """Main entry point for intelligent monitoring"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Cronnecture Intelligent Monitoring System")
    parser.add_argument("--db-path", default="/var/lib/cronnecture/monitoring.db",
                       help="Database path for metrics storage")
    parser.add_argument("--cycle-interval", type=int, default=300,
                       help="Monitoring cycle interval in seconds")
    args = parser.parse_args()
    
    # Initialize monitoring system
    monitor = IntelligentMonitoringSystem(db_path=args.db_path)
    
    # Run monitoring
    try:
        asyncio.run(monitor.run_continuous_monitoring())
    except KeyboardInterrupt:
        logger.info("Monitoring system shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()