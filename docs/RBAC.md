# RBAC

python manage_rbac.py init
python manage_rbac.py list-roles
python manage_rbac.py list-permissions
python manage_rbac.py show-role superadmin
python manage_rbac.py add-permission "report.generate" "Generate reports"
python manage_rbac.py add-role "moderator" "user.read,user.update,session.terminate"
python manage_rbac.py assign-role tim admin


# Rate limitter
# ============= USAGE EXAMPLE =============

"""
# In your authentication endpoint:

@router.post("/auth/login")
async def login(
    credentials: LoginSchema,
    request: Request,
    db: AsyncSession = Depends(get_db),
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
):
    # 1. Rate limiting (by IP)
    ip = SecurityMiddleware()._get_client_ip(request)
    is_allowed, remaining = await rate_limiter.check_rate_limit(
        f"login_ip:{ip}", max_attempts=5, window_seconds=300
    )

    if not is_allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Try again later."
        )

    # 2. Authenticate user
    user = await authenticate_user(credentials.username, credentials.password, db)
    if not user:
        # Log failed attempt
        await log_login_attempt(
            username=credentials.username,
            ip_address=ip,
            success=False,
            db=db
        )
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # 3. Check device trust
    security = SecurityMiddleware()
    is_trusted, reason = await security.check_device_trust(request, user.id, db)

    if not is_trusted:
        # Log the attempt
        await log_login_attempt(
            user_id=user.id,
            username=credentials.username,
            ip_address=ip,
            success=False,
            failure_reason=reason,
            db=db
        )

        # Send notification to admins about pending device
        await notify_admins_new_device(user, request)

        raise HTTPException(
            status_code=403,
            detail=reason
        )

    # 4. Success - create session
    token = create_access_token(user)

    # Log successful attempt
    await log_login_attempt(
        user_id=user.id,
        username=credentials.username,
        ip_address=ip,
        success=True,
        db=db
    )

    return {"access_token": token, "token_type": "bearer"}
"""