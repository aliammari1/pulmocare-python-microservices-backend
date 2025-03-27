import logging
import os
import socket
import sys
import uuid

import consul
from services.base_consul_service import BaseConsulService

logger = logging.getLogger(__name__)


class ConsulService(BaseConsulService):
    """Reports service Consul integration"""

    pass  # Inherits all functionality from BaseConsulService
