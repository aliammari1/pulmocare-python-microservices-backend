import consul
import logging
import socket
import os
import uuid
import sys
from services.base_consul_service import BaseConsulService

logger = logging.getLogger(__name__)

class ConsulService(BaseConsulService):
    """Reports service Consul integration"""
    pass  # Inherits all functionality from BaseConsulService
