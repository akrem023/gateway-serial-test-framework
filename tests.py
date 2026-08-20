#!/usr/bin/env python3
# tests.py - Test definitions with result saving to directory

from dataclasses import dataclass
from typing import List, Dict, Callable, Optional, Any
import time
import re
import json
import os
from datetime import datetime

# ======================= CONFIGURATION =======================

# Directory where test results will be saved
TEST_RESULTS_DIR = "test_results"

# Create directory if it doesn't exist
if not os.path.exists(TEST_RESULTS_DIR):
    os.makedirs(TEST_RESULTS_DIR)

# ======================= CORE CLASSES =======================

@dataclass
class TestCase:
    """Single test case definition"""
    name: str
    command: str
    description: str = ""
    summary: str = ""
    expected_output: Optional[str] = None
    timeout: int = 3
    validate_func: Optional[Callable[[str], bool]] = None
    wait_before: int = 0
    wait_after: int = 0
    result_filter: Optional[Callable[[str], Dict]] = None  # Function to filter/extract results
    
    def validate(self, output: str) -> bool:
        """Validate test output"""
        if self.validate_func:
            return self.validate_func(output)
        
        if self.expected_output:
            return self.expected_output in output
        
        # If no validation specified, assume success if we got output
        return bool(output.strip())
    
    def save_result_to_file(self, output: str, filtered_result: Optional[Dict] = None):
        """Save test result to file in test_results directory"""
        try:
            # Create a safe filename from test name
            safe_name = re.sub(r'[^\w\-_]', '_', self.name)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(TEST_RESULTS_DIR, f"{safe_name}_{timestamp}.txt")
            
            with open(filename, 'w') as f:
                f.write(f"{'='*60}\n")
                f.write(f"Test: {self.name}\n")
                f.write(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Command: {self.command}\n")
                f.write(f"Description: {self.description}\n")
                f.write(f"Summary: {self.summary}\n")
                f.write(f"{'='*60}\n\n")
                
                if filtered_result:
                    f.write("Filtered Results:\n")
                    f.write("-" * 40 + "\n")
                    for key, value in filtered_result.items():
                        if key not in ['AllParams', 'timestamp']:
                            f.write(f"{key}: {value}\n")
                    f.write("\n")
                
                f.write("Full Output:\n")
                f.write("-" * 40 + "\n")
                f.write(output)
                f.write(f"\n{'='*60}\n")
            
            print(f"    [+] Result saved to: {filename}")
            return filename
        except Exception as e:
            print(f"    [!] Error saving result: {e}")
            return None

@dataclass
class TestSuite:
    """Collection of test cases"""
    name: str
    description: str = ""
    tests: List[TestCase] = None
    setup_commands: List[str] = None
    teardown_commands: List[str] = None
    
    def __post_init__(self):
        if self.tests is None:
            self.tests = []
        if self.setup_commands is None:
            self.setup_commands = []
        if self.teardown_commands is None:
            self.teardown_commands = []

# ======================= HELPER FUNCTIONS =======================

def extract_value_from_output(output: str, pattern: str) -> str:
    """Extract value from output using regex pattern"""
    match = re.search(pattern, output)
    if match:
        return match.group(1)
    return ""

def parse_wan_status(output: str) -> Dict[str, str]:
    """Parse NMC.getWANStatus() output and extract key values"""
    result = {}
    
    # Extract the WAN status parameters from the output
    match = re.search(r'NMC\.getWANStatus\((.*?)\) returns', output, re.DOTALL)
    if match:
        params_str = match.group(1)
        
        # Parse key=value pairs
        params = {}
        for pair in params_str.split(', '):
            if '=' in pair:
                key, value = pair.split('=', 1)
                params[key] = value
        
        result = params
    
    return result

def check_wan_and_link_state(output: str) -> Dict[str, Any]:
    """Check if WanState and LinkState are both 'up'"""
    params = parse_wan_status(output)
    
    wan_state = params.get('WanState', 'unknown')
    link_state = params.get('LinkState', 'unknown')
    
    is_both_up = (wan_state.lower() == 'up' and link_state.lower() == 'up')
    
    return {
        "WanState": wan_state,
        "LinkState": link_state,
        "BothUp": is_both_up,
        "AllParams": params,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }

# ======================= BASIC SYSTEM TESTS =======================

# Individual test cases
TEST_UPTIME = TestCase(
    name="system_uptime",
    command="uptime",
    description="Check system uptime and load average",
    expected_output="up",
    timeout=3
)

TEST_VERSION = TestCase(
    name="system_version",
    command="cat /etc/version",
    description="Get system version",
    expected_output="06",
    timeout=3
)

TEST_DATE = TestCase(
    name="system_date",
    command="date",
    description="Get current date and time",
    expected_output="202",
    timeout=3
)

TEST_MEMORY = TestCase(
    name="memory_usage",
    command="free -m",
    description="Check memory usage",
    expected_output="Mem:",
    timeout=3
)

TEST_DISK = TestCase(
    name="disk_usage",
    command="df -h",
    description="Check disk usage",
    expected_output="/dev/",
    timeout=3
)

TEST_CPU = TestCase(
    name="cpu_info",
    command="cat /proc/cpuinfo | grep 'model name' | head -1",
    description="Get CPU information",
    timeout=3
)

TEST_NETWORK = TestCase(
    name="network_interfaces",
    command="ifconfig -a",
    description="List network interfaces",
    expected_output="eth",
    timeout=3
)

TEST_PROCESSES = TestCase(
    name="running_processes",
    command="ps aux | wc -l",
    description="Count running processes",
    timeout=3
)

def validate_kernel_version(output):
    """Custom validator for kernel version"""
    return "Linux" in output and "LIVEBOX" in output

TEST_KERNEL = TestCase(
    name="kernel_info",
    command="uname -a",
    description="Get kernel information",
    validate_func=validate_kernel_version,
    timeout=3
)

# ======================= WAN STATUS TESTS =======================

TEST_WAN_STATUS = TestCase(
    name="wan_status_check",
    command="pcb_cli 'NMC.getWANStatus()'",
    description="Get WAN connection status via pcb_cli",
    timeout=5,
    result_filter=check_wan_and_link_state
)

def enhanced_wan_check(output: str) -> Dict[str, Any]:
    """Enhanced WAN status check with more details"""
    params = parse_wan_status(output)
    
    wan_state = params.get('WanState', 'unknown')
    link_state = params.get('LinkState', 'unknown')
    link_type = params.get('LinkType', 'unknown')
    ip_address = params.get('IPAddress', 'unknown')
    connection_state = params.get('ConnectionState', 'unknown')
    
    is_both_up = (wan_state.lower() == 'up' and link_state.lower() == 'up')
    is_connected = connection_state.lower() == 'bound'
    
    status = "HEALTHY" if (is_both_up and is_connected) else "ISSUE"
    
    return {
        "status": status,
        "WanState": wan_state,
        "LinkState": link_state,
        "LinkType": link_type,
        "IPAddress": ip_address,
        "ConnectionState": connection_state,
        "BothUp": is_both_up,
        "Connected": is_connected,
        "AllParams": params,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }

ENHANCED_WAN_TEST = TestCase(
    name="enhanced_wan_status",
    command="pcb_cli 'NMC.getWANStatus()'",
    description="Enhanced WAN status check with detailed analysis",
    timeout=5,
    result_filter=enhanced_wan_check
)

# ======================= DSLITE ELIGIBILITY TESTS =======================

def dslite_value_filter(output: str) -> Dict[str, Any]:
    """Filter for DSLITE value check"""
    return {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "DSLITE_Value": output.strip(),
        "Is_0x0000": "0x0000" in output.strip(),
        "Status": "PASS" if "0x0000" in output.strip() else "FAIL"
    }

TEST_DSLITE_VALUE = TestCase(
    name="dslite_value_check",
    command="pcb_cli 'NMC.ServiceEligibility.DSLITE.Value?'",
    description="Check DSLITE eligibility value (should be 0x0000)",
    timeout=5,
    result_filter=dslite_value_filter
)

def option_125_filter(output: str) -> Dict[str, Any]:
    """Filter for Option 125 check"""
    expected = "000005580c020a000000ffffffffffffff"
    is_expected = expected in output.strip()
    return {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "Option_125_Value": output.strip(),
        "Expected_Value": expected,
        "Is_Expected": is_expected,
        "Status": "PASS" if is_expected else "FAIL"
    }

TEST_OPTION_125 = TestCase(
    name="option_125_check",
    command="pcb_cli 'NMC.ServiceEligibility.DSLITE.CgnOption.SentOption.125.Value?'",
    description="Check Option 125 value",
    timeout=5,
    result_filter=option_125_filter
)

def option_17_filter(output: str) -> Dict[str, Any]:
    """Filter for Option 17 check"""
    expected = "000005580002000a000000ffffffffffffff"
    is_expected = expected in output.strip()
    return {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "Option_17_Value": output.strip(),
        "Expected_Value": expected,
        "Is_Expected": is_expected,
        "Status": "PASS" if is_expected else "FAIL"
    }

TEST_OPTION_17 = TestCase(
    name="option_17_check",
    command="pcb_cli 'NMC.ServiceEligibility.DSLITE.CgnOption.SentOption.17.Value?'",
    description="Check Option 17 value",
    timeout=5,
    result_filter=option_17_filter
)

# ======================= PCB_CLI CONFIGURATION TESTS =======================

WAN_SET_USERNAME = TestCase(
    name="pcb_set_username",
    command="pcb_cli 'NMC.Username=softathome'",
    description="Set NMC username via pcb_cli",
    timeout=5
)

WAN_SET_PASSWORD = TestCase(
    name="pcb_set_password",
    command="pcb_cli 'NMC.Password=softathome'",
    description="Set NMC password via pcb_cli",
    timeout=5
)

WAN_SET_ADMIN_PASS = TestCase(
    name="pcb_set_admin_password",
    command="pcb_cli 'UserManagement.User.admin.Password=1234'",
    description="Set admin password via pcb_cli",
    timeout=5
)

WAN_SET_STATE = TestCase(
    name="pcb_set_connection_state",
    command="pcb_cli 'UserInterface.CurrentState=connected'",
    description="Set connection state via pcb_cli",
    timeout=5
)

# ======================= CGN TRACE TESTS =======================

TRACE_SET_NMC_CLIENT = TestCase(
    name="pcb_set_nmc_client_traces",
    command="pcb_cli 'Process.sysbus_nmc_client.Tracing.TraceLevel=500'",
    description="Set NMC client trace level via pcb_cli",
    timeout=1
)

TRACE_ADD_TRACE_ZONE = TestCase(
    name="pcb_add_trace_zone",
    command="pcb_cli 'Process.sysbus_nmc_client.addTraceZone(cgn,500)'",
    description="Set NMC client add trace zone via pcb_cli",
    timeout=1
)

PROCESS_SAVE = TestCase(
    name="pcb_process_save",
    command="pcb_cli 'Process.save()'",
    description="Save process configuration via pcb_cli",
    timeout=1
)

# ======================= RESET AND REBOOT TESTS =======================

RESET_HARD = TestCase(
    name="pcb_reset_hard",
    command="reset_hard",
    description="Perform hard reset on gateway",
    timeout=30,  # Increased timeout for reset command
    wait_after=5  # Wait after reset
)

REBOOT = TestCase(
    name="reboot_gateway",
    command="reboot",
    description="Reboot the gateway",
    timeout=30,  # Increased timeout for reboot
    wait_after=5  # Wait after reboot
)

# Warning test that runs first
RESET_WARNING = TestCase(
    name="reset_warning",
    command="echo 'WARNING: About to perform hard reset/reboot!'",
    description="Warning before reset/reboot",
    timeout=3
)

# ======================= REBOOT WITH MONITORING TESTS =======================

def reboot_with_monitor_filter(output: str) -> Dict[str, Any]:
    """Monitor reboot progress and detect completion"""
    result = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "boot_stage": "unknown",
        "sysinit_done": False,
        "boot_complete": False,
        "messages": []
    }
    
    # Check for boot stages
    if "reboot: Restarting system" in output or "Restarting system" in output:
        result["boot_stage"] = "reboot_initiated"
        result["messages"].append("Reboot initiated")
    
    if "Starting kernel" in output or "Uncompressing Linux" in output:
        result["boot_stage"] = "kernel_starting"
        result["messages"].append("Kernel starting")
    
    if "LIVEBOX login:" in output:
        result["boot_stage"] = "login_prompt"
        result["messages"].append("Login prompt ready")
    
    if "Sysinit done" in output:
        result["boot_stage"] = "sysinit_done"
        result["sysinit_done"] = True
        result["messages"].append("Sysinit completed")
    
    # Check for shell prompt (system fully booted)
    if "/cfg/system/root #" in output or "# " in output[-10:]:
        result["boot_stage"] = "shell_ready"
        result["boot_complete"] = True
        result["messages"].append("Shell ready")
    
    return result

