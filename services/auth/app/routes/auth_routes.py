from fastapi import APIRouter, Depends, HTTPException, Path, status
from middleware.keycloak_auth import get_current_user
from models.auth import *
from services.keycloak_service import KeycloakService

# Initialize router
router = APIRouter(prefix="/api/auth", tags=["Authentication"])

# Initialize Keycloak service
keycloak_service = KeycloakService()

@router.post(
    "/login",
    response_model=LoginResponse,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def login(request: LoginRequest):
    try:
        # Log the login attempt (without password)
        print(f"Login attempt for user: {request.email}")
        
        try:
            # Use KeycloakService for login
            result = keycloak_service.login(request.email, request.password)
            print(f"Login successful for user: {request.email}")
            return result
        except Exception as e:
            print(f"Keycloak login failed: {str(e)}")
            
            # Provide user-friendly error message
            raise HTTPException(
                status_code=401, 
                detail="The email or password you entered is incorrect. Please try again."
            )

    except HTTPException:
        raise
    except Exception as e:
        print(f"Login error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Authentication failed: {str(e)}")


@router.post("/token/verify", response_model=TokenVerifyResponse)
async def verify_token(request: TokenRequest):
    try:
        token = request.token
        # Only log a portion of the token for security
        print(f"Verifying token: {token[:15]}...")
        
        try:
            # Use KeycloakService for token verification
            payload = keycloak_service.verify_token(token)
            
            # Extract user data from token payload
            user_id = payload.get("sub")
            email = payload.get("email")
            
            # Extract detailed user information
            user_data = {
                "valid": True,
                "user_id": user_id,
                "email": email,
                "name": payload.get("name"),
                "given_name": payload.get("given_name"),
                "family_name": payload.get("family_name"),
                "preferred_username": payload.get("preferred_username"),
                "email_verified": payload.get("email_verified", False),
                
                # Extract roles information
                "roles": payload.get("realm_access", {}).get("roles", []),
                "resource_access": payload.get("resource_access", {}),
                
                # Extract token metadata
                "expires_at": payload.get("exp"),
                "issued_at": payload.get("iat"),
                "issuer": payload.get("iss"),
                "token_type": payload.get("typ"),
                "session_id": payload.get("sid"),
                "scope": payload.get("scope", "").split(),
            }
            
            # Detect the user's primary role for easier role-based access
            primary_role = None
            realm_roles = user_data["roles"]
            
            # Look for specific role patterns
            role_priority = ["admin", "doctor-role", "radiologist-role", "patient-role"]
            for role in role_priority:
                if role in realm_roles:
                    primary_role = role
                    break
            
            user_data["primary_role"] = primary_role
            
            print(f"Token verified successfully for user: {email}")
            return user_data

        except Exception as e:
            error_msg = str(e).lower()
            print(f"Token verification failed: {str(e)}")
            
            # Provide more specific error messages for common token issues
            if "expired" in error_msg:
                return {"valid": False, "error": "Token has expired"}
            elif "signature" in error_msg:
                return {"valid": False, "error": "Invalid token signature"}
            elif "malformed" in error_msg or "decode" in error_msg:
                return {"valid": False, "error": "Malformed token"}
            elif "invalid audience" in error_msg:
                return {"valid": False, "error": "Invalid token audience"}
            else:
                return {"valid": False, "error": str(e)}

    except Exception as e:
        print(f"Token verification error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Verification failed: {str(e)}")

@router.post(
    "/token/refresh",
    response_model=RefreshTokenResponse,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def refresh_token(request: RefreshTokenRequest):
    try:
        # Use KeycloakService for token refresh
        result = keycloak_service.refresh_token(request.refresh_token)
        return result

    except Exception as e:
        print(f"Token refresh error: {str(e)}")
        raise HTTPException(status_code=401, detail="Invalid refresh token")


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def register(request: RegisterRequest):
    try:
        # Log registration attempt
        print(f"Registration attempt for user: {request.email}")
        
        # Prepare user data for registration
        user_data = {
            "email": request.email,
            "username": request.username or request.email,
            "password": request.password,
            "firstName": request.name if request.name else "",  # Provide default empty string
            "lastName": request.name if request.name else "",   # Provide default empty string
            "phone": request.phone if request.phone else "",    # Handle potentially None values
            "specialty": request.specialty if request.specialty else "",
            "address": request.address if request.address else "",
            "role": request.role if request.role else "patient",   # Default role
        }
        
        try:
            # Use KeycloakService for user registration
            user_id = keycloak_service.register_user(user_data)
            print(f"User created successfully in Keycloak: {user_data['username']}")
            
            # Try auto-login after registration
            try:
                login_result = keycloak_service.login(request.email, request.password)
                
                # Return success with tokens
                return {
                    "message": "User registered successfully",
                    "user_id": user_id,
                    "access_token": login_result["access_token"],
                    "refresh_token": login_result["refresh_token"],
                    "expires_in": login_result["expires_in"],
                }
            except Exception as e:
                print(f"Auto-login after registration failed: {str(e)}")
                # Still return success without tokens
                return {"message": "User registered successfully", "user_id": user_id}
                
        except Exception as e:
            error_message = str(e)
            
            if "409" in error_message or "conflict" in error_message or "already exists" in error_message:
                raise HTTPException(status_code=409, detail="Email already registered")
            elif "403" in error_message or "permission" in error_message:
                print("Permission denied. Check Keycloak client permissions.")
                raise HTTPException(
                    status_code=500, 
                    detail="User registration failed: Insufficient permissions. Contact the administrator."
                )
            else:
                raise HTTPException(status_code=500, detail=f"User registration failed: {error_message}")

    except HTTPException:
        raise
    except Exception as e:
        print(f"Registration error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")


@router.post(
    "/logout",
    response_model=MessageResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def logout(request: LogoutRequest):
    try:
        # Use KeycloakService for logout
        keycloak_service.logout(request.refresh_token)
        return {"message": "Logged out successfully"}
    except Exception as e:
        print(f"Logout error: {str(e)}")
        # Still return success even if there was an error
        return {"message": "Logged out successfully"}


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def forgot_password(request: ForgotPasswordRequest):
    try:
        # Use KeycloakService for password reset
        keycloak_service.request_password_reset(request.email)
        return {"message": "Password reset email sent successfully"}
    except Exception as e:
        print(f"Password reset error: {str(e)}")
        # For security, always return the same message regardless of outcome
        return {"message": "If your email is registered, you will receive a password reset link"}


@router.get(
    "/user/{user_id}",
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_user(
    user_id: str = Path(...), user_info: dict = Depends(get_current_user)
):
    try:
        # Check if requesting own info or has admin role
        if user_id != user_info.get("sub") and "admin" not in user_info.get(
            "realm_access", {}
        ).get("roles", []):
            raise HTTPException(status_code=403, detail="Unauthorized")

        # Use KeycloakService to get user information
        user_data = keycloak_service.get_user_info_by_id(user_id)
        
        # Clean up sensitive data
        if "credentials" in user_data:
            del user_data["credentials"]

        if "access" in user_data:
            del user_data["access"]

        # Get user roles if possible
        try:
            # This would require implementing a method in KeycloakService to get user roles
            # For now, we'll use the roles from the token
            user_data["roles"] = user_info.get("realm_access", {}).get("roles", [])
        except Exception as e:
            print(f"Failed to get user roles: {str(e)}")
            user_data["roles"] = []

        return user_data

    except HTTPException:
        raise
    except Exception as e:
        print(f"Get user error: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get user info: {str(e)}"
        )
