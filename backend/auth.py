import os  # noqa: F401 — จะใช้ตอนเชื่อม Azure AD จริง (tenant/client id ผ่าน env var, ดู task.md Module 1)
from typing import Any

import jwt  # noqa: F401 — จะใช้ decode JWT จริงตอนเชื่อม Azure AD (ยังไม่ implement — mock อยู่)
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

security = HTTPBearer()

# For a production Azure AD setup, you would fetch the JWKS from:
# https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys
# and use the `msal` or `fastapi-azure-auth` library to properly decode and validate it.

def verify_azure_ad_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict[str, Any]:
    token = credentials.credentials
    
    # MOCK implementation for MVP:
    # In reality, decode the JWT and check roles/groups
    if token == "mock_admin_token":
        return {"user_id": "admin@company.com", "role": "Global_Admin", "name": "Admin User"}
    elif token == "mock_maker_token":
        return {"user_id": "maker@company.com", "role": "Com_Sec_Maker", "name": "Company Secretary Maker"}
    elif token == "mock_checker_token":
        return {"user_id": "checker@company.com", "role": "Com_Sec_Checker", "name": "Company Secretary Checker"}
    elif token == "mock_board_token":
        return {"user_id": "board@company.com", "role": "Board_Member", "name": "Board Director"}
        
    raise HTTPException(status_code=401, detail="Invalid or expired Azure AD token")

def require_role(required_roles: list[str]):
    def role_checker(user: dict = Depends(verify_azure_ad_token)):
        user_role = user.get("role")
        if user_role not in required_roles and user_role != "Global_Admin":
            raise HTTPException(status_code=403, detail=f"Permission denied. Requires one of: {required_roles}")
        return user
    return role_checker