REBOOT_WITH_MONITOR = TestCase(
    name="reboot_with_monitoring",
    command="""
    echo "=== Starting monitored reboot sequence ==="
    echo "1. Recording pre-reboot state..."
    date
    uptime
    echo ""
    echo "2. Initiating reboot..."
    reboot
    """,
    description="Reboot with boot progress monitoring",
    timeout=180,  # 3 minutes timeout for full reboot cycle
    result_filter=reboot_with_monitor_filter
)

def complete_reboot_cycle_filter(output: str) -> Dict[str, Any]:
    """Complete reboot cycle monitoring"""
    stages = []
    
    # Track all boot stages
    if "reboot: Restarting system" in output:
        stages.append({"stage": "reboot_initiated", "time": time.time()})
    
    if "Starting kernel" in output:
        stages.append({"stage": "kernel_start", "time": time.time()})
    
    if "LIVEBOX login:" in output:
        stages.append({"stage": "login_prompt", "time": time.time()})
    
    if "Sysinit done" in output:
        stages.append({"stage": "sysinit_done", "time": time.time()})
    
    # Calculate time between stages if we have multiple
    boot_time = None
    if len(stages) >= 2:
        first_stage = stages[0]["time"]
        last_stage = stages[-1]["time"]
        boot_time = last_stage - first_stage
    
    return {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "stages": stages,
        "boot_time_seconds": boot_time,
        "sysinit_detected": any(s["stage"] == "sysinit_done" for s in stages),
        "login_ready": any(s["stage"] == "login_prompt" for s in stages)
    }

