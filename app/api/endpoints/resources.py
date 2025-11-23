"""
Resource Management Endpoints

CRUD operations for resources within projects.
Resources demonstrate nested tenant isolation (tenant -> project -> resource).

RBAC: Same as projects (members can modify, viewers read-only)
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.models.user import User
from app.models.project import Project
from app.models.resource import Resource
from app.models.tenant import Tenant
from app.schemas.resource import (
    ResourceResponse,
    ResourceCreate,
    ResourceUpdate,
    ResourceListResponse
)
from app.api.deps import get_current_user, get_current_tenant
from app.core.permissions import can_modify_project
from app.core.exceptions import ProjectNotFoundError, ResourceNotFoundError, TenantIsolationError
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/resources", tags=["resources"])


@router.get("", response_model=ResourceListResponse)
async def list_resources(
    project_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
):
    """
    List resources.

    Can filter by project_id and resource_type.
    If project_id not provided, lists all resources in tenant.

    TENANT_ISOLATION: Always filtered by tenant, even when querying
    across projects. This is defense-in-depth.
    """
    # Build query with tenant filter (CRITICAL)
    query = db.query(Resource).filter(Resource.tenant_id == tenant.id)

    # Filter by project if specified
    if project_id:
        # Verify project belongs to tenant (additional security check)
        project = db.query(Project).filter(
            Project.id == project_id,
            Project.tenant_id == tenant.id,
            Project.is_deleted == False
        ).first()

        if not project:
            raise ProjectNotFoundError(project_id)

        query = query.filter(Resource.project_id == project_id)

    # Filter by type
    if resource_type:
        query = query.filter(Resource.resource_type == resource_type)

    # Get total count
    total = query.count()

    # Apply pagination
    offset = (page - 1) * page_size
    resources = query.order_by(
        Resource.created_at.desc()
    ).offset(offset).limit(page_size).all()

    logger.debug(f"Listed {len(resources)} resources for tenant {tenant.id}")

    return ResourceListResponse(
        resources=resources,
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/{resource_id}", response_model=ResourceResponse)
async def get_resource(
    resource_id: str,
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
):
    """
    Get resource by ID.

    TENANT_ISOLATION: Can only access resources in same tenant.
    """
    resource = db.query(Resource).filter(
        Resource.id == resource_id,
        Resource.tenant_id == tenant.id  # CRITICAL
    ).first()

    if not resource:
        raise ResourceNotFoundError(resource_id)

    return resource


@router.post("", response_model=ResourceResponse, status_code=status.HTTP_201_CREATED)
async def create_resource(
    resource_data: ResourceCreate,
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
):
    """
    Create a new resource in a project.

    CRITICAL: Must verify project belongs to current tenant.
    This prevents resources being created in other tenants' projects.
    """
    # Verify project exists and belongs to tenant
    project = db.query(Project).filter(
        Project.id == resource_data.project_id,
        Project.tenant_id == tenant.id,  # CRITICAL: Tenant isolation check
        Project.is_deleted == False
    ).first()

    if not project:
        raise ProjectNotFoundError(resource_data.project_id)

    # Check permissions
    if not can_modify_project(current_user, project.owner_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to add resources to this project"
        )

    # Create resource
    # IMPORTANT: We explicitly set tenant_id even though it's redundant
    # with project.tenant_id. This is defense-in-depth for isolation.
    new_resource = Resource(
        tenant_id=tenant.id,  # CRITICAL: Explicit tenant_id
        project_id=project.id,
        name=resource_data.name,
        resource_type=resource_data.resource_type,
        content=resource_data.content,
        file_url=resource_data.file_url,
        metadata=resource_data.metadata or {}
    )

    # Calculate file size if content provided
    if new_resource.content:
        new_resource.file_size = len(new_resource.content.encode('utf-8'))

    db.add(new_resource)
    db.commit()
    db.refresh(new_resource)

    logger.info(f"Resource created: {new_resource.id} in project {project.id}")

    return new_resource


@router.patch("/{resource_id}", response_model=ResourceResponse)
async def update_resource(
    resource_id: str,
    resource_data: ResourceUpdate,
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
):
    """
    Update resource information.

    SECURITY: Checks both resource and project tenant isolation.
    """
    # Load resource with tenant isolation
    resource = db.query(Resource).filter(
        Resource.id == resource_id,
        Resource.tenant_id == tenant.id  # CRITICAL
    ).first()

    if not resource:
        raise ResourceNotFoundError(resource_id)

    # Load project to check permissions
    project = db.query(Project).filter(
        Project.id == resource.project_id
    ).first()

    if not project:
        # This shouldn't happen due to FK constraints, but being defensive
        logger.error(f"Resource {resource_id} has invalid project_id")
        raise ProjectNotFoundError(resource.project_id)

    # Double-check tenant isolation (paranoid mode)
    if project.tenant_id != tenant.id:
        logger.error(
            f"TENANT ISOLATION VIOLATION: Resource {resource_id} project mismatch",
            extra={"resource_tenant": resource.tenant_id, "project_tenant": project.tenant_id}
        )
        raise TenantIsolationError("Resource-Project tenant mismatch")

    # Check permissions
    if not can_modify_project(current_user, project.owner_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to modify this resource"
        )

    # Apply updates
    update_data = resource_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(resource, field, value)

    # Update file size if content changed
    if 'content' in update_data and resource.content:
        resource.file_size = len(resource.content.encode('utf-8'))

    # Increment version on update
    resource.version += 1

    db.commit()
    db.refresh(resource)

    logger.info(f"Resource updated: {resource.id} (v{resource.version})")

    return resource


@router.delete("/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resource(
    resource_id: str,
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
):
    """
    Delete resource (hard delete).

    DESIGN NOTE: Resources are hard-deleted, unlike projects which are
    soft-deleted. This is because resources are more granular and less
    critical to recover. Could be changed based on requirements.
    """
    # Load resource with tenant isolation
    resource = db.query(Resource).filter(
        Resource.id == resource_id,
        Resource.tenant_id == tenant.id  # CRITICAL
    ).first()

    if not resource:
        raise ResourceNotFoundError(resource_id)

    # Load project to check permissions
    project = db.query(Project).filter(
        Project.id == resource.project_id
    ).first()

    if not project:
        raise ProjectNotFoundError(resource.project_id)

    # Check permissions
    if not can_modify_project(current_user, project.owner_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this resource"
        )

    # Hard delete
    db.delete(resource)
    db.commit()

    logger.info(f"Resource deleted: {resource_id} by {current_user.id}")

    return None


# Additional endpoint: Get resources by project
# This is a convenience endpoint, could also use query param on list endpoint
@router.get("/by-project/{project_id}", response_model=ResourceListResponse)
async def list_project_resources(
    project_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
):
    """
    Get all resources for a specific project.

    Convenience endpoint with higher default page size.
    """
    # Verify project access
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.tenant_id == tenant.id,
        Project.is_deleted == False
    ).first()

    if not project:
        raise ProjectNotFoundError(project_id)

    # Query resources
    query = db.query(Resource).filter(
        Resource.project_id == project_id,
        Resource.tenant_id == tenant.id  # Redundant but explicit
    )

    total = query.count()
    offset = (page - 1) * page_size
    resources = query.offset(offset).limit(page_size).all()

    return ResourceListResponse(
        resources=resources,
        total=total,
        page=page,
        page_size=page_size
    )
