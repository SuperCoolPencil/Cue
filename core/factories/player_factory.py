from typing import Dict, Any
from core.interfaces import IPlayerDriver
from core.drivers.mpv_driver import MpvDriver
from core.drivers.vlc_driver import VlcDriver
from core.drivers.ipc_driver import PlayerDriver

class PlayerFactory:
    """Factory for creating media player drivers."""
    
    @staticmethod
    def create_player(settings: Dict[str, Any]) -> IPlayerDriver:
        """
        Creates and returns a player driver based on the provided settings.
        """
        player_type = settings.get('player_type', 'mpv_native')
        player_executable = settings.get('player_executable', 'mpv')

        if player_type == 'vlc_rc':
            return VlcDriver()
        elif player_type == 'ipc':
            return PlayerDriver(player_executable)
        else:
            return MpvDriver(player_executable)
