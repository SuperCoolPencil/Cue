from typing import Dict, Any, Optional
from core.settings import load_settings, DATABASE_PATH
from core.repositories.sqlite_repository import SqliteRepository
from core.factories.player_factory import PlayerFactory
from core.services import LibraryService
from core.stats import StatsService

class AppContext:
    """
    Centralized container for application services and state.
    Provides easy access to core components across the application.
    """
    
    def __init__(self):
        self._settings: Optional[Dict[str, Any]] = None
        self._repository: Optional[SqliteRepository] = None
        self._library_service: Optional[LibraryService] = None
        self._stats_service: Optional[StatsService] = None

    @property
    def settings(self) -> Dict[str, Any]:
        if self._settings is None:
            self._settings = load_settings()
        return self._settings

    @property
    def repository(self) -> SqliteRepository:
        if self._repository is None:
            self._repository = SqliteRepository(DATABASE_PATH)
        return self._repository

    @property
    def library_service(self) -> LibraryService:
        if self._library_service is None:
            player_driver = PlayerFactory.create_player(self.settings)
            self._library_service = LibraryService(self.repository, player_driver)
        return self._library_service

    @property
    def stats_service(self) -> StatsService:
        if self._stats_service is None:
            self._stats_service = StatsService(self.repository)
        return self._stats_service

    def reload_settings(self):
        """Forces a reload of settings and dependent services."""
        self._settings = load_settings()
        # Re-initialize services that depend on settings
        player_driver = PlayerFactory.create_player(self._settings)
        self._library_service = LibraryService(self.repository, player_driver)

# Global singleton instance for easy access
app = AppContext()
