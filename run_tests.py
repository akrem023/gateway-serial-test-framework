#!/usr/bin/env python3
# run_tests.py - Test runner script

import argparse
import json
from datetime import datetime
from gtw_serial import GatewaySerialConnector
from config import get_config
from tests import list_test_suites, get_test_suite_details

def run_test_suite(suite_name, config_name='default', log_file=None):
    """Run a test suite and return results"""
    config = get_config(config_name)
    connector = GatewaySerialConnector(config)
    
    try:
        if not connector.connect():
            return None
        
        if log_file:
            connector.open_log(log_file)
        
        connector.login()
        
        results = connector.run_tests(suite_name)
        
        return results
        
    finally:
        connector.disconnect()

def main():
    parser = argparse.ArgumentParser(description='Gateway Test Runner')
    parser.add_argument('suite', help='Test suite to run')
    parser.add_argument('--config', default='default', help='Configuration profile')
    parser.add_argument('--output', help='Output log file')
    parser.add_argument('--json', action='store_true', help='Output results as JSON')
    parser.add_argument('--list', action='store_true', help='List available test suites')
    
    args = parser.parse_args()
    
    if args.list:
        print("Available test suites:")
        for name in list_test_suites():
            print(f"  - {name}")
        return
    
    results = run_test_suite(args.suite, args.config, args.output)
    
    if results and args.json:
        print(json.dumps(results, indent=2))
    
    if results:
        exit(0 if results.get('success', False) else 1)
    else:
        exit(1)

if __name__ == "__main__":
    main()