COMPLETE_REBOOT_CYCLE = TestCase(
    name="complete_reboot_cycle",
    command="""
    echo "=== COMPLETE REBOOT CYCLE TEST ==="
    echo "Pre-reboot checks:"
    echo "1. Current time:" && date
    echo "2. Uptime:" && uptime
    echo "3. System version:" && cat /etc/version
    echo ""
    echo "=== INITIATING REBOOT ==="
    reboot
    echo "Reboot command sent. Monitoring boot process..."
    """,
    description="Complete reboot cycle with full monitoring",
    timeout=240,  # 4 minutes for complete cycle
    result_filter=complete_reboot_cycle_filter
)

def smart_reboot_sequence_filter(output: str) -> Dict[str, Any]:
    """Filter for smart reboot sequence"""
    return {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "reboot_initiated": "reboot: Restarting system" in output,
        "kernel_started": any(x in output for x in ["Starting kernel", "Uncompressing Linux"]),
        "sysinit_completed": "Sysinit done" in output,
        "login_available": "LIVEBOX login:" in output,
        "shell_ready": "/cfg/system/root #" in output,
        "boot_progress": "complete" if "/cfg/system/root #" in output else "in_progress"
    }

SMART_REBOOT_SEQUENCE = TestCase(
    name="smart_reboot_verification",
    command="""
    echo "=== SMART REBOOT WITH VERIFICATION ==="
    echo "Phase 1: Pre-reboot state"
    echo "1. Timestamp:" && date
    echo "2. Uptime:" && uptime
    echo "3. Version:" && cat /etc/version
    echo ""
    echo "Phase 2: Initiating reboot"
    reboot
    echo "Reboot command sent. System will restart..."
    """,
    description="Smart reboot with boot monitoring and post-boot verification",
    timeout=300,  # 5 minutes
    result_filter=smart_reboot_sequence_filter
)

# ======================= TEST SUITES DEFINITION =======================

# Basic test suites
BASIC_TESTS = TestSuite(
    name="basic_checks",
    description="Basic system health checks",
    tests=[TEST_UPTIME, TEST_VERSION, TEST_DATE]
)

SYSTEM_TESTS = TestSuite(
    name="system_info",
    description="Comprehensive system information",
    tests=[
        TEST_UPTIME,
        TEST_KERNEL,
        TEST_VERSION,
        TEST_MEMORY,
        TEST_DISK,
        TEST_NETWORK,
        TEST_PROCESSES
    ]
)

QUICK_TESTS = TestSuite(
    name="quick_check",
    description="Quick system status check",
    tests=[TEST_UPTIME, TEST_VERSION]
)

# WAN test suites
WAN_STATUS_SUITE = TestSuite(
    name="wan_status",
    description="Check WAN connection status",
    tests=[TEST_WAN_STATUS]
)

WAN_ENHANCED_SUITE = TestSuite(
    name="wan_enhanced",
    description="Enhanced WAN status monitoring",
    tests=[ENHANCED_WAN_TEST]
)

# DSLITE test suites
DSLITE_COMPREHENSIVE_SUITE = TestSuite(
    name="dslite_full",
    description="Comprehensive DSLITE eligibility test with all checks",
    tests=[
        TEST_WAN_STATUS,
        TEST_DSLITE_VALUE,
        TEST_OPTION_125,
        TEST_OPTION_17
    ],
    setup_commands=[
        "echo 'Starting DSLITE comprehensive test...'",
        "date"
    ],
    teardown_commands=[
        "echo 'DSLITE comprehensive test completed.'",
        "date"
    ]
)

# Configuration test suites
WAN_PCB_CLI_SUITE = TestSuite(
    name="wan_pcb",
    description="WAN configuration via individual pcb_cli commands",
    tests=[
        WAN_SET_USERNAME,
        WAN_SET_PASSWORD,
        WAN_SET_ADMIN_PASS,
        WAN_SET_STATE
    ]
)

