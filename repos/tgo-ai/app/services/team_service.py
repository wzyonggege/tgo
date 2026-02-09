"""Team service for business logic."""

import uuid
from typing import List, Optional, Tuple

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.team import Team
from app.models.agent import Agent
from app.models.collection import AgentCollection
from app.schemas.team import TeamCreate, TeamUpdate


class TeamService:
    """Service for team-related business logic."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_team(self, project_id: uuid.UUID, team_data: TeamCreate) -> Team:
        """
        Create a new team.
        
        Args:
            project_id: Project ID
            team_data: Team creation data
            
        Returns:
            Created team
            
        Raises:
            ConflictError: If trying to create default team when one exists
        """
        # Check if trying to create default team when one already exists
        if team_data.is_default:
            await self._ensure_no_default_team_exists(project_id)

        # Create team
        team = Team(
            project_id=project_id,
            name=team_data.name,
            model=team_data.model,
            instruction=team_data.instruction,
            expected_output=team_data.expected_output,
            session_id=team_data.session_id,
            is_default=team_data.is_default,
            llm_provider_id=team_data.llm_provider_id,
            config=team_data.config,
        )

        self.db.add(team)
        await self.db.commit()
        await self.db.refresh(team)
        return team

    async def get_team(self, project_id: uuid.UUID, team_id: uuid.UUID) -> Team:
        """
        Get a team by ID.
        
        Args:
            project_id: Project ID
            team_id: Team ID
            
        Returns:
            Team
            
        Raises:
            NotFoundError: If team not found
        """
        stmt = (
            select(Team)
            .options(
                selectinload(Team.llm_provider),
                selectinload(Team.agents).selectinload(Agent.tools),
                selectinload(Team.agents).selectinload(Agent.collections),
                selectinload(Team.agents).selectinload(Agent.llm_provider),
            )
            .where(
                and_(
                    Team.id == team_id,
                    Team.project_id == project_id,
                    Team.deleted_at.is_(None),
                )
            )
        )
        result = await self.db.execute(stmt)
        team = result.scalar_one_or_none()

        if not team:
            raise NotFoundError("Team", team_id)

        return team

    async def list_teams(
        self,
        project_id: uuid.UUID,
        is_default: Optional[bool] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[Team], int]:
        """
        List teams for a project.
        
        Args:
            project_id: Project ID
            is_default: Filter by default status
            limit: Number of teams to return
            offset: Number of teams to skip
            
        Returns:
            Tuple of (teams, total_count)
        """
        # Build base query
        conditions = [
            Team.project_id == project_id,
            Team.deleted_at.is_(None),
        ]

        if is_default is not None:
            conditions.append(Team.is_default == is_default)

        # Get total count
        count_stmt = select(func.count(Team.id)).where(and_(*conditions))
        count_result = await self.db.execute(count_stmt)
        total_count = count_result.scalar()

        # Get teams
        stmt = (
            select(Team)
            .options(
                selectinload(Team.llm_provider),
                selectinload(Team.agents).selectinload(Agent.tools),
                selectinload(Team.agents).selectinload(Agent.collections),
                selectinload(Team.agents).selectinload(Agent.llm_provider),
            )
            .where(and_(*conditions))
            .order_by(Team.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(stmt)
        teams = result.scalars().all()

        return list(teams), total_count

    async def get_default_team(self, project_id: uuid.UUID) -> Team:
        """Retrieve the default team for a project."""

        stmt = (
            select(Team)
            .where(
                and_(
                    Team.project_id == project_id,
                    Team.deleted_at.is_(None),
                    Team.is_default.is_(True),
                )
            )
            .limit(1)
        )
        result = await self.db.execute(stmt)
        team = result.scalar_one_or_none()

        if not team:
            raise NotFoundError(
                "Team",
                details={"reason": "Default team not configured for project"},
            )

        return team

    async def get_unassigned_agents(self, project_id: uuid.UUID) -> List[Agent]:
        """Retrieve agents in a project that are not assigned to any team."""

        stmt = (
            select(Agent)
            .options(
                selectinload(Agent.tools),
                selectinload(Agent.collections),
                selectinload(Agent.team),
                selectinload(Agent.llm_provider),
            )
            .where(
                and_(
                    Agent.project_id == project_id,
                    Agent.team_id.is_(None),
                    Agent.deleted_at.is_(None),
                )
            )
            .order_by(Agent.created_at.desc())
        )
        result = await self.db.execute(stmt)
        agents = list(result.scalars().all())

        if not agents:
            return []

        from app.services.agent_service import AgentService

        agent_service = AgentService(self.db)
        agents_with_collections = await agent_service.enrich_agents_with_collection_data(
            agents, project_id
        )

        enriched_agents = await agent_service.enrich_agents_with_tool_details(
            agents_with_collections, project_id
        )

        return enriched_agents

    async def update_team(
        self, project_id: uuid.UUID, team_id: uuid.UUID, team_data: TeamUpdate
    ) -> Team:
        """
        Update a team.
        
        Args:
            project_id: Project ID
            team_id: Team ID
            team_data: Team update data
            
        Returns:
            Updated team
            
        Raises:
            NotFoundError: If team not found
            ConflictError: If trying to set default when another default exists
        """
        # Get existing team
        team = await self.get_team(project_id, team_id)

        # Check default team constraint
        if team_data.is_default is True and not team.is_default:
            await self._ensure_no_default_team_exists(project_id, exclude_team_id=team_id)

        # Update fields
        update_data = team_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(team, field, value)

        await self.db.commit()
        await self.db.refresh(team)
        return team

    async def delete_team(self, project_id: uuid.UUID, team_id: uuid.UUID) -> None:
        """
        Soft delete a team.
        
        Args:
            project_id: Project ID
            team_id: Team ID
            
        Raises:
            NotFoundError: If team not found
        """
        team = await self.get_team(project_id, team_id)
        team.soft_delete()
        await self.db.commit()

    async def _ensure_no_default_team_exists(
        self, project_id: uuid.UUID, exclude_team_id: Optional[uuid.UUID] = None
    ) -> None:
        """
        Ensure no default team exists for the project.
        
        Args:
            project_id: Project ID
            exclude_team_id: Team ID to exclude from check
            
        Raises:
            ConflictError: If default team already exists
        """
        conditions = [
            Team.project_id == project_id,
            Team.is_default == True,  # noqa: E712
            Team.deleted_at.is_(None),
        ]

        if exclude_team_id:
            conditions.append(Team.id != exclude_team_id)

        stmt = select(Team).where(and_(*conditions))
        result = await self.db.execute(stmt)
        existing_default = result.scalar_one_or_none()

        if existing_default:
            raise ConflictError(
                "Default team already exists for this project",
                "Team",
                {"existing_default_team_id": str(existing_default.id)},
            )
