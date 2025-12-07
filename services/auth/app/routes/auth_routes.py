from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, status, Query, Header
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
                detail="The email or password you entered is incorrect. Please try again.",
            )

    except HTTPException:
        raise
    except Exception as e:
        print(f"Login error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Authentication failed: {str(e)}")


@router.post("/token/verify", response_model=TokenVerifyResponse)
async def verify_token(request: TokenRequest, requested_role: Optional[Role] = None):
    """Verify JWT token and return user information"""
    try:
        token = request.token
        print(f"Verifying token: {token[:15]}...")

        try:
            # Verify token and get payload
            payload = keycloak_service.verify_token(token)
            print(f"Decoded token info: {payload}")

            # Get all realm roles from the token
            all_realm_roles = payload.get("realm_access", {}).get("roles", [])

            # Extract core user data
            user_data = {
                "valid": True,
                "user_id": payload.get("sub"),
                "email": payload.get("email"),
                "name": payload.get("name"),
                "roles": all_realm_roles,
                "expires_at": payload.get("exp"),
            }

            # Determine primary role
            realm_roles = all_realm_roles
            primary_role = None

            # Use requested role if user has it
            if requested_role and requested_role.value in realm_roles:
                primary_role = requested_role
            else:
                # Otherwise select highest priority role
                for role in [Role.ADMIN, Role.DOCTOR, Role.RADIOLOGIST, Role.PATIENT]:
                    if role.value in realm_roles:
                        primary_role = role
                        break

            user_data["primary_role"] = primary_role
            print(
                f"Token verified for user: {user_data['email']}, role: {primary_role}"
            )
            return user_data

        except Exception as e:
            error_msg = str(e).lower()
            print(f"Token verification failed: {str(e)}")
            return {"valid": False, "error": error_msg}

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
        print(f"Registering user: {request}")

        # Log registration attempt
        print(f"Registration attempt for user: {request.email}")

        # Prepare user data for registration
        user_data = {
            "email": request.email,
            "username": request.username or request.email,
            "password": request.password,
            "firstName": (request.name if request.name else ""),
            "lastName": (request.name if request.name else ""),
            "phone": (request.phone if request.phone else ""),
            "specialty": request.specialty if request.specialty else "",
            "address": request.address if request.address else "",
            "role": request.role if request.role else "patient",
            "bio": request.bio if request.bio else "",
            "license_number": request.license_number if request.license_number else "",
            "hospital": request.hospital if request.hospital else "",
            "education": request.education if request.education else "",
            "experience": request.experience if request.experience else "",
            "signature": request.signature if request.signature else "",
            "is_verified": (
                str(request.is_verified).lower()
                if request.is_verified is not None
                else "false"
            ),
            "verification_details": (
                request.verification_details if request.verification_details else None
            ),
            # Add new patient fields - handle both frontend and backend field naming
            "date_of_birth": request.date_of_birth or request.date_of_birth if hasattr(request,
                                                                                       'date_of_birth') else "",
            "blood_type": request.blood_type or request.blood_type if hasattr(request, 'blood_type') else "",
            "social_security_number": (
                request.social_security_number if request.social_security_number else ""
            ),
            "medical_history": (
                request.medical_history if request.medical_history else
                ([request.medical_history] if hasattr(request, 'medical_history') and isinstance(
                    request.medical_history, str) else
                 (request.medical_history if hasattr(request, 'medical_history') else []))
            ),
            "allergies": request.allergies if request.allergies else [],
            "height": str(request.height or request.height) if hasattr(request,
                                                                       'height') and request.height is not None else "",
            "weight": str(request.weight or request.weight) if hasattr(request,
                                                                       'weight') and request.weight is not None else "",
            "medical_files": request.medical_files if hasattr(request,
                                                              'medical_files') and request.medical_files else [],
        }

        try:
            # Use KeycloakService for user registration
            user_id = keycloak_service.register(user_data)
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

            if (
                    "409" in error_message
                    or "conflict" in error_message
                    or "already exists" in error_message
            ):
                raise HTTPException(status_code=409, detail="Email already registered")
            elif "403" in error_message or "permission" in error_message:
                print("Permission denied. Check Keycloak client permissions.")
                raise HTTPException(
                    status_code=500,
                    detail="User registration failed: Insufficient permissions. Contact the administrator.",
                )
            else:
                raise HTTPException(
                    status_code=500, detail=f"User registration failed: {error_message}"
                )

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
async def logout(
        request: Optional[LogoutRequest] = None, authorization: str = Header(None)
):
    try:
        # Log the logout attempt
        print("Logout attempt received")
        refresh_token = None

        # Try to get refresh token from request body
        if request and hasattr(request, "refresh_token") and request.refresh_token:
            refresh_token = request.refresh_token
            print(f"Logout with refresh token from body: {refresh_token[:10]}...")
        # If no refresh token in body, try to extract from Authorization header
        elif authorization:
            token = authorization.replace("Bearer ", "")
            print(f"Trying to logout with token from header: {token[:10]}...")
            try:
                # Attempt to use the access token to help with logout
                keycloak_service.logout_from_access_token(token)
                print("Logout from access token successful")
            except Exception as e:
                print(f"Logout from access token failed: {str(e)}")

        # Use KeycloakService for logout if we have a refresh token
        if refresh_token:
            try:
                keycloak_service.logout(refresh_token)
                print("Logout with refresh token successful")
            except Exception as e:
                print(f"Keycloak logout operation with refresh token failed: {str(e)}")

        # Always return success to client regardless of backend result
        return {"message": "Logged out successfully"}

    except Exception as e:
        print(f"Logout error: {str(e)}")
        # Return success even if we couldn't process the request properly
        # This is to ensure the client can continue with their logout flow
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
        return {
            "message": "If your email is registered, you will receive a password reset link"
        }


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
        print(f"Getting user info for user_id: {user_id}")
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


