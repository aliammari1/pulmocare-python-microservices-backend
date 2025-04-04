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

5. **Realm Settings**: Verify that you're using the correct realm name.

6. **Client Configuration**:

   - Make sure the client has correct access type (confidential)
   - Verify that "Direct Access Grants Enabled" is ON
   - Check that the client has the proper service account roles

7. **Environment Variables**: Ensure your environment variables are correctly set:

   ```
   KEYCLOAK_URL=http://keycloak:8080
   KEYCLOAK_REALM=medapp
   KEYCLOAK_CLIENT_ID=medapp-api
   KEYCLOAK_CLIENT_SECRET=your-client-secret
   ```

8. **Network Issues**: If Keycloak is running in a different container or service, ensure proper connectivity.

## Diagnostic Endpoint

The service provides a diagnostic endpoint at `/api/auth/diagnostics/keycloak` that can be used to verify your Keycloak configuration. You must be logged in with admin privileges to access this endpoint.
