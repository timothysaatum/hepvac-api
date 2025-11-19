# pagination
@router.get("/users")
async def list_users(
    pagination: PaginationParams = Depends(get_pagination_params)
):
    query = select(User).where(User.is_active == True)
    result = await Paginator.paginate(db, query, pagination, UserSchema)
    return {"users": result.items, "pagination": result.page_info}
