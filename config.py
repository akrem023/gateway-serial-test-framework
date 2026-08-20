#!/usr/bin/env python3
# config.py - Configuration settings

import os
from dataclasses import dataclass
from typing import List, Dict, Optional

@dataclass
class GatewayConfig:
    """Gateway connection configuration"""
    # Serial connection settings
    port: str = '/dev/ttyUSB0'
    baudrate: int = 115200
    timeout: int = 1
    
    # Login credentials
    username: str = 'root'
    password: str = 'sah'
    
    # Prompt patterns (for detecting shell)
    shell_prompts: List[str] = None
    
    # Command execution settings
    command_timeout: int = 5
    prompt_timeout: int = 3
    
    # Logging settings
    default_log_file: str = 'gateway_session.log'
    log_timestamp_format: str = '%Y%m%d_%H%M%S'
    
    def __post_init__(self):
        if self.shell_prompts is None:
            self.shell_prompts = ['# ', '$ ', '> ', ':/$ ', ':/# ']
    
    @classmethod
    def from_env(cls):
        """Create config from environment variables"""
        return cls(
            port=os.getenv('GTW_PORT', '/dev/ttyUSB0'),
            baudrate=int(os.getenv('GTW_BAUDRATE', '115200')),
            username=os.getenv('GTW_USERNAME', 'root'),
            password=os.getenv('GTW_PASSWORD', 'sah')
        )

# Default configuration
DEFAULT_CONFIG = GatewayConfig()

# Custom configurations (you can add more)
CONFIGURATIONS = {
    'default': DEFAULT_CONFIG,
    'livebox': GatewayConfig(
        port='/dev/ttyUSB0',
        baudrate=115200,
        username='root',
        password='sah'
    ),
    'fast': GatewayConfig(
        timeout=0.5,
        command_timeout=2,
        prompt_timeout=1
    ),
    'debug': GatewayConfig(
        port='/dev/ttyUSB0',
        timeout=2,
        command_timeout=10,
        prompt_timeout=5
    )
}

def get_config(config_name='default'):
    """Get configuration by name"""
    return CONFIGURATIONS.get(config_name, DEFAULT_CONFIG)