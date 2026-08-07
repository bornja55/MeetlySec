import os  # noqa: F401 — จะใช้ตอนเชื่อม Azure AD จริง (tenant/client id ผ่าน env var, ดู task.md Module 1)
from typing import Any

import jwt  # noqa: F401 — จะใช้ decode JWT จริงตอนเชื่อม Azure AD (ยังไม่ implement — mock อยู่)
from fastapi import Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

security = HTTPBearer()

# For a production Azure AD setup, you would fetch the JWKS from:
# https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys
# and use the `msal` or `fastapi-azure-auth` library to properly decode and validate it.


def _resolve_mock_token(token: str) -> dict[str, Any]:
    """แยก logic map token→user ออกมาจาก verify_azure_ad_token เดิม (2026-08-04) เพื่อ reuse ได้จาก
    verify_audio_stream_token() ด้านล่างด้วย — ตอนต่อ Azure AD จริงค่อยเปลี่ยน implementation ของ
    ฟังก์ชันนี้จุดเดียว (decode JWT จริง) ทั้งสอง entry point ข้างบนไม่ต้องแก้"""
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


def verify_azure_ad_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict[str, Any]:
    return _resolve_mock_token(credentials.credentials)


def verify_audio_stream_token(token: str = Query(..., description="Bearer token ผ่าน query string")) -> dict[str, Any]:
    """เฉพาะ endpoint ที่ต้องให้ HTML5 <audio>/<video> element เรียก src= ตรงๆ (preview ฟังไฟล์เสียง
    ย้อนหลัง, ดู main.py's GET /api/meetings/{id}/audio) — element พวกนี้แนบ Authorization header เอง
    ไม่ได้ (ต่างจาก apiFetch/downloadAuthenticatedFile ฝั่ง frontend ที่ใช้ fetch() สั่งเองได้) เลยต้อง
    รับ token ผ่าน query param แทน

    ⚠️ ความเสี่ยงที่รู้อยู่แล้ว: token ใน query string หลุดไปอยู่ใน browser history/server access log
    ได้ง่ายกว่า header — ยอมรับได้สำหรับ MVP นี้เพราะเป็น mock token คงที่ ไม่ใช่ credential จริงของ
    ผู้ใช้ ต้องทบทวนใหม่ตอนต่อ Azure AD จริง (เช่นออก short-lived signed URL แทน ไม่ใช่ token เต็มอายุ)"""
    return _resolve_mock_token(token)


def _build_role_checker(get_user):
    """factory กลาง ใช้สร้างทั้ง require_role (header-based, endpoint ปกติ) และ
    require_role_for_audio_stream (query-token-based, <audio>/<video> element) จาก dependency ที่คืน
    user dict คนละแบบ — ตรรกะเช็ค role เหมือนกันเป๊ะ ไม่อยากก็อปเก็บ 2 ที่เสี่ยง diverge"""
    def require_role(required_roles: list[str]):
        def role_checker(user: dict = Depends(get_user)):
            user_role = user.get("role")
            if user_role not in required_roles and user_role != "Global_Admin":
                raise HTTPException(status_code=403, detail=f"Permission denied. Requires one of: {required_roles}")
            return user
        return role_checker
    return require_role


require_role = _build_role_checker(verify_azure_ad_token)
require_role_for_audio_stream = _build_role_checker(verify_audio_stream_token)
