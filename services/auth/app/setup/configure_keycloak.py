import os
import requests
import logging
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("keycloak_setup")

# Configuration
KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "http://localhost:8090")
KEYCLOAK_ADMIN = os.getenv("KEYCLOAK_ADMIN", "admin")
KEYCLOAK_ADMIN_PASSWORD = os.getenv("KEYCLOAK_ADMIN_PASSWORD", "admin")
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "medapp")
KEYCLOAK_CLIENT_ID = os.getenv("KEYCLOAK_CLIENT_ID", "medapp-api")
KEYCLOAK_CLIENT_SECRET = os.getenv("KEYCLOAK_CLIENT_SECRET", "your-client-secret")

def get_admin_token():
    """Get admin token from Keycloak"""
    try:
        response = requests.post(
            f"{KEYCLOAK_URL}/realms/master/protocol/openid-connect/token",
            data={
                "username": KEYCLOAK_ADMIN,
                "password": KEYCLOAK_ADMIN_PASSWORD,
                "grant_type": "password",
                "client_id": "admin-cli"
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        
        if response.status_code != 200:
            logger.error(f"Failed to get admin token: {response.text}")
            return None
            
        return response.json()["access_token"]
    except Exception as e:
        logger.error(f"Error getting admin token: {str(e)}")
        return None

def configure_client_service_account():
    """Configure the client service account with proper roles"""
    admin_token = get_admin_token()
    if not admin_token:
        logger.error("Cannot proceed without admin token")
        return False
    
    # Get client ID
    logger.info(f"Getting client ID for {KEYCLOAK_CLIENT_ID}")
    response = requests.get(
        f"{KEYCLOAK_URL}/admin/realms/{KEYCLOAK_REALM}/clients",
        headers={"Authorization": f"Bearer {admin_token}"},
        params={"clientId": KEYCLOAK_CLIENT_ID}
    )
    
    if response.status_code != 200:
        logger.error(f"Failed to get client: {response.text}")
        return False
    
    clients = response.json()
    if not clients:
        logger.error(f"Client {KEYCLOAK_CLIENT_ID} not found")
        return False
    
    client_id = clients[0]["id"]
    logger.info(f"Found client with ID: {client_id}")
    
    # Ensure service account is enabled
    logger.info("Enabling service account")
    response = requests.put(
        f"{KEYCLOAK_URL}/admin/realms/{KEYCLOAK_REALM}/clients/{client_id}",
        headers={
            "Authorization": f"Bearer {admin_token}",
            "Content-Type": "application/json"
        },
        json={
            "serviceAccountsEnabled": True,
            "clientAuthenticatorType": "client-secret"
        }
    )
    
    if response.status_code != 204:
        logger.error(f"Failed to enable service account: {response.text}")
        return False
    
    # Get service account user ID
    logger.info("Getting service account user")
    response = requests.get(
        f"{KEYCLOAK_URL}/admin/realms/{KEYCLOAK_REALM}/clients/{client_id}/service-account-user",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    if response.status_code != 200:
        logger.error(f"Failed to get service account user: {response.text}")
        return False
    
    service_account_user_id = response.json()["id"]
    logger.info(f"Service account user ID: {service_account_user_id}")
    
    # Get realm-management client ID
    logger.info("Getting realm-management client ID")
    response = requests.get(
        f"{KEYCLOAK_URL}/admin/realms/{KEYCLOAK_REALM}/clients",
        headers={"Authorization": f"Bearer {admin_token}"},
        params={"clientId": "realm-management"}
    )
    
    if response.status_code != 200 or not response.json():
        logger.error(f"Failed to get realm-management client: {response.text}")
        return False
    
    realm_management_id = response.json()[0]["id"]
    logger.info(f"Realm management client ID: {realm_management_id}")
    
    # Get available roles from realm-management
    logger.info("Getting available roles")
    response = requests.get(
        f"{KEYCLOAK_URL}/admin/realms/{KEYCLOAK_REALM}/clients/{realm_management_id}/roles",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    if response.status_code != 200:
        logger.error(f"Failed to get roles: {response.text}")
        return False
    
    roles = response.json()
    
    # Find required roles
    required_roles = ["manage-users", "view-users", "query-users", "view-realm"]
    roles_to_assign = []
    
    for role_name in required_roles:
        role = next((r for r in roles if r["name"] == role_name), None)
        if role:
            roles_to_assign.append(role)
        else:
            logger.warning(f"Role {role_name} not found")
    
    if not roles_to_assign:
        logger.error("No required roles found")
        return False
    
    # Assign roles to service account
    logger.info(f"Assigning roles: {[r['name'] for r in roles_to_assign]}")
    response = requests.post(
        f"{KEYCLOAK_URL}/admin/realms/{KEYCLOAK_REALM}/users/{service_account_user_id}/role-mappings/clients/{realm_management_id}",
        headers={
            "Authorization": f"Bearer {admin_token}",
            "Content-Type": "application/json"
        },
        json=roles_to_assign
    )
    
    if response.status_code != 204:
        logger.error(f"Failed to assign roles: {response.text}")
        return False
    
    logger.info("Service account configured successfully")
    return True

def main():
    logger.info("Starting Keycloak configuration")
    
    # Wait for Keycloak to be ready
    max_retries = 10
    retry_delay = 5
    
    for i in range(max_retries):
        try:
            logger.info(f"Checking if Keycloak is ready (attempt {i+1}/{max_retries})")
            response = requests.get(f"{KEYCLOAK_URL}")
            if response.status_code < 400:
                logger.info("Keycloak is ready")
                break
        except Exception as e:
            logger.warning(f"Keycloak not ready yet: {str(e)}")
        
        if i < max_retries - 1:
            logger.info(f"Waiting {retry_delay} seconds before retry...")
            time.sleep(retry_delay)
            retry_delay *= 1.5  # Exponential backoff
    
    # Configure service account
    if configure_client_service_account():
        logger.info("Keycloak configuration completed successfully")
    else:
        logger.error("Keycloak configuration failed")

if __name__ == "__main__":
    main()
