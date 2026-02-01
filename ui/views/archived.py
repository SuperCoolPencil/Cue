import os
import streamlit as st

def render_archived_page(library_service):
    """Renders the archived sessions page with minimal info and unarchive option."""
    st.markdown('<div class="main-header">Archived.</div>', unsafe_allow_html=True)
    
    sessions = library_service.get_all_sessions()
    archived_items = sorted(
        [(sid, s) for sid, s in sessions.items() if s.archived],
        key=lambda x: x[1].playback.timestamp,
        reverse=True
    )
    
    st.markdown(f'<div class="sub-header">{len(archived_items)} archived items</div>', unsafe_allow_html=True)
    
    if not archived_items:
        st.info("📁 No archived items. Use the archive button on a session to move it here.")
        return
    
    for session_id, session in archived_items:
        k_id = hash(session_id)
        display_name = session.metadata.clean_title
        is_folder = os.path.isdir(session.filepath)
        
        # Build badges
        badges = []
        badges.append(f'<span class="badge b-folder">{"SERIES" if is_folder else "MOVIE"}</span>')
        
        if session.metadata.year:
            badges.append(f'<span class="badge b-year">{session.metadata.year}</span>')
        
        current_season = session.metadata.season_number
        if isinstance(current_season, list):
            current_season = current_season[0] if current_season else None
        if current_season:
            badges.append(f'<span class="badge b-season">SEASON {current_season:02d}</span>')
        
        if is_folder:
            series_files = library_service.get_series_files(session)
            if series_files:
                total = len(series_files)
                badges.append(f'<span class="badge b-accent">{total} EPISODES</span>')
        
        with st.container():
            col_info, col_action = st.columns([0.85, 0.15], gap="small")
            
            with col_info:
                html_info = f"""<div class="cue-card archived-card">
<div class="card-header">
<div class="card-title">{display_name}</div>
</div>
<div class="badge-container">{"".join(badges)}</div>
</div>"""
                st.markdown(html_info, unsafe_allow_html=True)
            
            with col_action:
                st.write("")
                if st.button("Unarchive", key=f"unarchive_{k_id}", use_container_width=True):
                    session.archived = False
                    library_service.repository.save_session(session)
                    st.rerun()
        
        st.markdown("<div style='margin-bottom: 12px;'></div>", unsafe_allow_html=True)
