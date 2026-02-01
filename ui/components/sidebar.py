import os
import streamlit as st
import pathlib
from core.settings import save_settings
from ui.utils import open_file_dialog, open_in_file_manager, open_file_in_default_app

DRIVER_DEFAULTS = {
    "mpv_native": "mpv",
    "ipc": "celluloid",
    "vlc_rc": "vlc"
}

def render_sidebar(settings, current_page):
    """Renders the sidebar navigation and preferences."""
    with st.sidebar:
        if st.button("Library", use_container_width=True, 
                    type="primary" if current_page == 'library' else "secondary"):
            st.session_state.current_page = 'library'
            st.rerun()
        if st.button("Archived", use_container_width=True,
                    type="primary" if current_page == 'archived' else "secondary"):
            st.session_state.current_page = 'archived'
            st.rerun()
        if st.button("Stats", use_container_width=True,
                    type="primary" if current_page == 'stats' else "secondary"):
            st.session_state.current_page = 'stats'
            st.rerun()
        
        st.markdown("---")
        
        # File Operations
        if st.button("Open Folder", use_container_width=True):
            if p := open_file_dialog(select_folder=True):
                st.session_state['pending_play'] = p
                st.session_state.current_page = 'library'
                st.rerun()
                
        if st.button("Open File", use_container_width=True):
            if p := open_file_dialog(select_folder=False):
                st.session_state['pending_play'] = p
                st.session_state.current_page = 'library'
                st.rerun()
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Settings
        with st.expander("Preferences"):
            if 'w_exe' not in st.session_state: 
                st.session_state.w_exe = settings.get('player_executable', 'mpv')
            
            if 'w_mode' not in st.session_state:
                saved_type = settings.get('player_type', 'mpv_native')
                st.session_state.w_mode = 'ipc' if saved_type == 'celluloid_ipc' else saved_type

            def update_driver_path():
                new_mode = st.session_state.w_mode
                st.session_state.w_exe = DRIVER_DEFAULTS.get(new_mode, "")

            st.radio("Driver", ["mpv_native", "ipc", "vlc_rc"], key="w_mode", on_change=update_driver_path)
            st.text_input("Path", key="w_exe")
            
            if st.button("Save", use_container_width=True):
                settings['player_executable'] = st.session_state.w_exe
                settings['player_type'] = st.session_state.w_mode
                save_settings(settings)
                # We need to trigger a context reload in the main app
                st.session_state['context_reload_needed'] = True
                st.rerun()
        
        # OpenSubtitles Account
        from core.providers.subtitle_provider import get_subtitle_provider
        
        with st.expander("OpenSubtitles Account"):
            provider = get_subtitle_provider()
            
            if provider.token:
                user = provider.user_info or {}
                st.write(f"Logged in as: **{user.get('username', 'Unknown')}**")
                # User info usually has 'level' or 'vip' boolean. OpenSubtitles user info structure varies.
                # Just show what we generally have or generic message.
                if isinstance(user, dict):
                     level = user.get('level', 'Free')
                     st.caption(f"Status: {level}")
                
                if st.button("Logout", use_container_width=True):
                    provider.logout()
                    st.rerun()
            else:
                st.caption("Login to increase download limits.")
                username = st.text_input("Username", key="os_user")
                password = st.text_input("Password", type="password", key="os_pass")
                
                if st.button("Login", use_container_width=True):
                    if not username or not password:
                        st.error("Missing credentials")
                    else:
                        success, msg = provider.login(username, password)
                        if success:
                            st.success("Logged in!")
                            st.rerun()
                        else:
                            st.error(msg)
        
        # Open config in default editor
        if st.button("Open Config", use_container_width=True):
            config_path = pathlib.Path(__file__).parent.parent.parent / "core" / "config.py"
            open_file_in_default_app(str(config_path))
                
        if st.button("Quit", type="secondary", use_container_width=True): 
            os._exit(0)

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(
            f"""<a href="https://github.com/SuperCoolPencil/Cue" target="_blank" class="github-link">
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12"></path></svg>
                View on GitHub
            </a>""", 
            unsafe_allow_html=True
        )