@router.get(
    "/users",
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_users_by_role(
        role: Optional[Role] = None,
        first: int = Query(0, ge=0),
        max: int = Query(10, ge=1, le=100),
        user_info: dict = Depends(get_current_user),
):
    """
    Get users filtered by role with pagination

    Args:
        role: Optional role filter (e.g., 'doctor', 'patient')
        first: Pagination offset
        max: Maximum number of users to return
    """
    try:
        print(f"Getting users with role: {role}, first: {first}, max: {max}")

        # If no role filter, just return all users with pagination
        if not role:
            print("No role specified, getting all users")
            return keycloak_service.keycloak_admin.get_users(
                {"first": first, "max": max}
            )

        role_name = role

        print(f"Normalized role name: {role_name}")

        # Get all users to check their roles (we'll apply pagination later)
        all_users = keycloak_service.keycloak_admin.get_users({})
        print(f"Total users found: {len(all_users)}")

        # Filter users by role (check both realm roles and attributes)
        filtered_users = []

        for user in all_users:
            user_id = user.get("id")
            username = user.get("username")
            has_role = False

            # APPROACH 1: Check realm roles
            try:
                user_realm_roles = (
                    keycloak_service.keycloak_admin.get_realm_roles_of_user(user_id)
                )
                realm_role_names = [r.get("name") for r in user_realm_roles]
                print(f"User {username} realm roles: {realm_role_names}")

                if role_name in realm_role_names:
                    print(f"User {username} has {role_name} in realm roles")
                    has_role = True

            except Exception as e:
                print(f"Error getting realm roles for user {username}: {str(e)}")

            # APPROACH 2: Check user attributes if realm role check didn't find a match
            if not has_role:
                try:
                    attributes = user.get("attributes", {})
                    print(f"User {username} attributes: {attributes}")

                    if attributes and "role" in attributes:
                        attr_role = attributes["role"]
                        # Handle both string and list values
                        if isinstance(attr_role, list) and attr_role:
                            attr_role = attr_role[0]

                        # Compare with both formats of the role name
                        if attr_role == role_name or attr_role == role:
                            print(f"User {username} has {role_name} in attributes")
                            has_role = True

                except Exception as e:
                    print(f"Error checking attributes for user {username}: {str(e)}")

            # Add user to filtered list if either check passed
            if has_role:
                filtered_users.append(user)

        print(f"Found {len(filtered_users)} users with role {role_name}")

        # Apply pagination to filtered results
        start_idx = first
        end_idx = min(first + max, len(filtered_users))
        return filtered_users[start_idx:end_idx]

    except Exception as e:
        print(f"Get users error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get users: {str(e)}")


@router.get(
    "/profile",
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_profile(user_info: dict = Depends(get_current_user)):
    """
    Get the current logged-in user's profile information.

    Returns the complete user profile including all attributes.
    """
    try:
        # Extract user ID from the token
        user_id = user_info.get("user_id")
        if not user_id:
            raise HTTPException(status_code=404, detail="User ID not found in token")

        print(f"Getting profile for user: {user_id}")

        # Use KeycloakService to get user information
        user_data = keycloak_service.get_user_info_by_id(user_id)

        if not user_data:
            raise HTTPException(status_code=404, detail="User profile not found")

        # Clean up sensitive data
        if "credentials" in user_data:
            del user_data["credentials"]

        if "access" in user_data:
            del user_data["access"]

        # Format attributes correctly - convert list values to single values for client
        attributes = user_data.get("attributes", {})
        formatted_attributes = {}

        for key, value in attributes.items():
            # Handle array values from Keycloak by using the first item
            if isinstance(value, list) and len(value) > 0:
                formatted_attributes[key] = value[0]
            else:
                formatted_attributes[key] = value

        # Replace attributes with formatted version
        user_data["attributes"] = formatted_attributes

        # Add roles information
        user_data["roles"] = user_info.get("roles", [])

        # Add role information
        user_data["role"] = user_info.get("primary_role")

        return user_data

    except HTTPException:
        raise
    except Exception as e:
        print(f"Get profile error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get profile: {str(e)}")
