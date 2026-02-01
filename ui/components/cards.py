import os
import streamlit as st
from core.config import EPISODE_COMPLETION_THRESHOLD
from core.utils import format_seconds_to_human_readable
from ui.utils import open_in_file_manager

def render_card(session_id: str, session, library_service):
    """Renders a single media card with playback info and controls."""
    path = session.filepath
    display_name = session.metadata.clean_title
    pos, dur = session.playback.position, session.playback.duration
    
    is_folder = os.path.isdir(path)
    is_done = (pos / dur > EPISODE_COMPLETION_THRESHOLD) if dur else False
    k_id = hash(session_id)
    
    # Build badges
    badges = []
    badges.append(f'<span class="badge b-folder">{"SERIES" if is_folder else "MOVIE"}</span>')
    
    # Year badge
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
            curr = session.playback.last_played_index + 1
            total = len(series_files)
            badges.append(f'<span class="badge b-accent">EP {curr}/{total}</span>')
    
    if is_done: 
        badges.append('<span class="badge b-success">✓ COMPLETED</span>')
    
    # Rating badge
    rating_html = ""
    if session.metadata.vote_average and session.metadata.vote_average > 0:
        rating = session.metadata.vote_average
        rating_html = f'<span class="rating-badge">★ {rating:.1f}</span>'
    
    # Genres
    genre_html = ""
    if session.metadata.genres:
        genre_tags = "".join([f'<span class="genre-tag">{g}</span>' for g in session.metadata.genres[:3]])
        genre_html = f'<div class="genre-container">{genre_tags}</div>'
    
    # Description preview
    desc_html = ""
    if session.metadata.description:
        desc_preview = session.metadata.description[:120] + "..." if len(session.metadata.description) > 120 else session.metadata.description
        desc_html = f'<div class="description-preview">{desc_preview}</div>'

    with st.container():
        # Layout with optional poster
        if session.metadata.poster_path:
            col_poster, col_info, col_actions = st.columns([0.18, 0.59, 0.23], gap="small")
            
            with col_poster:
                st.markdown(f'''<div class="card-poster">
                    <img src="{session.metadata.poster_path}" alt="Poster" />
                </div>''', unsafe_allow_html=True)
        else:
            col_info, col_actions = st.columns([0.75, 0.25], gap="small")
        
        with col_info:
            # Calculate progress percentage
            progress_pct = (pos / dur * 100) if dur > 0 else 0
            progress_bar_html = ""
            if progress_pct > 0:
                progress_bar_html = f'''<div class="card-progress-container">
                    <div class="card-progress-fill" style="width: {progress_pct}%"></div>
                </div>'''

            html_info = f"""<div class="cue-card">
<div class="card-header">
<div class="card-title">{display_name}</div>
{rating_html}
</div>
<div class="badge-container">{"".join(badges)}</div>
{genre_html}
{desc_html}
<div class="stats-row">
<span>{format_seconds_to_human_readable(pos)} / {format_seconds_to_human_readable(dur)}</span>
<span class="time-remaining">{'Finished' if is_done else f"{format_seconds_to_human_readable(dur - pos)} left in episode"}</span>
</div>
{progress_bar_html}
</div>"""
            st.markdown(html_info, unsafe_allow_html=True)
        
        with col_actions:
            st.write("") 
            
            resume_action = library_service.get_resume_action(session)
            
            if resume_action == "restart_or_next":
                if is_folder and library_service.has_next_episode(session):
                    next_info = library_service.get_next_episode_info(session)
                    if next_info:
                        play_label = f"Next: EP {next_info[0] + 1}"
                else:
                    play_label = "Restart"
            elif resume_action == "show_recap":
                play_label = "Continue (1w+ ago)"
            else:
                play_label = "Replay" if is_done else "Continue"
            
            if st.button(play_label, key=f"play_{k_id}", use_container_width=True):
                st.session_state['resume_data'] = path
                st.rerun()

            c_folder, c_edit, c_del = st.columns([1, 1, 1], gap="small")
            
            with c_folder:
                if st.button("📂", key=f"open_{k_id}", help="Show in File Manager", use_container_width=True):
                    open_in_file_manager(path)

            with c_edit:
                if st.button("✎", key=f"edit_{k_id}", help="Edit Metadata", use_container_width=True):
                    st.session_state['edit_modal_session'] = {
                        'session_id': session_id,
                        'session': session,
                        'display_name': display_name,
                        'current_season': current_season,
                        'path': path,
                        'library_service': library_service
                    }
                    st.rerun()

            with c_del:
                if st.session_state.get('confirm_del') == session_id:
                    if st.button("✓", key=f"y_{k_id}", use_container_width=True, help="Confirm Delete"):
                        library_service.repository.delete_session(session_id)
                        st.session_state.sessions.pop(session_id, None)
                        st.session_state.pop('confirm_del', None)
                        st.rerun()
                else:
                    if st.button("✕", key=f"del_{k_id}", use_container_width=True, help="Remove from Library"):
                        st.session_state['confirm_del'] = session_id
                        st.rerun()
            
            # Archive button on its own row
            if st.button("Archive", key=f"archive_{k_id}", use_container_width=True):
                session.archived = True
                library_service.repository.save_session(session)
                st.rerun()

    st.markdown("<div style='margin-bottom: 12px;'></div>", unsafe_allow_html=True)
