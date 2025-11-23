"""
Project Management Endpoints

CRUD operations for projects within a tenant.
Projects are the main resource type in this demo system.

RBAC:
- List/view projects: All authenticated users
- Create project: Member role or higher
- Update project: Members (any project), viewers cannot
- Delete project: Admin or project owner
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime

from app.database import get_db
from app.models.user import User, UserRole
from app.models.project import Project
from app.models.tenant import Tenant
from app.schemas.project import (
    ProjectResponse,
    ProjectCreate,
    ProjectUpdate,
    ProjectListResponse
)
from app.api.deps import get_current_user, get_current_tenant
from app.core.permissions import require_member, can_delete_project, can_modify_project
from app.core.exceptions import ProjectNotFoundError
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=ProjectListResponse)
async def list_projects(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None, pattern="^(active|archived|completed)$"),
    owner_id: Optional[str] = None,
    include_deleted: bool = False,
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
):
    """
    List projects in current tenant.

    Supports filtering by status, owner, and soft-deleted flag.
    Paginated for performance.

    TENANT_ISOLATION: Automatically filtered by current tenant.

    PERFORMANCE NOTE: This could be slow with many projects.
    Consider adding indexes on filter columns.
    """
    # Build query with tenant filter (CRITICAL for isolation)
    query = db.query(Project).filter(Project.tenant_id == tenant.id)

    # Apply filters
    if not include_deleted:
        query = query.filter(Project.is_deleted == False)

    if status:
        query = query.filter(Project.status == status)

    if owner_id:
        query = query.filter(Project.owner_id == owner_id)

    # Get total count
    total = query.count()

    # Apply pagination and ordering
    offset = (page - 1) * page_size
    projects = query.order_by(
        Project.created_at.desc()
    ).offset(offset).limit(page_size).all()

    logger.debug(f"Listed {len(projects)} projects for tenant {tenant.id}")

    return ProjectListResponse(
        projects=projects,
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
):
    """
    Get project by ID.

    TENANT_ISOLATION: Can only access projects in same tenant.

    FEATURE: Increments view count for analytics.
    """
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.tenant_id == tenant.id,  # CRITICAL: Tenant isolation
        Project.is_deleted == False
    ).first()

    if not project:
        raise ProjectNotFoundError(project_id)

    # Track view for analytics
    # NOTE: This updates DB on every view - might want to batch these
    # or use a separate analytics system for high-traffic scenarios
    project.view_count += 1
    project.last_accessed_at = datetime.utcnow()
    db.commit()

    return project


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    project_data: ProjectCreate,
    current_user: User = Depends(require_member),  # Member role required
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
):
    """
    Create a new project.

    Requires member role or higher.
    Current user becomes the project owner.

    BUSINESS LOGIC: In production, you might want to:
    - Enforce project limits based on subscription tier
    - Validate project name uniqueness within tenant
    - Initialize default resources/settings
    """
    # Create project
    new_project = Project(
        tenant_id=tenant.id,  # CRITICAL: Set tenant_id
        owner_id=current_user.id,
        name=project_data.name,
        description=project_data.description,
        is_public=project_data.is_public,
        status="active"
    )

    db.add(new_project)
    db.commit()
    db.refresh(new_project)

    logger.info(f"Project created: {new_project.id} by {current_user.id}")

    return new_project


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: str,
    project_data: ProjectUpdate,
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
):
    """
    Update project information.

    Permissions:
    - Admin: Can update any project
    - Member: Can update any project (collaborative)
    - Viewer: Cannot update projects

    DESIGN CHOICE: We allow members to edit any project for collaboration.
    Alternative: Only owner + admin can edit.
    """
    # Load project with tenant isolation
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.tenant_id == tenant.id,  # CRITICAL
        Project.is_deleted == False
    ).first()

    if not project:
        raise ProjectNotFoundError(project_id)

    # Check permissions
    if not can_modify_project(current_user, project.owner_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to modify this project"
        )

    # Apply updates
    update_data = project_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(project, field, value)

    db.commit()
    db.refresh(project)

    logger.info(f"Project updated: {project.id} by {current_user.id}")

    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: str,
    hard_delete: bool = Query(False, description="Permanently delete (admin only)"),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
):
    """
    Delete project (soft delete by default).

    Permissions:
    - Admin: Can delete any project (soft or hard)
    - Project owner: Can soft delete own project
    - Hard delete: Admin only

    PATTERN: Soft delete by default for easy recovery.
    Hard delete permanently removes data.
    """
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.tenant_id == tenant.id  # CRITICAL
    ).first()

    if not project:
        raise ProjectNotFoundError(project_id)

    # Check permissions
    if not can_delete_project(current_user, project.owner_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this project"
        )

    if hard_delete:
        # Hard delete - admin only
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Hard delete requires admin privileges"
            )

        db.delete(project)
        logger.info(f"Project hard deleted: {project_id} by {current_user.id}")
    else:
        # Soft delete
        project.soft_delete()
        logger.info(f"Project soft deleted: {project_id} by {current_user.id}")

    db.commit()
    return None


@router.post("/{project_id}/restore", response_model=ProjectResponse)
async def restore_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
):
    """
    Restore a soft-deleted project.

    Requires admin role.

    FEATURE: Allows recovering accidentally deleted projects.
    This is why soft delete is preferred in SaaS applications.
    """
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can restore projects"
        )

    project = db.query(Project).filter(
        Project.id == project_id,
        Project.tenant_id == tenant.id,  # CRITICAL
        Project.is_deleted == True
    ).first()

    if not project:
        raise ProjectNotFoundError(project_id)

    # Restore project
    project.is_deleted = False
    project.deleted_at = None

    db.commit()
    db.refresh(project)

    logger.info(f"Project restored: {project_id} by {current_user.id}")

    return project
