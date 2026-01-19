import os
from datetime import datetime
import streamlit as st
from core.config import EPISODE_COMPLETION_THRESHOLD
from core.utils import format_seconds_to_human_readable
from ui.utils import open_file_dialog, open_in_file_manager, open_file_in_default_app
from core.settings import save_settings

# Constants for UI
DRIVER_DEFAULTS = {
    "mpv_native": "mpv",
    "ipc": "celluloid",
    "vlc_rc": "vlc"
}

@st.dialog("Edit Metadata")
def edit_metadata_dialog():
    """Modal dialog for editing session metadata."""
    modal_data = st.session_state.get('edit_modal_session')
    if not modal_data:
        st.rerun()
        return
    
    session = modal_data['session']
    session_id = modal_data['session_id']
    display_name = modal_data['display_name']
    current_season = modal_data['current_season']
    path = modal_data['path']
    library_service = modal_data['library_service']
    
    # Title input
    new_title = st.text_input("Title", value=display_name, key="modal_title")
    
    # Season number
    new_season = st.number_input(
        "Season Number", 
        min_value=1, 
        value=current_season if current_season is not None else 1, 
        key="modal_season"
    )
    
    # Save and Refresh buttons
    col_save, col_refresh = st.columns(2)
    with col_save:
        if st.button("Save", key="modal_save", use_container_width=True, type="primary"):
            library_service.update_session_metadata(
                path, 
                clean_title=new_title, 
                season_number=new_season, 
                is_user_locked_title=True
            )
            session.metadata.clean_title = new_title
            session.metadata.season_number = new_season
            st.session_state.pop('edit_modal_session', None)
            st.rerun()
    
    with col_refresh:
        if st.button("Refresh", key="modal_refresh", use_container_width=True, help="Refresh from TMDB"):
            library_service.refresh_metadata(session)
            st.session_state.pop('edit_modal_session', None)
            st.rerun()
    
    st.markdown("---")
    st.markdown("**Fetch by TMDB ID**")
    
    # TMDB ID input
    current_tmdb_id = session.metadata.tmdb_id or ""
    new_tmdb_id = st.text_input(
        "TMDB ID", 
        value=str(current_tmdb_id) if current_tmdb_id else "",
        key="modal_tmdb_id",
        placeholder="e.g., 550 for Fight Club"
    )
    
    # Media type selector
    col_type1, col_type2 = st.columns(2)
    with col_type1:
        is_movie = st.button("Movie", key="modal_movie", use_container_width=True,
                            type="primary" if st.session_state.get('modal_media_type', 'movie') == 'movie' else "secondary")
        if is_movie:
            st.session_state['modal_media_type'] = 'movie'
    with col_type2:
        is_tv = st.button("TV Show", key="modal_tv", use_container_width=True,
                         type="primary" if st.session_state.get('modal_media_type') == 'tv' else "secondary")
        if is_tv:
            st.session_state['modal_media_type'] = 'tv'
    
    media_type = st.session_state.get('modal_media_type', 'movie')
    
    if st.button("Fetch by ID", key="modal_fetch", use_container_width=True):
        if new_tmdb_id and new_tmdb_id.isdigit():
            library_service.fetch_metadata_by_id(session, int(new_tmdb_id), media_type)
            st.session_state.pop('edit_modal_session', None)
            st.rerun()
        else:
            st.error("Please enter a valid TMDB ID")
    
    # Close button at the bottom
    if st.button("Close", key="modal_close", use_container_width=True):
        st.session_state.pop('edit_modal_session', None)
        st.rerun()


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
        
        # Open config in default editor
        if st.button("Open Config", use_container_width=True):
            import pathlib
            config_path = pathlib.Path(__file__).parent.parent / "core" / "config.py"
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

