import os
import streamlit as st
from core.app_context import app
from ui.components import render_sidebar, render_card, render_stats_page, edit_metadata_dialog, render_archived_page

# === INITIALIZATION ===
def load_css(file_name=os.path.join(os.path.abspath(os.path.dirname(__file__)), "styles.css")):
    if os.path.exists(file_name):
        with open(file_name) as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

st.set_page_config(
    page_title="Cue", 
    page_icon="⏯️", 
    layout="centered", 
    initial_sidebar_state="expanded"
)

load_css()

# === MAIN ENTRY POINT ===
def main():
    # Handle context reload if settings were changed
    if st.session_state.get('context_reload_needed'):
        app.reload_settings()
        st.session_state.sessions = app.library_service.get_all_sessions()
        del st.session_state['context_reload_needed']

    # State initialization
    if 'sessions' not in st.session_state:
        st.session_state.sessions = app.library_service.get_all_sessions()
    
    def reload_sessions_and_rerun():
        st.session_state.sessions = app.library_service.get_all_sessions()
        st.rerun()

    # Handle Playback Triggers
    if 'pending_play' in st.session_state:
        app.library_service.launch_media(st.session_state.pop('pending_play'))
        reload_sessions_and_rerun()
        
    if 'resume_data' in st.session_state:
        app.library_service.launch_media(st.session_state.pop('resume_data'))
        reload_sessions_and_rerun()

    # Get current page (default to library)
    current_page = st.session_state.get('current_page', 'library')
    
    # Sidebar
    render_sidebar(app.settings, current_page)
    
    # Show Edit Metadata modal if triggered
    if 'edit_modal_session' in st.session_state:
        edit_metadata_dialog()
    
    if current_page == 'stats':
        render_stats_page(app.stats_service, app.library_service)
    elif current_page == 'archived':
        render_archived_page(app.library_service)
    else:
        # Library Page
        st.markdown('<div class="main-header">Cue.</div>', unsafe_allow_html=True)
        
        # Filter out archived sessions for the main library view
        active_sessions = {sid: s for sid, s in st.session_state.sessions.items() if not s.archived}
        st.markdown(f'<div class="sub-header">Resume where you left off • {len(active_sessions)} items</div>', unsafe_allow_html=True)

        query = st.text_input("Search", placeholder="Filter your library...", label_visibility="collapsed")
        
        # Filtering and Sorting
        items = sorted(
            [i for i in active_sessions.items() if query.lower() in str(i[1].metadata.clean_title).lower()],
            key=lambda x: x[1].playback.timestamp, 
            reverse=True
        )

        if not items: 
            st.info("📚 Your library is empty. Click 'Open Folder' or 'Open File' in the sidebar to get started.")
        else: 
            for session_id, session in items: 
                render_card(session_id, session, app.library_service)

if __name__ == "__main__":
    main()
