"""
Environment Verification Script

This script checks if all required environment variables are properly configured.
Run this to verify your setup is correct before starting the backend.

Usage:
    python verify_env.py
"""

import os
from dotenv import load_dotenv
from pathlib import Path
from typing import Dict, Tuple

# Colors for terminal output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_header(text: str):
    """Print a formatted header"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'=' * 60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text:^60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'=' * 60}{Colors.RESET}\n")

def print_section(text: str):
    """Print a formatted section"""
    print(f"\n{Colors.BOLD}{text}{Colors.RESET}")
    print("-" * 60)

def print_check(status: bool, message: str, details: str = ""):
    """Print a check result"""
    symbol = f"{Colors.GREEN}✓{Colors.RESET}" if status else f"{Colors.RED}✗{Colors.RESET}"
    print(f"{symbol} {message}")
    if details:
        print(f"  {Colors.YELLOW}→ {details}{Colors.RESET}")

def verify_env_file_exists() -> bool:
    """Verify .env file exists"""
    env_path = Path(".env")
    exists = env_path.exists()
    print_check(exists, ".env file exists", str(env_path.absolute()) if exists else "Not found")
    return exists

def load_env() -> bool:
    """Load environment variables"""
    try:
        load_dotenv()
        print_check(True, "Environment variables loaded")
        return True
    except Exception as e:
        print_check(False, "Failed to load environment variables", str(e))
        return False

def verify_maya_credentials() -> Tuple[bool, Dict[str, str]]:
    """Verify Maya API credentials"""
    print_section("Maya API Credentials")
    
    credentials = {
        'MAYA_API_KEY': os.getenv('MAYA_API_KEY', ''),
        'MAYA_SECRET_KEY': os.getenv('MAYA_SECRET_KEY', ''),
        'MAYA_WEBHOOK_SECRET': os.getenv('MAYA_WEBHOOK_SECRET', ''),
        'MAYA_SANDBOX_URL': os.getenv('MAYA_SANDBOX_URL', ''),
    }
    
    all_valid = True
    
    # Check API Key
    api_key = credentials['MAYA_API_KEY']
    is_valid = bool(api_key) and api_key.startswith('pk_test_')
    print_check(is_valid, "MAYA_API_KEY", "Sandbox key (pk_test_...)" if is_valid else "Invalid or missing")
    all_valid = all_valid and is_valid
    
    # Check Secret Key
    secret_key = credentials['MAYA_SECRET_KEY']
    is_valid = bool(secret_key) and secret_key.startswith('sk_test_')
    print_check(is_valid, "MAYA_SECRET_KEY", "Sandbox key (sk_test_...)" if is_valid else "Invalid or missing")
    all_valid = all_valid and is_valid
    
    # Check Webhook Secret
    webhook_secret = credentials['MAYA_WEBHOOK_SECRET']
    is_valid = bool(webhook_secret) and webhook_secret.startswith('whsec_')
    print_check(is_valid, "MAYA_WEBHOOK_SECRET", "Format valid (whsec_...)" if is_valid else "Invalid or missing")
    all_valid = all_valid and is_valid
    
    # Check Sandbox URL
    sandbox_url = credentials['MAYA_SANDBOX_URL']
    is_valid = sandbox_url == 'https://payments-sandbox.paycom.ph'
    print_check(is_valid, "MAYA_SANDBOX_URL", "Correct sandbox URL" if is_valid else f"Got: {sandbox_url}")
    all_valid = all_valid and is_valid
    
    return all_valid, credentials

def verify_webhook_configuration() -> bool:
    """Verify webhook configuration"""
    print_section("Webhook Configuration")
    
    webhook_url = os.getenv('WEBHOOK_URL', '')
    
    checks = [
        (bool(webhook_url), "WEBHOOK_URL is set", webhook_url if webhook_url else "Not set"),
        (
            webhook_url.startswith('http') if webhook_url else False,
            "WEBHOOK_URL is valid URL",
            "HTTPS recommended" if webhook_url and webhook_url.startswith('https') else "Should use HTTPS"
        ),
        (
            '/api/webhooks/payments/maya' in webhook_url if webhook_url else False,
            "WEBHOOK_URL has correct path",
            "Path: /api/webhooks/payments/maya"
        ),
    ]
    
    all_valid = True
    for is_valid, message, details in checks:
        print_check(is_valid, message, details)
        all_valid = all_valid and is_valid
    
    return all_valid

def verify_return_urls() -> bool:
    """Verify return URL configuration"""
    print_section("Return URLs (After Payment)")
    
    frontend_url = os.getenv('FRONTEND_RETURN_URL', '')
    mobile_url = os.getenv('MOBILE_APP_RETURN_URL', '')
    
    checks = [
        (bool(frontend_url), "FRONTEND_RETURN_URL is set", frontend_url if frontend_url else "Not set"),
        (
            frontend_url.startswith('http') if frontend_url else False,
            "FRONTEND_RETURN_URL is valid URL",
            frontend_url if frontend_url else "Not set"
        ),
        (bool(mobile_url), "MOBILE_APP_RETURN_URL is set", mobile_url if mobile_url else "Not set"),
        (
            mobile_url.startswith('condoease://') if mobile_url else False,
            "MOBILE_APP_RETURN_URL has correct scheme",
            "Deep link: condoease://..."
        ),
    ]
    
    all_valid = True
    for is_valid, message, details in checks:
        print_check(is_valid, message, details)
        all_valid = all_valid and is_valid
    
    return all_valid

def verify_existing_configuration() -> bool:
    """Verify existing configuration"""
    print_section("Existing Configuration")
    
    existing_vars = {
        'JWT_SECRET': 'JWT authentication secret',
        'DB_SERVER': 'Database server',
        'DB_USER': 'Database user',
        'DB_PASS': 'Database password',
        'DB_NAME': 'Database name',
    }
    
    all_valid = True
    for var, description in existing_vars.items():
        value = os.getenv(var, '')
        is_valid = bool(value) and not 'your_' in value.lower()
        print_check(is_valid, f"{var}", description if is_valid else "Not configured")
        all_valid = all_valid and is_valid
    
    return all_valid

def verify_imports() -> bool:
    """Verify Python imports work"""
    print_section("Python Dependencies")
    
    imports_to_test = [
        ('fastapi', 'FastAPI'),
        ('sqlalchemy', 'SQLAlchemy'),
        ('pydantic', 'Pydantic'),
        ('jose', 'PyJOSE'),
        ('dotenv', 'python-dotenv'),
        ('requests', 'Requests'),
        ('cryptography', 'Cryptography'),
    ]
    
    all_valid = True
    for module_name, display_name in imports_to_test:
        try:
            __import__(module_name)
            print_check(True, f"{display_name} installed", "Ready to use")
        except ImportError:
            print_check(False, f"{display_name} not installed", f"Run: pip install {module_name}")
            all_valid = False
    
    return all_valid

def main():
    """Run all verification checks"""
    print_header("CondoEase Backend - Environment Verification")
    
    # Run checks
    env_exists = verify_env_file_exists()
    
    if not env_exists:
        print(f"\n{Colors.RED}{Colors.BOLD}ERROR: .env file not found!{Colors.RESET}")
        print(f"Please create .env file in the backend directory")
        return False
    
    env_loaded = load_env()
    
    if not env_loaded:
        print(f"\n{Colors.RED}{Colors.BOLD}ERROR: Could not load .env file!{Colors.RESET}")
        return False
    
    maya_valid, credentials = verify_maya_credentials()
    webhook_valid = verify_webhook_configuration()
    urls_valid = verify_return_urls()
    existing_valid = verify_existing_configuration()
    imports_valid = verify_imports()
    
    # Summary
    print_header("Verification Summary")
    
    checks_summary = [
        (maya_valid, "Maya API Credentials", "All credentials properly configured"),
        (webhook_valid, "Webhook Configuration", "Webhook URL properly set"),
        (urls_valid, "Return URLs", "Return URLs properly configured"),
        (existing_valid, "Existing Configuration", "Database and JWT configured"),
        (imports_valid, "Python Dependencies", "All dependencies installed"),
    ]
    
    print(f"\n{Colors.BOLD}Status:{Colors.RESET}\n")
    all_passed = True
    for is_valid, name, message in checks_summary:
        print_check(is_valid, name, message)
        all_passed = all_passed and is_valid
    
    # Final status
    print("\n" + "=" * 60)
    if all_passed:
        print(f"{Colors.GREEN}{Colors.BOLD}✓ All checks passed! Environment is ready.{Colors.RESET}")
        print(f"\nYou can now start the backend:")
        print(f"  {Colors.YELLOW}python main.py{Colors.RESET}")
    else:
        print(f"{Colors.RED}{Colors.BOLD}✗ Some checks failed. Please review above.{Colors.RESET}")
        print(f"\nVisit {Colors.YELLOW}ENV_SETUP_GUIDE.md{Colors.RESET} for detailed instructions.")
    print("=" * 60 + "\n")
    
    return all_passed

if __name__ == '__main__':
    import sys
    success = main()
    sys.exit(0 if success else 1)
