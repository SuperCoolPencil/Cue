import streamlit as st
from datetime import datetime, timedelta

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