def render_stats_page(stats_service, library_service):
    """Renders the statistics dashboard page."""
    st.markdown('<div class="main-header">Stats.</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Your viewing analytics and watch history</div>', unsafe_allow_html=True)
    
    stats = stats_service.get_all_stats()
    
    watch_time_str = stats_service.format_watch_time(stats.total_watch_time)
    weekly_time_str = stats_service.format_watch_time(stats.weekly_watch_time)
    daily_avg_str = stats_service.format_watch_time(stats.daily_average)
    
    metrics_html = f'''<div class="stats-grid">
<div class="stat-card">
<div class="stat-value">{stats.library_size}</div>
<div class="stat-label">Library Items</div>
</div>
<div class="stat-card">
<div class="stat-value">{weekly_time_str if weekly_time_str else "0s"}</div>
<div class="stat-label">This Week</div>
</div>
<div class="stat-card">
<div class="stat-value">{daily_avg_str if daily_avg_str else "0s"}</div>
<div class="stat-label">Daily Avg</div>
</div>
<div class="stat-card">
<div class="stat-value">{watch_time_str if watch_time_str else "0s"}</div>
<div class="stat-label">Total Watch Time</div>
</div>
</div>'''
    st.markdown(metrics_html, unsafe_allow_html=True)
    
    st.markdown("<div style='height: 2rem'></div>", unsafe_allow_html=True)
    
    st.markdown('<div class="section-header">Activity</div>', unsafe_allow_html=True)
    
    current_streak = stats_service.get_current_streak(stats.watch_streak) if stats.watch_streak else 0
    today = datetime.now().date()
    start_date = today - datetime.timedelta(days=364) if hasattr(datetime, 'timedelta') else today # Safety check
    # Actually just use timedelta from datetime
    from datetime import timedelta
    start_date = today - timedelta(days=364)

    calendar_html = f'''<div class="streak-container">
<div class="streak-info">
<span class="streak-count">{current_streak}</span>
<span class="streak-label">day streak</span>
</div>
<div class="streak-calendar">'''
    
    current_date = start_date
    while current_date.weekday() != 6:
        current_date -= timedelta(days=1)
    
    for week in range(53):
        calendar_html += '<div class="streak-week">'
        for day in range(7):
            date_str = current_date.isoformat()
            minutes = stats.watch_streak.get(date_str, 0) if stats.watch_streak else 0
            level = stats_service.get_streak_level(minutes)
            tooltip = f"{date_str}: {minutes}m" if minutes else date_str
            calendar_html += f'<div class="streak-day level-{level}" title="{tooltip}"></div>'
            current_date += timedelta(days=1)
        calendar_html += '</div>'
    
    calendar_html += '</div></div>'
    st.markdown(calendar_html, unsafe_allow_html=True)
    
    st.markdown("<div style='height: 2rem'></div>", unsafe_allow_html=True)
    
    col_left, col_right = st.columns(2, gap="medium")
    
    with col_left:
        st.markdown('<div class="section-header">Most Watched</div>', unsafe_allow_html=True)
        if stats.most_watched and any(t[1] > 0 for t in stats.most_watched):
            max_time = max(t[1] for t in stats.most_watched) if stats.most_watched else 1
            rankings_html = '<div class="rankings-list">'
            for i, (title, watch_time) in enumerate(stats.most_watched[:5], 1):
                if watch_time <= 0: continue
                progress_pct = (watch_time / max_time * 100) if max_time > 0 else 0
                time_str = stats_service.format_watch_time(watch_time)
                rankings_html += f'''<div class="ranking-item">
<div class="ranking-header">
<span class="ranking-position">{i}</span>
<span class="ranking-title">{title}</span>
<span class="ranking-time">{time_str}</span>
</div>
<div class="ranking-bar-bg"><div class="ranking-bar" style="width: {progress_pct}%"></div></div>
</div>'''
            rankings_html += '</div>'
            st.markdown(rankings_html, unsafe_allow_html=True)
        else:
            st.markdown('<div class="empty-state">No watch data recorded yet</div>', unsafe_allow_html=True)
    with col_right:
        st.markdown('<div class="section-header">Viewing Patterns</div>', unsafe_allow_html=True)
        
        if stats.viewing_patterns and any(v > 0 for v in stats.viewing_patterns.values()):
            max_minutes = max(stats.viewing_patterns.values())
            
            pattern_html = '<div class="patterns-container"><div class="viewing-patterns">'
            
            for i in range(24):
                hour = (6 + i) % 24
                minutes = stats.viewing_patterns.get(hour, 0)
                height_pct = (minutes / max_minutes * 100) if max_minutes > 0 else 0
                
                # --- LABEL LOGIC CHANGED HERE ---
                # Only show label if i is 0 (6am), 6 (12pm), 12 (6pm), or 18 (12am)
                if i % 6 == 0:
                    display_hour = hour if hour <= 12 else hour - 12
                    if display_hour == 0: display_hour = 12
                    
                    suffix = ""
                    if hour == 12: suffix = "pm"
                    elif hour == 0: suffix = "am"
                    elif hour == 6: suffix = "am" 
                    elif hour == 18: suffix = "pm"

                    label_text = f"{display_hour}{suffix}"
                else:
                    # Keep the div but leave text empty to maintain spacing alignment
                    label_text = "&nbsp;" 

                pattern_html += f'''
                <div class="pattern-col" title="{hour:02d}:00 - {int(minutes)}m">
                    <div class="bar-wrapper">
                        <div class="pattern-bar" style="height: {height_pct}%"></div>
                    </div>
                    <div class="pattern-label">{label_text}</div>
                </div>'''
                
            pattern_html += '</div></div>'
            st.markdown(pattern_html, unsafe_allow_html=True)
        else:
            st.markdown('<div class="empty-state">No viewing pattern data yet</div>', unsafe_allow_html=True)
            
    st.markdown("<div style='height: 2rem'></div>", unsafe_allow_html=True)
    st.markdown('<div class="section-header">Recent History</div>', unsafe_allow_html=True)
    
    if stats.recent_history:
        history_html = '<div class="history-list">'
        sessions = library_service.get_all_sessions()
        current_date_tracker = None
        
        for event in stats.recent_history:
            event_date = event.started_at.date()
            if current_date_tracker != event_date:
                date_str = "Today" if event_date == datetime.now().date() else event_date.strftime("%B %d, %Y")
                history_html += f'<div class="history-date-header">{date_str}</div>'
                current_date_tracker = event_date
            
            title = sessions.get(event.session_id, {}).metadata.clean_title if event.session_id in sessions else "Unknown Title"
            duration_str = stats_service.format_watch_time((event.ended_at - event.started_at).total_seconds())
            time_str = event.started_at.strftime("%I:%M %p")
            
            history_html += f'''<div class="history-item">
<div class="history-time">{time_str}</div>
<div class="history-details">
<div class="history-title">{title}</div>
<div class="history-meta">Duration: {duration_str}</div>
</div>
</div>'''
        history_html += '</div>'
        st.markdown(history_html, unsafe_allow_html=True)
    else:
        st.markdown('<div class="empty-state">No recent watch history</div>', unsafe_allow_html=True)


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
