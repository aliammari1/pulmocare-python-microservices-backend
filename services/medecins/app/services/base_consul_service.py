import logging
import os
import socket
import uuid
from typing import Optional

import consul
import requests

logger = logging.getLogger(__name__)


class BaseConsulService:
    """Base class for Consul service registration and discovery"""

    def __init__(self, config):
        self.config = config
        self.service_id = f"{config.SERVICE_NAME}-{uuid.uuid4()}"
        self.consul = consul.Consul(
            host=config.CONSUL_HOST,
            port=config.CONSUL_PORT,
            token=getattr(config, "CONSUL_TOKEN", None),
            scheme="http",
        )

    def register_service(self) -> bool:
        """Register service with Consul with improved error handling and metadata"""
        try:
            # Get hostname and container IP
            hostname = os.getenv("HOSTNAME", socket.gethostname())
            container_ip = self._get_container_ip()

            # Enhanced service registration
            self.consul.agent.service.register(
                name=self.config.SERVICE_NAME,
                service_id=self.service_id,
                address=container_ip,
                port=self.config.PORT,
                tags=[
                    self.config.SERVICE_NAME.split("-")[0],
                    "medical",
                    "api",
                    f"version-{self.config.VERSION}",
                ],
                check={
                    "name": f"Health check for {self.config.SERVICE_NAME}",
                    "http": f"http://{container_ip}:{self.config.PORT}/health",
                    "method": "GET",
                    "interval": self.config.HEALTH_CHECK_INTERVAL,
                    "timeout": self.config.HEALTH_CHECK_TIMEOUT,
                    "deregister_critical_service_after": self.config.HEALTH_CHECK_DEREGISTER_TIMEOUT,
                },
            )

            logger.info(
                f"Successfully registered {self.config.SERVICE_NAME} with Consul"
            )
            return True

        except Exception as e:
            if (
                hasattr(self.config, "REGISTRY_IGNORE_ERRORS")
                and self.config.ENV == "development"
                and self.config.REGISTRY_IGNORE_ERRORS
            ):
                logger.warning(
                    f"Failed to register with Consul (ignored in dev mode): {str(e)}"
                )
                return False
            logger.error(f"Failed to register service with Consul: {str(e)}")
            raise

    def deregister_service(self) -> bool:
        """Deregister service from Consul"""
        try:
            self.consul.agent.service.deregister(self.service_id)
            logger.info(f"Deregistered service {self.service_id} from Consul")
            return True
        except Exception as e:
            logger.error(f"Failed to deregister service: {str(e)}")
            raise

    def _get_container_ip(self) -> str:
        """Get container IP with fallback options"""
        try:
            # Try getting the container IP first
            hostname = os.getenv("HOSTNAME", socket.gethostname())
            container_ip = socket.gethostbyname(hostname)

            # For development on Windows, get the actual network interface IP
            if self.config.ENV == "development" and container_ip == "127.0.0.1":
                container_ip = self._get_local_ip()

            return container_ip
        except:
            # Fallback to localhost for development
            return "127.0.0.1"

    def _get_local_ip(self) -> str:
        """Get a non-loopback IP address for the local machine"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.connect(("8.8.8.8", 80))
            local_ip = sock.getsockname()[0]
            sock.close()
            return local_ip
        except:
            return "127.0.0.1"
