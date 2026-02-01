import os
import streamlit as st
import time

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
    new_title = st.text_input("Title", value=display_name, key=f"modal_title_{session_id}")
    
    # Season number
    new_season = st.number_input(
        "Season Number", 
        min_value=1, 
        value=current_season if current_season is not None else 1, 
        key=f"modal_season_{session_id}"
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
    
    # Subtitles Section
    st.markdown("**Subtitles**")
    
    # Batch Download for Series (Folders)
    if os.path.isdir(path):
        if st.button("⚡ Batch Auto-Download & Sync (All Episodes)", key=f"batch_subs_{session_id}", use_container_width=True):
             with st.status("Processing batch subtitles...", expanded=True) as status:
                def update_log(msg):
                    st.write(msg)
                    
                success, fail, logs = library_service.batch_download_subtitles(session, on_progress=update_log)
                
                if fail == 0:
                    status.update(label=f"Completed! Downloaded {success} subtitles.", state="complete", expanded=False)
                else:
                    status.update(label=f"Finished with {fail} errors. Downloaded {success}.", state="error")
    
    col_sub1, col_sub2 = st.columns([0.7, 0.3])
    
    with col_sub1:
         st.write("Search and download subtitles powered by OpenSubtitles.")
    
    with col_sub2:
        if st.button("Search Subs", key="modal_search_subs", use_container_width=True):
            st.session_state['show_subtitle_modal'] = True
            st.rerun()
            
    # Sync button
    if st.button("🔄 Sync Subtitles (ffsync)", key="modal_sync_subs", use_container_width=True, help="Run ffsync on all subtitles in the folder"):
        with st.spinner("Syncing subtitles... (this may take a minute)"):
            success, msg = library_service.sync_subtitles(session)
            if success:
                st.success(msg)
            else:
                st.error(msg)

    # Subtitle Modal logic
    if st.session_state.get('show_subtitle_modal'):
        subtitle_modal(session, library_service)
        

    st.markdown("---")
    st.markdown("**Fetch by TMDB ID**")
    
    # TMDB ID input
    current_tmdb_id = session.metadata.tmdb_id or ""
    new_tmdb_id = st.text_input(
        "TMDB ID", 
        value=str(current_tmdb_id) if current_tmdb_id else "",
        key=f"modal_tmdb_id_{session_id}",
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
            with st.spinner(f"Fetching {media_type} #{new_tmdb_id} from TMDB..."):
                _, success, message = library_service.fetch_metadata_by_id(session, int(new_tmdb_id), media_type)
            
            if success:
                st.success(message)
                time.sleep(1)  # Brief pause to show success message
                st.session_state.pop('edit_modal_session', None)
                st.rerun()
            else:
                st.error(message)
        else:
            st.error("Please enter a valid TMDB ID")
    
    # Close button at the bottom
    if st.button("Close", key="modal_close", use_container_width=True):
        st.session_state.pop('edit_modal_session', None)
        st.rerun()

def subtitle_modal(session, library_service):
    """Modal specifically for searching and downloading subtitles"""
    
    st.markdown("### Subtitle Search")
    st.write(f"Searching subtitles for: **{session.metadata.clean_title}**")
    
    # Check API Key
    from core.config import OPENSUBTITLES_API_KEY
    if not OPENSUBTITLES_API_KEY:
        st.error("⚠️ OpenSubtitles API Key is missing. Please add it to your .env file.")
        if st.button("Close", key="sub_modal_close_err"):
            st.session_state['show_subtitle_modal'] = False
            st.rerun()
        return

    # Trigger search only once or when requested
    if 'subtitle_results' not in st.session_state:
        with st.spinner("Searching OpenSubtitles..."):
            results = library_service.search_subtitles(session)
            st.session_state['subtitle_results'] = results
            
    results = st.session_state.get('subtitle_results', [])
    
    if not results:
        st.info("No subtitles found.")
    else:
        st.success(f"Found {len(results)} subtitles")
        
        # Display results
        for idx, sub in enumerate(results):
            col1, col2 = st.columns([0.75, 0.25])
            with col1:
                match_badge = "🔥 BEST MATCH" if sub.is_hash_match else ""
                st.markdown(f"**{sub.language}** | {sub.format} | ⬇️ {sub.download_count} {match_badge}")
                st.caption(sub.filename)
            with col2:
                if st.button("Download", key=f"dl_sub_{sub.id}_{idx}", use_container_width=True):
                    with st.spinner("Downloading..."):
                        success, msg = library_service.download_subtitle(session, sub.id)
                        if success:
                            st.toast(f"Subtitle downloaded! ({msg})", icon="✅")
                            # Close modals
                            st.session_state['show_subtitle_modal'] = False
                            # Optional: Clear results for next time
                            del st.session_state['subtitle_results']
                            st.rerun()
                        else:
                            st.error(msg)
                            
    st.markdown("---")
    if st.button("Close", key="sub_modal_close"):
        st.session_state['show_subtitle_modal'] = False
        del st.session_state['subtitle_results']
        st.rerun()
