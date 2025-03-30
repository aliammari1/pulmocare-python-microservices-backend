import os
import socket
import sys
import uuid

import consul
from services.base_consul_service import BaseConsulService
from services.logger_service import logger_service


class ConsulService(BaseConsulService):
    """Reports service Consul integration"""

    pass  # Inherits all functionality from BaseConsulService