PROCESS_CGN_TRACES = TestSuite(
    name="trace_cgn",
    description="Process CGN traces via individual pcb_cli commands",
    tests=[
        TRACE_SET_NMC_CLIENT,
        TRACE_ADD_TRACE_ZONE,
        PROCESS_SAVE
    ]
)

# Reset and Reboot test suites
RESET_REBOOT_SUITE = TestSuite(
    name="reset_reboot",
    description="Gateway reset and reboot operations (WARNING: Disconnects!)",
    tests=[
        RESET_WARNING,
        RESET_HARD,
        REBOOT
    ],
    setup_commands=[
        "echo '=== WARNING: This will reset and reboot the gateway! ==='",
        "echo '=== You will be disconnected from the serial connection ==='",
        "date"
    ],
    teardown_commands=[
        "echo '=== Gateway reset/reboot initiated ==='",
        "echo '=== Reconnect manually after gateway restarts ==='",
        "date"
    ]
)

RESET_ONLY_SUITE = TestSuite(
    name="reset_only",
    description="Hard reset only (WARNING: Disconnects!)",
    tests=[RESET_HARD],
    setup_commands=[
        "echo 'WARNING: Performing hard reset...'",
        "date"
    ]
)

REBOOT_ONLY_SUITE = TestSuite(
    name="reboot_only",
    description="Reboot only (WARNING: Disconnects!)",
    tests=[REBOOT],
    setup_commands=[
        "echo 'WARNING: Rebooting gateway...'",
        "date"
    ]
)

# Reboot monitoring suites
MONITORED_REBOOT_SUITE = TestSuite(
    name="monitored_reboot",
    description="Monitored reboot with boot progress tracking",
    tests=[REBOOT_WITH_MONITOR],
    setup_commands=[
        "echo '=== MONITORED REBOOT SEQUENCE STARTING ==='",
        "echo 'Pre-reboot timestamp:' && date"
    ]
)

COMPLETE_REBOOT_SUITE = TestSuite(
    name="complete_reboot",
    description="Complete reboot cycle with pre/post checks",
    tests=[COMPLETE_REBOOT_CYCLE],
    setup_commands=[
        "echo '=== COMPLETE REBOOT TEST STARTING ==='",
        "echo 'Test start time:' && date"
    ]
)

SMART_REBOOT_SUITE = TestSuite(
    name="smart_reboot",
    description="Smart reboot with full monitoring and post-boot verification",
    tests=[SMART_REBOOT_SEQUENCE],
    setup_commands=[
        "echo '=== SMART REBOOT TEST STARTING ==='",
        "echo 'Start time:' && date"
    ]
)

# Custom test suites
MY_COMMANDS_SUITE = TestSuite(
    name="my_commands",
    description="My custom commands",
    tests=[
        TestCase(
            name="my_uptime",
            command="uptime",
            description="Check uptime"
        ),
        TestCase(
            name="my_version",
            command="cat /etc/version",
            description="Check version"
        ),
        TestCase(
            name="my_date",
            command="date",
            description="Check date"
        )
    ]
)

# ======================= ALL TEST SUITES REGISTRY =======================

TEST_SUITES = {
    'basic': BASIC_TESTS,
    'system': SYSTEM_TESTS,
    'quick': QUICK_TESTS,
    'uptime': TestSuite(
        name="uptime_only",
        description="Only uptime check",
        tests=[TEST_UPTIME]
    ),
    'version': TestSuite(
        name="version_only",
        description="Only version check",
        tests=[TEST_VERSION]
    ),
    'wan_status': WAN_STATUS_SUITE,
    'wan_enhanced': WAN_ENHANCED_SUITE,
    'dslite_full': DSLITE_COMPREHENSIVE_SUITE,
    'wan_pcb': WAN_PCB_CLI_SUITE,
    'trace_cgn': PROCESS_CGN_TRACES,
    'my_commands': MY_COMMANDS_SUITE,
    'reset_reboot': RESET_REBOOT_SUITE,
    'reset_only': RESET_ONLY_SUITE,
    'reboot_only': REBOOT_ONLY_SUITE,
    'monitored_reboot': MONITORED_REBOOT_SUITE,
    'complete_reboot': COMPLETE_REBOOT_SUITE,
    'smart_reboot': SMART_REBOOT_SUITE,
}

# ======================= ADVANCED DSLITE TEST WITH RETRY LOGIC =======================

