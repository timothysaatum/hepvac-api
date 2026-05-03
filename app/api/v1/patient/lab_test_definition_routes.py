import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_db
from app.core.permission_checker import require_admin, require_staff_or_admin
from app.models.patient_model import LabTestDefinition, LabTestParameterDefinition
from app.models.user_model import User
from app.schemas.patient_schemas import (
    LabTestDefinitionCreateSchema,
    LabTestDefinitionResponseSchema,
    LabTestDefinitionUpdateSchema,
    LabTestParameterDefinitionCreateSchema,
    LabTestParameterDefinitionResponseSchema,
    LabTestParameterDefinitionUpdateSchema,
)


router = APIRouter(prefix="/lab-test-definitions", tags=["lab test definitions"])


async def _get_test_definition(
    db: AsyncSession,
    test_definition_id: uuid.UUID,
) -> LabTestDefinition:
    result = await db.execute(
        select(LabTestDefinition)
        .where(LabTestDefinition.id == test_definition_id)
        .options(selectinload(LabTestDefinition.parameters))
    )
    definition = result.scalars().first()
    if not definition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lab test definition not found.",
        )
    return definition


async def _get_parameter_definition(
    db: AsyncSession,
    parameter_id: uuid.UUID,
) -> LabTestParameterDefinition:
    result = await db.execute(
        select(LabTestParameterDefinition).where(LabTestParameterDefinition.id == parameter_id)
    )
    parameter = result.scalars().first()
    if not parameter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lab test parameter not found.",
        )
    return parameter


@router.get("", response_model=list[LabTestDefinitionResponseSchema])
async def list_lab_test_definitions(
    include_inactive: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    query = select(LabTestDefinition).options(selectinload(LabTestDefinition.parameters))
    if not include_inactive:
        query = query.where(LabTestDefinition.is_active == True)
    query = query.order_by(LabTestDefinition.name.asc())
    result = await db.execute(query)
    return list(result.scalars().all())


@router.post(
    "",
    response_model=LabTestDefinitionResponseSchema,
    status_code=status.HTTP_201_CREATED,
)
async def create_lab_test_definition(
    payload: LabTestDefinitionCreateSchema,
    current_user: Annotated[User, Depends(require_admin())],
    db: AsyncSession = Depends(get_db),
):
    definition_data = payload.model_dump(exclude={"parameters"})
    definition = LabTestDefinition(**definition_data, created_by_id=current_user.id)
    for index, parameter_payload in enumerate(payload.parameters):
        parameter_data = parameter_payload.model_dump()
        if "display_order" not in parameter_data or parameter_data["display_order"] == 0:
            parameter_data["display_order"] = index
        definition.parameters.append(LabTestParameterDefinition(**parameter_data))

    db.add(definition)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A lab test or parameter with that code already exists.",
        ) from exc

    return await _get_test_definition(db, definition.id)


@router.get("/{test_definition_id}", response_model=LabTestDefinitionResponseSchema)
async def get_lab_test_definition(
    test_definition_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin()),
):
    return await _get_test_definition(db, test_definition_id)


@router.patch("/{test_definition_id}", response_model=LabTestDefinitionResponseSchema)
async def update_lab_test_definition(
    test_definition_id: uuid.UUID,
    payload: LabTestDefinitionUpdateSchema,
    current_user: Annotated[User, Depends(require_admin())],
    db: AsyncSession = Depends(get_db),
):
    definition = await _get_test_definition(db, test_definition_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(definition, field, value)

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A lab test with that code already exists.",
        ) from exc

    return await _get_test_definition(db, test_definition_id)


@router.delete("/{test_definition_id}", response_model=LabTestDefinitionResponseSchema)
async def deactivate_lab_test_definition(
    test_definition_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_admin())],
    db: AsyncSession = Depends(get_db),
):
    definition = await _get_test_definition(db, test_definition_id)
    definition.is_active = False
    await db.commit()
    return await _get_test_definition(db, test_definition_id)


@router.post(
    "/{test_definition_id}/parameters",
    response_model=LabTestParameterDefinitionResponseSchema,
    status_code=status.HTTP_201_CREATED,
)
async def create_lab_test_parameter(
    test_definition_id: uuid.UUID,
    payload: LabTestParameterDefinitionCreateSchema,
    current_user: Annotated[User, Depends(require_admin())],
    db: AsyncSession = Depends(get_db),
):
    await _get_test_definition(db, test_definition_id)
    parameter = LabTestParameterDefinition(
        lab_test_definition_id=test_definition_id,
        **payload.model_dump(),
    )
    db.add(parameter)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A parameter with that code already exists for this test.",
        ) from exc

    await db.refresh(parameter)
    return parameter


@router.patch("/parameters/{parameter_id}", response_model=LabTestParameterDefinitionResponseSchema)
async def update_lab_test_parameter(
    parameter_id: uuid.UUID,
    payload: LabTestParameterDefinitionUpdateSchema,
    current_user: Annotated[User, Depends(require_admin())],
    db: AsyncSession = Depends(get_db),
):
    parameter = await _get_parameter_definition(db, parameter_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(parameter, field, value)

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A parameter with that code already exists for this test.",
        ) from exc

    await db.refresh(parameter)
    return parameter


@router.delete("/parameters/{parameter_id}", response_model=LabTestParameterDefinitionResponseSchema)
async def deactivate_lab_test_parameter(
    parameter_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_admin())],
    db: AsyncSession = Depends(get_db),
):
    parameter = await _get_parameter_definition(db, parameter_id)
    parameter.is_active = False
    await db.commit()
    await db.refresh(parameter)
    return parameter
