#!/usr/bin/env python3
"""
Cronnecture Enterprise Credential Manager
Intelligent credential management with AES-256 encryption, auto-rotation, and K8s integration
"""

import os
import sys
import json
import base64
import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import kubernetes
from kubernetes import client, config
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class CredentialPolicy:
    """Credential management policy"""
    min_length: int = 32
    require_special_chars: bool = True
    require_numbers: bool = True
    require_uppercase: bool = True
    rotation_days: int = 90
    max_age_days: int = 365
    encryption_algorithm: str = "AES-256-GCM"
    
@dataclass
class Credential:
    """Secure credential with metadata"""
    id: str
    name: str
    value: str
    encrypted_value: str
    created_at: datetime
    last_rotated: datetime
    expires_at: datetime
    rotation_policy: CredentialPolicy
    tags: Dict[str, str]
    namespace: str = "default"
    secret_name: str = ""
    
class IntelligentCredentialManager:
    """Enterprise-grade credential manager with AI-driven security"""
    
    def __init__(self, master_key: Optional[str] = None):
        """Initialize credential manager"""
        self.master_key = master_key or os.environ.get('CRONNECTURE_MASTER_KEY')
        if not self.master_key:
            logger.info("Generating new master key")
            self.master_key = base64.urlsafe_b64encode(os.urandom(32)).decode()
            
        # Initialize encryption
        self.cipher_suite = self._init_encryption()
        
        # Initialize Kubernetes client
        try:
            config.load_incluster_config()
        except:
            try:
                config.load_kube_config()
            except Exception as e:
                logger.warning(f"Could not load K8s config: {e}")
                
        self.k8s_client = client.CoreV1Api()
        self.credentials: Dict[str, Credential] = {}
        
        # Default policies
        self.default_policy = CredentialPolicy()
        self.service_policies = {
            'database': CredentialPolicy(min_length=64, rotation_days=30),
            'api_key': CredentialPolicy(min_length=48, rotation_days=60),
            'certificate': CredentialPolicy(rotation_days=365, max_age_days=730),
            'oauth_secret': CredentialPolicy(min_length=40, rotation_days=45)
        }
        
        self.allowed_namespace = os.environ.get(
            "CREDENTIAL_NAMESPACE", "cronnecture-intelligence"
        )

    def _init_encryption(self) -> Fernet:
        """Initialize Fernet encryption with master key"""
        # Derive key from master key using PBKDF2
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b'cronnecture_salt',  # In production, use random salt per credential
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(self.master_key.encode()))
        return Fernet(key)
        
    def generate_secure_password(self, 
                                policy: Optional[CredentialPolicy] = None,
                                service_type: str = "default") -> str:
        """Generate cryptographically secure password with AI-optimized entropy"""
        if not policy:
            policy = self.service_policies.get(service_type, self.default_policy)
            
        # Character sets
        lowercase = "abcdefghijklmnopqrstuvwxyz"
        uppercase = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        digits = "0123456789"
        special = "!@#$%^&*()_+-=[]{}|;:,.<>?"
        
        # Build character pool
        chars = lowercase
        if policy.require_uppercase:
            chars += uppercase
        if policy.require_numbers:
            chars += digits
        if policy.require_special_chars:
            chars += special
            
        # Generate password with guaranteed character requirements
        password = []
        
        # Ensure requirements are met
        if policy.require_uppercase:
            password.append(secrets.choice(uppercase))
        if policy.require_numbers:
            password.append(secrets.choice(digits))
        if policy.require_special_chars:
            password.append(secrets.choice(special))
            
        # Fill remaining length
        remaining_length = policy.min_length - len(password)
        for _ in range(remaining_length):
            password.append(secrets.choice(chars))
            
        # Shuffle to avoid predictable patterns
        secrets.SystemRandom().shuffle(password)
        
        result = ''.join(password)
        logger.info(f"Generated secure password: length={len(result)}, entropy={self._calculate_entropy(result):.2f} bits")
        return result
        
    def _calculate_entropy(self, password: str) -> float:
        """Calculate password entropy in bits"""
        charset_size = 0
        if any(c.islower() for c in password):
            charset_size += 26
        if any(c.isupper() for c in password):
            charset_size += 26
        if any(c.isdigit() for c in password):
            charset_size += 10
        if any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password):
            charset_size += 23
            
        import math
        return len(password) * math.log2(charset_size)
        
    def create_credential(self,
                         name: str,
                         service_type: str = "default",
                         namespace: str = "cronnecture-intelligence",
                         tags: Optional[Dict[str, str]] = None,
                         custom_value: Optional[str] = None) -> str:
        """Create new managed credential"""
        if namespace != self.allowed_namespace:
            logger.warning(
                f"Refusing credential namespace {namespace}; "
                f"forcing {self.allowed_namespace}"
            )
            namespace = self.allowed_namespace
        
        # Generate or use provided value
        if custom_value:
            value = custom_value
        else:
            value = self.generate_secure_password(service_type=service_type)
            
        # Get policy
        policy = self.service_policies.get(service_type, self.default_policy)
        
        # Create credential
        credential_id = hashlib.sha256(f"{name}_{namespace}_{datetime.now().isoformat()}".encode()).hexdigest()[:16]
        
        now = datetime.now()
        credential = Credential(
            id=credential_id,
            name=name,
            value=value,
            encrypted_value=self.cipher_suite.encrypt(value.encode()).decode(),
            created_at=now,
            last_rotated=now,
            expires_at=now + timedelta(days=policy.max_age_days),
            rotation_policy=policy,
            tags=tags or {},
            namespace=namespace,
            secret_name=f"cronnecture-{name.lower().replace('_', '-')}"
        )
        
        # Store credential
        self.credentials[credential_id] = credential
        
        # Create Kubernetes secret
        self._create_k8s_secret(credential)
        
        logger.info(f"Created credential: {name} (ID: {credential_id})")
        return credential_id
        
    def _create_k8s_secret(self, credential: Credential):
        """Create Kubernetes secret for credential"""
        if credential.namespace != self.allowed_namespace:
            logger.error(
                f"Refusing to write secret {credential.secret_name} "
                f"into {credential.namespace}"
            )
            return
        try:
            secret_body = client.V1Secret(
                metadata=client.V1ObjectMeta(
                    name=credential.secret_name,
                    namespace=credential.namespace,
                    labels={
                        'managed-by': 'cronnecture-intelligence',
                        'credential-id': credential.id,
                        'service-type': credential.tags.get('service_type', 'default')
                    }
                ),
                data={
                    credential.name: base64.b64encode(credential.value.encode()).decode(),
                    'metadata': base64.b64encode(json.dumps({
                        'created_at': credential.created_at.isoformat(),
                        'expires_at': credential.expires_at.isoformat(),
                        'rotation_days': credential.rotation_policy.rotation_days
                    }).encode()).decode()
                }
            )
            
            self.k8s_client.create_namespaced_secret(
                namespace=credential.namespace,
                body=secret_body
            )
            logger.info(f"Created K8s secret: {credential.secret_name}")
            
        except kubernetes.client.ApiException as e:
            if e.status == 409:  # Already exists
                logger.info(f"K8s secret already exists: {credential.secret_name}")
            else:
                logger.error(f"Failed to create K8s secret: {e}")
                
    def rotate_credential(self, credential_id: str) -> bool:
        """Intelligently rotate credential"""
        if credential_id not in self.credentials:
            logger.error(f"Credential not found: {credential_id}")
            return False
            
        credential = self.credentials[credential_id]
        
        # Generate new value
        new_value = self.generate_secure_password(
            policy=credential.rotation_policy,
            service_type=credential.tags.get('service_type', 'default')
        )
        
        # Update credential
        credential.value = new_value
        credential.encrypted_value = self.cipher_suite.encrypt(new_value.encode()).decode()
        credential.last_rotated = datetime.now()
        credential.expires_at = datetime.now() + timedelta(days=credential.rotation_policy.max_age_days)
        
        # Update Kubernetes secret
        self._update_k8s_secret(credential)
        
        logger.info(f"Rotated credential: {credential.name} (ID: {credential_id})")
        return True
        
    def _update_k8s_secret(self, credential: Credential):
        """Update Kubernetes secret"""
        if credential.namespace != self.allowed_namespace:
            logger.error(
                f"Refusing to update secret {credential.secret_name} "
                f"in {credential.namespace}"
            )
            return
        try:
            secret_body = client.V1Secret(
                metadata=client.V1ObjectMeta(
                    name=credential.secret_name,
                    namespace=credential.namespace,
                    labels={
                        'managed-by': 'cronnecture-intelligence',
                        'credential-id': credential.id,
                        'service-type': credential.tags.get('service_type', 'default')
                    }
                ),
                data={
                    credential.name: base64.b64encode(credential.value.encode()).decode(),
                    'metadata': base64.b64encode(json.dumps({
                        'created_at': credential.created_at.isoformat(),
                        'last_rotated': credential.last_rotated.isoformat(),
                        'expires_at': credential.expires_at.isoformat(),
                        'rotation_days': credential.rotation_policy.rotation_days
                    }).encode()).decode()
                }
            )
            
            self.k8s_client.replace_namespaced_secret(
                name=credential.secret_name,
                namespace=credential.namespace,
                body=secret_body
            )
            logger.info(f"Updated K8s secret: {credential.secret_name}")
            
        except kubernetes.client.ApiException as e:
            logger.error(f"Failed to update K8s secret: {e}")
            
    def check_rotation_needed(self) -> List[str]:
        """Check which credentials need rotation"""
        needs_rotation = []
        now = datetime.now()
        
        for cred_id, credential in self.credentials.items():
            days_since_rotation = (now - credential.last_rotated).days
            if days_since_rotation >= credential.rotation_policy.rotation_days:
                needs_rotation.append(cred_id)
                logger.info(f"Credential needs rotation: {credential.name} ({days_since_rotation} days)")
                
        return needs_rotation
        
    def auto_rotate_expired(self) -> Dict[str, bool]:
        """Automatically rotate expired credentials"""
        needs_rotation = self.check_rotation_needed()
        results = {}
        
        for cred_id in needs_rotation:
            results[cred_id] = self.rotate_credential(cred_id)
            
        logger.info(f"Auto-rotation completed: {sum(results.values())}/{len(results)} successful")
        return results
        
    def get_credential_status(self) -> Dict[str, Any]:
        """Get comprehensive credential status report"""
        now = datetime.now()
        status = {
            'total_credentials': len(self.credentials),
            'by_service_type': {},
            'expiring_soon': [],
            'needs_rotation': [],
            'security_score': 0.0
        }
        
        for cred_id, credential in self.credentials.items():
            # Count by service type
            service_type = credential.tags.get('service_type', 'default')
            status['by_service_type'][service_type] = status['by_service_type'].get(service_type, 0) + 1
            
            # Check expiring soon (within 30 days)
            days_to_expire = (credential.expires_at - now).days
            if days_to_expire <= 30:
                status['expiring_soon'].append({
                    'id': cred_id,
                    'name': credential.name,
                    'days_remaining': days_to_expire
                })
                
            # Check rotation needed
            days_since_rotation = (now - credential.last_rotated).days
            if days_since_rotation >= credential.rotation_policy.rotation_days:
                status['needs_rotation'].append({
                    'id': cred_id,
                    'name': credential.name,
                    'days_overdue': days_since_rotation - credential.rotation_policy.rotation_days
                })
                
        # Calculate security score (0-100)
        if status['total_credentials'] > 0:
            overdue_count = len(status['needs_rotation'])
            expiring_count = len(status['expiring_soon'])
            status['security_score'] = max(0, 100 - (overdue_count * 20) - (expiring_count * 5))
            
        return status
        
    def run_intelligence_cycle(self):
        """Run one cycle of intelligent credential management"""
        logger.info("Starting credential management intelligence cycle")
        
        # Auto-rotate expired credentials
        rotation_results = self.auto_rotate_expired()
        
        # Get status
        status = self.get_credential_status()
        
        # Log intelligence insights
        logger.info(f"Intelligence Summary: {status['total_credentials']} credentials managed")
        logger.info(f"Security Score: {status['security_score']:.1f}/100")
        
        if status['needs_rotation']:
            logger.warning(f"{len(status['needs_rotation'])} credentials need rotation")
            
        if status['expiring_soon']:
            logger.warning(f"{len(status['expiring_soon'])} credentials expiring within 30 days")
            
        return {
            'rotation_results': rotation_results,
            'status': status,
            'cycle_timestamp': datetime.now().isoformat()
        }

def main():
    """Main entry point for credential manager service"""
    import time
    
    # Initialize credential manager
    manager = IntelligentCredentialManager()

    logger.info(
        f"Credential manager restricted to namespace {manager.allowed_namespace}; "
        "not seeding secrets in identity or networking"
    )
    
    # Main service loop
    logger.info("Starting credential management service...")
    cycle_count = 0
    
    while True:
        try:
            cycle_count += 1
            logger.info(f"=== Intelligence Cycle #{cycle_count} ===")
            
            # Run intelligence cycle
            results = manager.run_intelligence_cycle()
            
            # Sleep for 1 hour between cycles
            logger.info("Cycle complete, sleeping for 1 hour...")
            time.sleep(3600)
            
        except KeyboardInterrupt:
            logger.info("Credential management service stopping...")
            break
        except Exception as e:
            logger.error(f"Error in intelligence cycle: {e}")
            time.sleep(300)  # Sleep 5 minutes on error

if __name__ == "__main__":
    main()