def create_dslite_retry_test_suite(max_attempts=30, delay_seconds=10):
    """Create a special test suite with retry logic for DSLITE"""
    
    def dslite_retry_executor(connector):
        """Execute DSLITE test with retry logic"""
        print(f"\n{'='*60}")
        print("DSLITE COMPREHENSIVE TEST WITH RETRY LOGIC")
        print(f"Max attempts: {max_attempts}, Delay between checks: {delay_seconds}s")
        print('='*60)
        
        results = {
            "test_name": "dslite_retry_comprehensive",
            "timestamp": datetime.now().isoformat(),
            "attempts": [],
            "final_status": "UNKNOWN"
        }
        
        for attempt in range(1, max_attempts + 1):
            print(f"\n[ATTEMPT {attempt}/{max_attempts}]")
            print(f"Time: {datetime.now().strftime('%H:%M:%S')}")
            
            attempt_result = {
                "attempt_number": attempt,
                "timestamp": datetime.now().isoformat(),
                "steps": {}
            }
            
            # Step 1: Check WAN Status
            print("\n[1/4] Checking WAN status...")
            wan_result = connector.execute_command("pcb_cli 'NMC.getWANStatus()'", timeout=5)
            
            wan_up = "WanState=up" in wan_result["output"] and "LinkState=up" in wan_result["output"]
            attempt_result["steps"]["wan_status"] = {
                "both_up": wan_up,
                "passed": wan_up
            }
            
            if not wan_up:
                print(f"    ✗ WAN not up. Waiting {delay_seconds}s...")
                time.sleep(delay_seconds)
                results["attempts"].append(attempt_result)
                continue
            
            print("    ✓ WAN is up")
            
            # Step 2: Check DSLITE Value
            print("\n[2/4] Checking DSLITE Value...")
            dslite_result = connector.execute_command("pcb_cli 'NMC.ServiceEligibility.DSLITE.Value?'", timeout=5)
            
            dslite_ok = "0x0000" in dslite_result["output"]
            attempt_result["steps"]["dslite_value"] = {
                "is_0x0000": dslite_ok,
                "passed": dslite_ok
            }
            
            if not dslite_ok:
                print(f"    ✗ DSLITE Value not 0x0000. Waiting {delay_seconds}s...")
                time.sleep(delay_seconds)
                results["attempts"].append(attempt_result)
                continue
            
            print("    ✓ DSLITE Value is 0x0000")
            
            # Step 3: Check Option 125
            print("\n[3/4] Checking Option 125...")
            option125_result = connector.execute_command("pcb_cli 'NMC.ServiceEligibility.DSLITE.CgnOption.SentOption.125.Value?'", timeout=5)
            
            option125_expected = "000005580c020a000000ffffffffffffff"
            option125_ok = option125_expected in option125_result["output"]
            attempt_result["steps"]["option_125"] = {
                "passed": option125_ok
            }
            
            if not option125_ok:
                print(f"    ✗ Option 125 not as expected. Waiting {delay_seconds}s...")
                time.sleep(delay_seconds)
                results["attempts"].append(attempt_result)
                continue
            
            print("    ✓ Option 125 is correct")
            
            # Step 4: Check Option 17
            print("\n[4/4] Checking Option 17...")
            option17_result = connector.execute_command("pcb_cli 'NMC.ServiceEligibility.DSLITE.CgnOption.SentOption.17.Value?'", timeout=5)
            
            option17_expected = "000005580002000a000000ffffffffffffff"
            option17_ok = option17_expected in option17_result["output"]
            attempt_result["steps"]["option_17"] = {
                "passed": option17_ok
            }
            
            if not option17_ok:
                print(f"    ✗ Option 17 not as expected. Waiting {delay_seconds}s...")
                time.sleep(delay_seconds)
                results["attempts"].append(attempt_result)
                continue
            
            print("    ✓ Option 17 is correct")
            
            # All tests passed!
            attempt_result["all_passed"] = True
            results["attempts"].append(attempt_result)
            results["final_status"] = "SUCCESS"
            
            print(f"\n{'='*60}")
            print("✅ ALL TESTS PASSED!")
            print(f"Completed in attempt {attempt}")
            print('='*60)
            
            # Save final results
            save_dslite_retry_results(results, attempt_result)
            return results
        
        # If we get here, max attempts reached without success
        results["final_status"] = "FAILED_MAX_ATTEMPTS"
        
        print(f"\n{'='*60}")
        print("❌ MAX ATTEMPTS REACHED WITHOUT SUCCESS")
        print('='*60)
        
        save_dslite_retry_results(results, None)
        return results
    
    return dslite_retry_executor

