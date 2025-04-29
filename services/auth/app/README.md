# Authentication Service Troubleshooting Guide

## Common Errors

### Invalid User Credentials Error

If you're seeing this error:

```
ERROR auth_service:app.py:165 Keycloak login failed: {"error":"invalid_grant","error_description":"Invalid user credentials"}
```

This indicates that Keycloak rejected the provided username/password combination.

#### Troubleshooting Steps:

1. **Verify User Exists**: Make sure the user exists in Keycloak with the exact email/username being used for login.

2. **Check Credentials**: Verify the password is correct. You might need to reset the password in Keycloak admin console.

3. **Email vs Username**: Confirm whether Keycloak is configured to use email or username for login. By default, it accepts both.

4. **User Status**: Check that the user is not temporarily locked due to too many failed attempts.

5. **Realm Settings**: Verify that you're using the correct realm name (`pulmocare`).

6. **Client Configuration**:

   - Make sure the client has correct access type (confidential)
   - Verify that "Direct Access Grants Enabled" is ON
   - Check that the client has the proper service account roles

7. **Environment Variables**: Ensure your environment variables are correctly set:

   ```
   KEYCLOAK_URL=http://keycloak:8080  # In production
   KEYCLOAK_URL=http://localhost:8090  # In development
   KEYCLOAK_REALM=pulmocare
   KEYCLOAK_CLIENT_ID=pulmocare-api
   KEYCLOAK_CLIENT_SECRET=pulmocare-secret
   ```

8. **Network Issues**: If Keycloak is running in a different container or service, ensure proper connectivity.

## Diagnostic Endpoints

The service provides diagnostic endpoints to verify your Keycloak configuration. You must be logged in with admin privileges to access these endpoints.

### Basic Connection Test

```
GET /api/auth/diagnostics/keycloak
```

This will test connectivity, realm existence, and client credentials verification.

### Realm Configuration Verification

```
GET /api/auth/diagnostics/realm-config
```

This endpoint verifies that the realm configuration matches our expected structure:

- Checks that required roles exist (`admin`, `doctor-role`, `patient-role`, `radiologist-role`)
- Verifies group structure (`Doctors`, `Patients`, `Radiologists`, `Administrators`)
- Confirms client configuration is correct
- Checks for the admin test user

## Keycloak Realm Structure

Our service expects the following Keycloak realm structure:

### Realm

- Name: `pulmocare`

### Roles

- `admin`: Administrator role
- `doctor-role`: Doctor role
- `patient-role`: Patient role
- `radiologist-role`: Radiologist role

### Groups

- `Administrators`: Users with admin role
- `Doctors`: Users with doctor-role
- `Patients`: Users with patient-role
- `Radiologists`: Users with radiologist-role

### Client

- Client ID: `pulmocare-api`
- Client Secret: `pulmocare-secret`
- Access Type: Confidential
- Service Account Enabled: Yes
- Direct Access Grants Enabled: Yes

## Running Tests

The auth service includes comprehensive tests to validate the Keycloak integration.

### Unit Tests

Run unit tests with:

```bash
cd /home/pulmocareadmin/medapp-backend/services/auth
python -m pytest tests/
```

### Running Specific Tests

To run only the Keycloak service tests:

```bash
python -m pytest tests/test_keycloak_service.py -v
```

To run the integration route tests:

```bash
python -m pytest tests/test_integration_routes.py -v
```

### Test Coverage

Generate a test coverage report with:

```bash
python -m pytest --cov=app --cov-report=html
```

This will create an HTML coverage report in the `htmlcov` directory.
