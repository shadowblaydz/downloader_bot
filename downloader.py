import asyncio
import os
import yt_dlp
import logging

logger = logging.getLogger(__name__)

def _download_video_sync(url: str, output_dir: str) -> str:
    # We want a format that combines video and audio, and ideally under 50MB
    ydl_opts = {
        'format': 'bestvideo[ext=mp4][filesize<=50M]+bestaudio[ext=m4a]/best[ext=mp4][filesize<=50M]/best[filesize<=50M]/best',
        'outtmpl': os.path.join(output_dir, '%(id)s.%(ext)s'),
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'extractor_args': {'youtube': ['player_client=ios,web']},
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if 'entries' in info:
            # If it's a playlist, take the first entry (shouldn't happen with noplaylist=True)
            info = info['entries'][0]
        
        filename = ydl.prepare_filename(info)
        
        # Sometimes after merging, the extension changes (e.g., .webm + .m4a -> .mkv)
        # Check if the exact filename exists.
        if not os.path.exists(filename):
            base_name = os.path.splitext(filename)[0]
            for ext in ['.mp4', '.mkv', '.webm', '.flv']:
                if os.path.exists(base_name + ext):
                    return base_name + ext
                    
        return filename

async def download_video(url: str, output_dir: str) -> str:
    """
    Downloads a video from the given URL and saves it to the output directory.
    Returns the path to the downloaded file.
    """
    return await asyncio.to_thread(_download_video_sync, url, output_dir)
