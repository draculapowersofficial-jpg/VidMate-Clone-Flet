import flet as ft
import os
import threading

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

def main(page: ft.Page):
    page.title = "VidMate Next-Gen Portal"
    page.theme_mode = ft.ThemeMode.DARK
    page.scroll = None
    page.padding = 10
    
    # --- AUTOMATIC PATH CONFIGURATION ---
    if os.name == 'posix' and 'ANDROID_ARGUMENT' in os.environ:
        download_path = "/storage/emulated/0/Download/MediaDownloader"
    else:
        download_path = os.path.join(os.path.expanduser("~"), "Downloads", "MediaDownloader")
        
    if not os.path.exists(download_path):
        try: os.makedirs(download_path)
        except: pass

    # --- UI STATE ELEMENT CONTROLS ---
    status_text = ft.Text("Explore trending media or search keywords", size=14, color=ft.Colors.GREY_400)
    url_input = ft.TextField(
        hint_text="Search keywords or paste URL...",
        expand=True,
        text_size=14,
        content_padding=12
    )
    progress_ring = ft.ProgressRing(visible=False, width=20, height=20, stroke_width=2)
    
    trending_grid = ft.GridView(expand=1, runs_count=2, max_extent=250, child_aspect_ratio=0.72, spacing=10, run_spacing=10)
    library_list = ft.ListView(expand=1, spacing=8)

    # --- QUALITY SELECTION BOTTOM SHEET ---
    quality_bs = ft.BottomSheet(
        content=ft.Container(
            padding=20,
            content=ft.Column([
                ft.Text("Select Media Quality", size=18, weight=ft.FontWeight.BOLD),
                ft.Divider(),
                ft.Text("Fetching available resolutions...", id="loading_msg", italic=True),
                ft.ListView(id="format_list", spacing=5, height=250, expand=True)
            ], tight=True)
        )
    )
    page.overlay.append(quality_bs)

    # --- ACTION COMPONENT GENERATORS ---
    def make_media_card(title, author, views, duration, thumbnail, video_url):
        return ft.Container(
            content=ft.Column([
                ft.Image(src=thumbnail, fit=ft.ImageFit.COVER, aspect_ratio=1.77, border_radius=8),
                ft.Text(title, size=13, weight=ft.FontWeight.BOLD, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                ft.Text(f"👤 {author}", size=11, color=ft.Colors.GREY_400, max_lines=1),
                ft.Text(f"👁️ {views} • ⏱️ {duration}", size=10, color=ft.Colors.GREY_500),
                ft.Row([
                    ft.IconButton(ft.Icons.PLAY_ARROW_ROUNDED, icon_color=ft.Colors.BLUE_400, icon_size=20, tooltip="Stream",
                                  on_click=lambda e: process_action(video_url, "stream")),
                    ft.ElevatedButton(
                        text="Download",
                        icon=ft.Icons.DOWNLOAD_ROUNDED,
                        icon_color=ft.Colors.GREEN_400,
                        style=ft.ButtonStyle(padding=5, shape=ft.RoundedRectangleBorder(radius=6)),
                        on_click=lambda e: open_quality_picker(video_url)
                    )
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, spacing=0)
            ], tight=True, spacing=4),
            padding=8,
            bgcolor=ft.Colors.SURFACE_VARIANT,
            border_radius=12,
        )

    # --- OFFLINE LIBRARY MANAGERS ---
    def refresh_library():
        library_list.controls.clear()
        if os.path.exists(download_path):
            files = [f for f in os.listdir(download_path) if f.endswith(('.mp4', '.mp3', '.mkv', '.webm'))]
            if not files:
                library_list.controls.append(ft.Text("No offline downloads found yet.", italic=True, size=13, color=ft.Colors.GREY_500))
            for f in files:
                full_path = os.path.join(download_path, f)
                library_list.controls.append(
                    ft.ListTile(
                        leading=ft.Icon(ft.Icons.PLAY_CIRCLE_FILLED, color=ft.Colors.AMBER_600),
                        title=ft.Text(f, size=13, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                        subtitle=ft.Text("Local Saved Storage File", size=11),
                        on_click=lambda e, p=full_path: page.launch_url(f"file://{p}"),
                        trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT)
                    )
                )
        page.update()

    # --- QUALITY PICKER LOGIC WORKER ---
    def open_quality_picker(url):
        # Open empty sheet with loading text immediately
        loading_text = quality_bs.content.content.controls[2]
        format_list_view = quality_bs.content.content.controls[3]
        loading_text.visible = True
        loading_text.value = "Scanning stream formats..."
        format_list_view.controls.clear()
        quality_bs.open = True
        page.update()

        def fetch_formats():
            try:
                opts = {'nocheckcertificate': True, 'quiet': True}
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    formats = info.get('formats', [])
                    
                    # Track added video resolutions to avoid duplicates in the UI list
                    seen_resolutions = set()
                    
                    # Always provide an optimized MP3 option at the top
                    format_list_view.controls.append(
                        ft.ListTile(
                            leading=ft.Icon(ft.Icons.AUDIOTRACK, color=ft.Colors.PURPLE_400),
                            title=ft.Text("Audio MP3 (High Quality Track)"),
                            on_click=lambda e, f_id="bestaudio": trigger_download(url, f_id, True)
                        )
                    )

                    for f in formats:
                        # Extract clean standard video resolutions (e.g., 360p, 720p, 1080p)
                        res = f.get('height')
                        ext = f.get('ext')
                        if res and res not in seen_resolutions and ext in ['mp4', 'webm']:
                            seen_resolutions.add(res)
                            size_mb = f" (~{int(f['filesize'])/(1024*1024):.1f} MB)" if f.get('filesize') else ""
                            
                            format_list_view.controls.append(
                                ft.ListTile(
                                    leading=ft.Icon(ft.Icons.VIDEO_SETTINGS, color=ft.Colors.GREEN_400),
                                    title=ft.Text(f"Video {res}p ({ext.upper()}){size_mb}"),
                                    on_click=lambda e, f_id=f.get('format_id'): trigger_download(url, f_id, False)
                                )
                            )
                loading_text.visible = False
            except Exception as e:
                loading_text.value = f"Failed to parse formats: {str(e)[:40]}"
            page.update()

        threading.Thread(target=fetch_formats, daemon=True).start()

    def trigger_download(url, format_id, is_audio):
        quality_bs.open = False
        progress_ring.visible = True
        status_text.value = "Starting customized download task..."
        page.update()

        def download_worker():
            try:
                opts = {
                    'outtmpl': os.path.join(download_path, '%(title)s.%(ext)s'),
                    'nocheckcertificate': True,
                    'quiet': True,
                }
                if is_audio:
                    opts.update({
                        'format': 'bestaudio/best',
                        'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}]
                    })
                else:
                    # Request chosen resolution merged automatically with matching audio tracks
                    opts['format'] = f"{format_id}+bestaudio/best"
                
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([url])
                status_text.value = "Custom download stored successfully!"
                refresh_library()
            except Exception as e:
                status_text.value = f"Download error: {str(e)[:40]}"
            progress_ring.visible = False
            page.update()

        threading.Thread(target=download_worker, daemon=True).start()

    # --- CORE EXTRACTION ENGINE BACKGROUND THREADS ---
    def fetch_trends_worker():
        if yt_dlp is None: return
        progress_ring.visible = True
        status_text.value = "Fetching YouTube global trends..."
        page.update()
        
        trending_grid.controls.clear()
        opts = {'extract_flat': 'in_playlist', 'skip_download': True, 'quiet': True, 'nocheckcertificate': True}
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                result = ydl.extract_info("ytsearchdate20:trending music gaming", download=False)
                if 'entries' in result:
                    for entry in result['entries']:
                        if not entry: continue
                        v_id = entry.get('id', '')
                        title = entry.get('title', 'Unknown Title')
                        author = entry.get('uploader', 'Unknown Creator')
                        duration = f"{int(entry.get('duration', 0)) // 60}m" if entry.get('duration') else "Live"
                        view_count = f"{entry.get('view_count', 0):,}" if entry.get('view_count') else "N/A"
                        thumb = f"https://youtube.com{v_id}/mqdefault.jpg" if v_id else "https://placehold.co"
                        v_url = f"https://youtube.com{v_id}"
                        
                        trending_grid.controls.append(
                            make_media_card(title, author, view_count, duration, thumb, v_url)
                        )
            status_text.value = "Trends parsed successfully."
        except Exception as e:
            status_text.value = f"Failed to pull trends: {str(e)[:40]}"