def save_dslite_retry_results(results: Dict, final_attempt: Optional[Dict]):
    """Save DSLITE retry test results to file"""
    try:
        filename = os.path.join(TEST_RESULTS_DIR, f"dslite_retry_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
        
        with open(filename, 'w') as f:
            f.write(f"{'='*80}\n")
            f.write("DSLITE COMPREHENSIVE TEST WITH RETRY LOGIC - RESULTS\n")
            f.write(f"{'='*80}\n\n")
            
            f.write(f"Test Name: {results['test_name']}\n")
            f.write(f"Start Time: {results['timestamp']}\n")
            f.write(f"End Time: {datetime.now().isoformat()}\n")
            f.write(f"Final Status: {results['final_status']}\n")
            f.write(f"Total Attempts: {len(results['attempts'])}\n\n")
            
            if final_attempt and final_attempt.get('all_passed'):
                f.write("✅ FINAL RESULT: ALL TESTS PASSED\n\n")
                f.write(f"Completed in attempt: {final_attempt['attempt_number']}\n\n")
            
            f.write(f"{'='*80}\n")
            f.write("ATTEMPT HISTORY\n")
            f.write(f"{'='*80}\n\n")
            
            for attempt in results["attempts"]:
                f.write(f"Attempt {attempt['attempt_number']} - {attempt['timestamp']}\n")
                f.write("-" * 40 + "\n")
                
                if "steps" in attempt:
                    steps = attempt["steps"]
                    
                    # WAN Status
                    if "wan_status" in steps:
                        status = "✓" if steps["wan_status"]["passed"] else "✗"
                        f.write(f"WAN Status: {status}\n")
                    
                    # DSLITE Value
                    if "dslite_value" in steps:
                        status = "✓" if steps["dslite_value"]["passed"] else "✗"
                        f.write(f"DSLITE Value: {status}\n")
                    
                    # Option 125
                    if "option_125" in steps:
                        status = "✓" if steps["option_125"]["passed"] else "✗"
                        f.write(f"Option 125: {status}\n")
                    
                    # Option 17
                    if "option_17" in steps:
                        status = "✓" if steps["option_17"]["passed"] else "✗"
                        f.write(f"Option 17: {status}\n")
                
                f.write("\n")
        
        print(f"[+] DSLITE retry results saved to: {filename}")
        
    except Exception as e:
        print(f"[!] Error saving DSLITE retry results: {e}")

# ======================= PUBLIC INTERFACE =======================

def get_test_suite(suite_name):
    """Get test suite by name"""
    return TEST_SUITES.get(suite_name)

def list_test_suites():
    """List all available test suites"""
    return list(TEST_SUITES.keys())

def get_test_suite_details():
    """Get details of all test suites"""
    details = {}
    for name, suite in TEST_SUITES.items():
        details[name] = {
            'name': suite.name,
            'description': suite.description,
            'test_count': len(suite.tests),
            'tests': [test.name for test in suite.tests]
        }
    return details

def create_custom_suite(name, commands, description=""):
    """Create a custom test suite from list of commands"""
    tests = []
    for i, cmd in enumerate(commands):
        test = TestCase(
            name=f"custom_{i}",
            command=cmd,
            description=f"Custom command: {cmd}",
            timeout=3
        )
        tests.append(test)
    
    new_suite = TestSuite(
        name=name,
        description=description,
        tests=tests
    )
    
    # Add to available suites
    TEST_SUITES[name] = new_suite
    return new_suite

# Function to get DSLITE retry test executor
def get_dslite_retry_executor(max_attempts=30, delay_seconds=10):
    """Get a DSLITE retry test executor function"""
    return create_dslite_retry_test_suite(max_attempts, delay_seconds)

def get_extended_monitor_executor(monitor_timeout=300):
    """Get an executor for extended monitoring tests"""
    def extended_monitor_executor(connector, test_suite_name):
        """Execute test with extended monitoring"""
        test_suite = get_test_suite(test_suite_name)
        if not test_suite:
            print(f"[!] Test suite '{test_suite_name}' not found")
            return None
        
        print(f"\n{'='*60}")
        print(f"Running extended monitor test: {test_suite.name}")
        print(f"Description: {test_suite.description}")
        print(f"Will monitor for {monitor_timeout}s after command")
        print('='*60)
        
        results = {
            "suite_name": test_suite.name,
            "description": test_suite.description,
            "timestamp": datetime.now().isoformat(),
            "tests": [],
            "boot_monitoring": {
                "messages": [],
                "stages": [],
                "sysinit_detected": False,
                "boot_complete": False
            }
        }
        
        # Run setup commands
        if test_suite.setup_commands:
            print("\n[*] Running setup commands...")
            for cmd in test_suite.setup_commands:
                connector.execute_command(cmd, timeout=2)
        
        # Run each test
        for test in test_suite.tests:
            print(f"\n[+] Test: {test.name}")
            print(f"    Command: {test.command}")
            if test.description:
                print(f"    Description: {test.description}")
            
            # Execute command with extended monitoring would be handled by main.py
            # This is just a placeholder to return the test suite
            pass
        
        return results
    
    return extended_monitor_executor

# ======================= CONTINUOUS TEST LOOP EXECUTOR =======================

def create_continuous_test_loop(max_loops=None):
    """Create a continuous test loop executor"""
    
    def continuous_loop_executor(connector):
        """Execute continuous test loop"""
        import time
        from datetime import datetime
        
        print(f"\n{'='*80}")
        print("CONTINUOUS TEST LOOP SEQUENCE")
        print('='*80)
        print("Sequence: reset_only → reboot → wait for boot → login →")
        print("          wan_pcb → trace_cgn → dslite_full → check results")
        print('='*80)
        
        if max_loops:
            print(f"Maximum loops: {max_loops}")
        else:
            print("Loop will run indefinitely until Ctrl+C")
        
        # Initialize count file
        count_file = "count_loop.txt"
        loop_count = 0
        ok_count = 0
        ko_count = 0
        
        # Create or read existing count file
        if os.path.exists(count_file):
            try:
                with open(count_file, 'r') as f:
                    content = f.read()
                    # Try to parse existing counts
                    lines = content.strip().split('\n')
                    for line in lines:
                        if 'Total loops:' in line:
                            loop_count = int(line.split(':')[1].strip())
                        elif 'OK cases:' in line:
                            ok_count = int(line.split(':')[1].strip())
                        elif 'KO cases:' in line:
                            ko_count = int(line.split(':')[1].strip())
                print(f"[*] Loaded existing counts: {loop_count} total, {ok_count} OK, {ko_count} KO")
            except:
                print("[*] Starting fresh count file")
        else:
            print("[*] Creating new count file")
        
        try:
            while True:
                if max_loops and loop_count >= max_loops:
                    print(f"\n[*] Reached maximum loops: {max_loops}")
                    break
                
                loop_count += 1
                print(f"\n{'='*80}")
                print(f"LOOP {loop_count} - STARTING")
                print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                print('='*80)
                
                # Step 1: Hard reset
                print("\n[1/7] Performing hard reset...")
                try:
                    connector.execute_command("reset_hard", timeout=10)
                    print("    ✓ Reset command sent")
                    time.sleep(5)  # Wait for reset to start
                except Exception as e:
                    print(f"    [!] Reset error (may be normal): {e}")
                
                # We'll get disconnected here, need to reconnect
                print("\n[*] Waiting for gateway to reset...")
                time.sleep(2)  # Wait for reset to complete
                
                # Reconnect
                print("\n[*] Reconnecting after reset...")
                connector.disconnect()
                time.sleep(2)
                
                if not connector.connect():
                    print("[!] Failed to reconnect after reset")
                    print("[*] Waiting and retrying...")
                    time.sleep(30)
                    if not connector.connect():
                        print("[!] Still cannot reconnect, skipping loop")
                        ko_count += 1
                        update_count_file(count_file, loop_count, ok_count, ko_count)
                        continue
                
                # Step 2: Wait for login prompt
                print("\n[2/7] Waiting for login prompt...")
                if not connector.wait_for_login_prompt(timeout=120):
                    print("[!] Login prompt not detected within timeout")
                    ko_count += 1
                    update_count_file(count_file, loop_count, ok_count, ko_count)
                    continue
                
                # Step 3: Login
                print("\n[3/7] Logging in after reboot...")
                if not connector.login(max_attempts=3):
                    print("[!] Login failed after reboot")
                    ko_count += 1
                    update_count_file(count_file, loop_count, ok_count, ko_count)
                    continue
                
                print("    ✓ Login successful")
                
                # Step 4: Reboot
                print("\n[4/7] Rebooting gateway...")
                try:
                    connector.execute_command("reboot", timeout=10)
                    print("    ✓ Reboot command sent")
                except Exception as e:
                    print(f"    [!] Reboot error (may be normal): {e}")
                
                # Step 5: Wait for boot with monitoring
                print("\n[5/7] Monitoring boot process...")
                print("[*] Waiting for 'Sysinit done'...")
                
                boot_start = time.time()
                boot_timeout = 300  # 3 minutes
                sysinit_detected = False
                
                while time.time() - boot_start < boot_timeout:
                    try:
                        # Send Enter periodically
                        connector.send('', wait=0.5, echo=False)
                        time.sleep(1)
                        
                        output = connector.read_available(timeout=5, show=False)
                        
                        if "Sysinit done" in output:
                            print("\n    ✓ Sysinit done detected!")
                            sysinit_detected = True
                            break
                        
                        if "LIVEBOX login:" in output:
                            print("\n    ✓ Login prompt detected (skip Sysinit)")
                            break
                        
                        time.sleep(2)
                        
                    except Exception as e:
                        # Expected during reboot
                        pass
                
                if not sysinit_detected:
                    print("\n    [!] Sysinit not detected within timeout, continuing...")
                
                # Step 6: Wait for login prompt and login
                print("\n[6/7] Waiting for login prompt...")
                time.sleep(5)
                
                if not connector.wait_for_login_prompt(timeout=60):
                    print("[!] Login prompt not detected after reboot")
                
                if not connector.login(max_attempts=3):
                    print("[!] Login failed after reboot")
                    ko_count += 1
                    update_count_file(count_file, loop_count, ok_count, ko_count)
                    continue
                
                print("    ✓ Login successful after reboot")
                
                # Step 7: Run wan_pcb suite
                time.sleep(3)
                print("\n[7/7] Running WAN configuration...")
                wan_result = connector.run_tests("wan_pcb")
                if wan_result and wan_result.get("success"):
                    print("    ✓ WAN configuration completed")
                else:
                    print("    [!] WAN configuration may have issues")
                
                # Step 8: Run trace_cgn suite
                time.sleep(3)
                print("\n[8/7] Running CGN trace configuration...")
                trace_result = connector.run_tests("trace_cgn")
                if trace_result and trace_result.get("success"):
                    print("    ✓ CGN trace configuration completed")
                else:
                    print("    [!] CGN trace configuration may have issues")
                
                # Step 9: Run dslite_full suite and check results
                time.sleep(3)
                print("\n[9/7] Running DSLITE comprehensive test...")
                dslite_result = connector.run_tests("dslite_full")
                
                # Check if option tests passed
                option_125_ok = False
                option_17_ok = False
                
                if dslite_result and "tests" in dslite_result:
                    for test in dslite_result["tests"]:
                        if test["name"] == "option_125_check":
                            option_125_ok = test.get("valid", False)
                            print(f"    Option 125 check: {'✓ PASS' if option_125_ok else '✗ FAIL'}")
                        elif test["name"] == "option_17_check":
                            option_17_ok = test.get("valid", False)
                            print(f"    Option 17 check: {'✓ PASS' if option_17_ok else '✗ FAIL'}")
                
                # Determine if both options passed
                both_ok = option_125_ok and option_17_ok
                
                if both_ok:
                    print(f"\n{'='*80}")
                    print("✅ SUCCESS: Both Option 125 and Option 17 checks PASSED")
                    print('='*80)
                    ok_count += 1
                else:
                    print(f"\n{'='*80}")
                    print("❌ FAILURE: One or both Option checks FAILED")
                    print('='*80)
                    ko_count += 1
                    
                    # Save logs on failure
                    print("\n[*] Saving logs from /var/log/messages...")
                    try:
                        log_result = connector.execute_command("cat /var/log/messages", timeout=10)
                        if log_result and "output" in log_result:
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            ko_filename = f"result_cgn_test_ko_{timestamp}.txt"
                            
                            with open(ko_filename, 'w') as f:
                                f.write(f"{'='*80}\n")
                                f.write(f"CGN TEST FAILURE - Loop {loop_count}\n")
                                f.write(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                                f.write(f"Option 125: {'PASS' if option_125_ok else 'FAIL'}\n")
                                f.write(f"Option 17: {'PASS' if option_17_ok else 'FAIL'}\n")
                                f.write(f"{'='*80}\n\n")
                                f.write("LOG CONTENTS FROM /var/log/messages:\n")
                                f.write('-' * 80 + '\n')
                                f.write(log_result["output"])
                                f.write(f"\n{'='*80}\n")
                            
                            print(f"    ✓ Logs saved to: {ko_filename}")
                        else:
                            print("    [!] Failed to retrieve logs")
                    except Exception as e:
                        print(f"    [!] Error saving logs: {e}")
                
                # Update count file
                update_count_file(count_file, loop_count, ok_count, ko_count)
                
                print(f"\n[*] Loop {loop_count} completed")
                print(f"[*] Statistics: {ok_count} OK, {ko_count} KO out of {loop_count} total")
                
                # Check if we should continue
                if max_loops and loop_count >= max_loops:
                    print(f"\n[*] Reached maximum loops: {max_loops}")
                    break
                
                # Wait before next loop
                print("\n[*] Waiting 10 seconds before next loop...")
                time.sleep(10)
        
        except KeyboardInterrupt:
            print(f"\n\n[*] Loop interrupted by user")
            print(f"[*] Final statistics: {loop_count} loops, {ok_count} OK, {ko_count} KO")
            update_count_file(count_file, loop_count, ok_count, ko_count)
        
        except Exception as e:
            print(f"\n[!] Unexpected error in loop: {e}")
            import traceback
            traceback.print_exc()
            update_count_file(count_file, loop_count, ok_count, ko_count)
        
        finally:
            print(f"\n{'='*80}")
            print("CONTINUOUS TEST LOOP COMPLETED")
            print('='*80)
    
    return continuous_loop_executor

def update_count_file(filename, total, ok, ko):
    """Update the count file with current statistics"""
    try:
        with open(filename, 'w') as f:
            f.write(f"Continuous Test Loop Statistics\n")
            f.write(f"{'='*40}\n")
            f.write(f"Last update: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Total loops: {total}\n")
            f.write(f"OK cases: {ok}\n")
            f.write(f"KO cases: {ko}\n")
            f.write(f"Success rate: {(ok/total*100 if total > 0 else 0):.1f}%\n")
            f.write(f"{'='*40}\n")
        
        print(f"    [*] Counts updated in {filename}")
    except Exception as e:
        print(f"    [!] Error updating count file: {e}")

# ======================= SIMPLIFIED LOOP EXECUTOR =======================

def create_simple_test_loop(max_loops=None):
    """Create a simpler test loop that doesn't handle disconnect/reconnect"""
    
    def simple_loop_executor(connector):
        """Execute simple test loop (assumes connection stays active)"""
        import time
        from datetime import datetime
        
        print(f"\n{'='*80}")
        print("SIMPLE TEST LOOP SEQUENCE")
        print('='*80)
        print("Note: This assumes connection stays active (no reset_hard)")
        print('='*80)
        
        if max_loops:
            print(f"Maximum loops: {max_loops}")
        else:
            print("Loop will run indefinitely until Ctrl+C")
        
        # Initialize count file
        count_file = "count_loop.txt"
        loop_count = 0
        ok_count = 0
        ko_count = 0
        
        # Create or read existing count file
        if os.path.exists(count_file):
            try:
                with open(count_file, 'r') as f:
                    content = f.read()
                    lines = content.strip().split('\n')
                    for line in lines:
                        if 'Total loops:' in line:
                            loop_count = int(line.split(':')[1].strip())
                        elif 'OK cases:' in line:
                            ok_count = int(line.split(':')[1].strip())
                        elif 'KO cases:' in line:
                            ko_count = int(line.split(':')[1].strip())
                print(f"[*] Loaded existing counts: {loop_count} total, {ok_count} OK, {ko_count} KO")
            except:
                print("[*] Starting fresh count file")
        
        try:
            while True:
                if max_loops and loop_count >= max_loops:
                    print(f"\n[*] Reached maximum loops: {max_loops}")
                    break
                
                loop_count += 1
                print(f"\n{'='*80}")
                print(f"LOOP {loop_count} - STARTING")
                print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                print('='*80)
                
                # Step 1: Reboot (skip reset_hard to keep connection)
                print("\n[1/6] Rebooting gateway...")
                try:
                    reboot_result = connector.execute_command("reboot", timeout=10)
                    print("    ✓ Reboot command sent")
                except Exception as e:
                    print(f"    [!] Reboot error: {e}")
                
                # Monitor boot
                print("\n[2/6] Monitoring boot process...")
                boot_start = time.time()
                boot_timeout = 180
                sysinit_detected = False
                
                for i in range(boot_timeout):
                    try:
                        # Send Enter to wake up
                        connector.send('', wait=0.5, echo=False)
                        time.sleep(1)
                        
                        # Try to read
                        output = connector.read_available(timeout=2, show=False)
                        
                        if "Sysinit done" in output:
                            print(f"\n    ✓ Sysinit done detected after {i+1}s")
                            sysinit_detected = True
                            break
                            
                        if i % 10 == 0:  # Print progress every 10 seconds
                            print(f"    ... waiting for boot ({i}s)")
                        
                    except Exception as e:
                        # Expected during reboot
                        pass
                
                if not sysinit_detected:
                    print("\n    [!] Sysinit not detected within timeout, continuing anyway")
                
                # Login
                print("\n[3/6] Logging in...")
                time.sleep(5)
                
                if not connector.login(max_attempts=3):
                    print("[!] Login failed")
                    ko_count += 1
                    update_count_file(count_file, loop_count, ok_count, ko_count)
                    continue
                
                print("    ✓ Login successful")
                
                # Step 4: Run wan_pcb
                print("\n[4/6] Running WAN configuration...")
                try:
                    connector.run_tests("wan_pcb")
                    print("    ✓ WAN configuration completed")
                except Exception as e:
                    print(f"    [!] WAN configuration error: {e}")
                
                # Step 5: Run trace_cgn
                print("\n[5/6] Running CGN trace configuration...")
                try:
                    connector.run_tests("trace_cgn")
                    print("    ✓ CGN trace configuration completed")
                except Exception as e:
                    print(f"    [!] CGN trace configuration error: {e}")
                
                # Step 6: Run dslite_full and check
                print("\n[6/6] Running DSLITE comprehensive test...")
                option_125_ok = False
                option_17_ok = False
                
                try:
                    dslite_result = connector.run_tests("dslite_full")
                    
                    if dslite_result and "tests" in dslite_result:
                        for test in dslite_result["tests"]:
                            if test["name"] == "option_125_check":
                                option_125_ok = test.get("valid", False)
                            elif test["name"] == "option_17_check":
                                option_17_ok = test.get("valid", False)
                except Exception as e:
                    print(f"    [!] DSLITE test error: {e}")
                
                print(f"    Option 125: {'✓ PASS' if option_125_ok else '✗ FAIL'}")
                print(f"    Option 17: {'✓ PASS' if option_17_ok else '✗ FAIL'}")
                
                both_ok = option_125_ok and option_17_ok
                
                if both_ok:
                    print(f"\n✅ SUCCESS: Both options PASSED")
                    ok_count += 1
                else:
                    print(f"\n❌ FAILURE: One or both options FAILED")
                    ko_count += 1
                    
                    # Save logs
                    print("\n[*] Saving failure logs...")
                    try:
                        log_result = connector.execute_command("cat /var/log/messages | tail -1000", timeout=10)
                        if log_result and "output" in log_result:
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            ko_filename = f"result_cgn_test_ko_{timestamp}.txt"
                            
                            with open(ko_filename, 'w') as f:
                                f.write(f"Loop {loop_count} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                                f.write(f"Option 125: {'PASS' if option_125_ok else 'FAIL'}\n")
                                f.write(f"Option 17: {'PASS' if option_17_ok else 'FAIL'}\n")
                                f.write("-" * 60 + "\n")
                                f.write(log_result["output"])
                            
                            print(f"    ✓ Logs saved to: {ko_filename}")
                    except Exception as e:
                        print(f"    [!] Error saving logs: {e}")
                
                # Update count file
                update_count_file(count_file, loop_count, ok_count, ko_count)
                
                print(f"\n[*] Loop {loop_count} completed: {ok_count} OK, {ko_count} KO")
                
                if max_loops and loop_count >= max_loops:
                    break
                
                print("\n[*] Waiting 5 seconds before next loop...")
                time.sleep(5)
        
        except KeyboardInterrupt:
            print(f"\n\n[*] Loop interrupted by user")
            update_count_file(count_file, loop_count, ok_count, ko_count)
        
        except Exception as e:
            print(f"\n[!] Error in loop: {e}")
            update_count_file(count_file, loop_count, ok_count, ko_count)
    
    return simple_loop_executor

# Public interface for loop executors
def get_continuous_loop_executor(max_loops=None):
    """Get continuous loop executor with reset_hard"""
    return create_continuous_test_loop(max_loops)

def get_simple_loop_executor(max_loops=None):
    """Get simple loop executor (no reset_hard)"""
    return create_simple_test_loop(max_loops)