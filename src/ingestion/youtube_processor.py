"""YouTube video processor - converts videos to PDF-like structure for existing pipeline."""
from __future__ import annotations
import os
import json
import subprocess
from typing import Dict, List, Optional, Any
from pathlib import Path
import tempfile
import re

try:
    import yt_dlp
except ImportError:
    raise ImportError("yt-dlp not installed. Run: pip install yt-dlp")

try:
    from openai import OpenAI
except ImportError:
    raise ImportError("openai not installed. Run: pip install openai")


class YouTubeProcessor:
    """
    Process YouTube videos into the same format as PDFs.

    Reuses existing components:
    - ImageProcessor for screenshots
    - DocumentSummarizer for chapter detection
    - EmbeddingGenerator for embeddings
    - HierarchyBuilderV2 for structure

    Key concept: Treat videos as "time-based PDFs"
    - 1 page = 1 minute of video
    - Screenshots = images
    - Transcript segments = text chunks
    - Chapters = sections
    """

    def __init__(self, output_dir: Optional[str] = None):
        """Initialize YouTube processor."""
        self.output_dir = output_dir or tempfile.gettempdir() + '/youtube'
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)

        self.client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

        # Verify ffmpeg is available
        try:
            subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError("ffmpeg not found. Please install ffmpeg.")

    def extract_youtube_id(self, url: str) -> str:
        """Extract YouTube video ID from URL."""
        patterns = [
            r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
            r'(?:embed\/)([0-9A-Za-z_-]{11})',
            r'^([0-9A-Za-z_-]{11})$'
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        raise ValueError(f"Could not extract YouTube ID from URL: {url}")

    def download_video(self, url: str) -> Dict[str, Any]:
        """
        Download YouTube video and extract metadata.

        Returns:
            {
                'youtube_id': str,
                'title': str,
                'duration': int (seconds),
                'channel': str,
                'description': str,
                'thumbnail': str (URL),
                'filepath': str (local path to video),
                'playlist_id': Optional[str],
                'playlist_index': Optional[int]
            }
        """
        print(f"📥 Downloading YouTube video: {url}")

        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': f'{self.output_dir}/%(id)s.%(ext)s',
            'quiet': False,
            'no_warnings': False,
            # Download subtitles if available (can help with transcription)
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitlesformat': 'vtt',
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

        # Extract playlist info if available
        playlist_id = info.get('playlist_id')
        playlist_index = info.get('playlist_index')

        result = {
            'youtube_id': info['id'],
            'title': info['title'],
            'duration': info['duration'],
            'channel': info.get('channel', info.get('uploader', 'Unknown')),
            'description': info.get('description', ''),
            'thumbnail': info.get('thumbnail', ''),
            'filepath': f"{self.output_dir}/{info['id']}.mp4",
            'playlist_id': playlist_id,
            'playlist_index': playlist_index,
            'upload_date': info.get('upload_date'),
            'view_count': info.get('view_count'),
        }

        print(f"✓ Downloaded: {result['title']} ({result['duration']}s)")
        return result

    def extract_audio(self, video_path: str) -> str:
        """
        Extract audio track from video for transcription.

        Outputs 16kHz mono WAV (optimal for Whisper API).
        """
        audio_path = video_path.replace('.mp4', '.wav')

        print(f"🔊 Extracting audio: {video_path}")

        cmd = [
            'ffmpeg',
            '-i', video_path,
            '-vn',  # No video
            '-acodec', 'pcm_s16le',  # WAV format
            '-ar', '16000',  # 16kHz sample rate
            '-ac', '1',  # Mono
            '-y',  # Overwrite
            audio_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise RuntimeError(f"Audio extraction failed: {result.stderr}")

        print(f"✓ Audio extracted: {audio_path}")
        return audio_path

    def transcribe(self, audio_path: str, youtube_id: str) -> List[Dict]:
        """
        Transcribe audio using OpenAI Whisper API.

        Returns segments with timestamps:
            [{
                'segment_index': int,
                'start_time': float,
                'end_time': float,
                'text': str
            }, ...]
        """
        print(f"🎤 Transcribing with Whisper API...")

        # Check file size (Whisper API limit is 25MB)
        file_size = os.path.getsize(audio_path)
        if file_size > 25 * 1024 * 1024:
            print(f"⚠️  Audio file too large ({file_size / 1024 / 1024:.1f}MB). Compressing...")
            audio_path = self._compress_audio(audio_path)

        with open(audio_path, 'rb') as audio_file:
            transcript = self.client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="verbose_json",
                timestamp_granularities=["segment"]
            )

        segments = []
        for i, seg in enumerate(transcript.segments):
            segments.append({
                'segment_index': i,
                'start_time': seg['start'],
                'end_time': seg['end'],
                'text': seg['text'].strip()
            })

        print(f"✓ Transcribed {len(segments)} segments")
        return segments

    def _compress_audio(self, audio_path: str) -> str:
        """Compress audio file to fit Whisper API limit."""
        compressed_path = audio_path.replace('.wav', '_compressed.wav')

        cmd = [
            'ffmpeg',
            '-i', audio_path,
            '-ar', '16000',
            '-ac', '1',
            '-b:a', '64k',  # Lower bitrate
            '-y',
            compressed_path
        ]

        subprocess.run(cmd, capture_output=True, check=True)
        return compressed_path

    def extract_screenshots(
        self,
        video_path: str,
        youtube_id: str,
        method: str = 'scene',
        interval: int = 30
    ) -> List[Dict]:
        """
        Extract key frames from video.

        Methods:
        - 'scene': Detect scene changes (best for presentations/slides)
        - 'interval': Fixed interval in seconds (best for demos)
        - 'hybrid': Combination of both

        Returns:
            [{
                'timestamp': float,
                'filepath': str,
                'frame_index': int
            }, ...]
        """
        print(f"📸 Extracting screenshots ({method} method)...")

        screenshots_dir = f"{self.output_dir}/screenshots_{youtube_id}"
        Path(screenshots_dir).mkdir(exist_ok=True)

        screenshots = []

        if method == 'scene':
            screenshots = self._extract_scene_screenshots(video_path, screenshots_dir)

        elif method == 'interval':
            screenshots = self._extract_interval_screenshots(video_path, screenshots_dir, interval)

        elif method == 'hybrid':
            # Combine both methods and deduplicate
            scene_shots = self._extract_scene_screenshots(video_path, screenshots_dir)
            interval_shots = self._extract_interval_screenshots(
                video_path,
                screenshots_dir,
                interval=60  # Less frequent for hybrid
            )

            # Merge and sort by timestamp
            all_shots = scene_shots + interval_shots
            all_shots.sort(key=lambda x: x['timestamp'])

            # Deduplicate (remove screenshots within 5 seconds of each other)
            screenshots = []
            last_timestamp = -10
            for shot in all_shots:
                if shot['timestamp'] - last_timestamp > 5:
                    screenshots.append(shot)
                    last_timestamp = shot['timestamp']

        print(f"✓ Extracted {len(screenshots)} screenshots")
        return screenshots

    def _extract_scene_screenshots(self, video_path: str, output_dir: str) -> List[Dict]:
        """Extract screenshots at scene changes."""
        # Use ffmpeg scene detection
        output_pattern = f"{output_dir}/scene_%04d.png"

        cmd = [
            'ffmpeg',
            '-i', video_path,
            '-vf', 'select=gt(scene\\,0.3)',  # Scene change threshold
            '-vsync', 'vfr',
            '-frame_pts', '1',
            '-y',
            output_pattern
        ]

        subprocess.run(cmd, capture_output=True)

        # Get all extracted frames
        import glob
        frame_files = sorted(glob.glob(f"{output_dir}/scene_*.png"))

        # Get timestamps for each frame
        screenshots = []
        for i, filepath in enumerate(frame_files):
            # Get timestamp using ffprobe
            timestamp = self._get_frame_timestamp(video_path, i)

            screenshots.append({
                'timestamp': timestamp,
                'filepath': filepath,
                'frame_index': i,
                'extraction_method': 'scene'
            })

        return screenshots

    def _extract_interval_screenshots(
        self,
        video_path: str,
        output_dir: str,
        interval: int = 30
    ) -> List[Dict]:
        """Extract screenshots at fixed intervals."""
        output_pattern = f"{output_dir}/interval_%04d.png"

        # Extract 1 frame every N seconds
        cmd = [
            'ffmpeg',
            '-i', video_path,
            '-vf', f'fps=1/{interval}',  # 1 frame per interval
            '-y',
            output_pattern
        ]

        subprocess.run(cmd, capture_output=True)

        # Get all extracted frames
        import glob
        frame_files = sorted(glob.glob(f"{output_dir}/interval_*.png"))

        screenshots = []
        for i, filepath in enumerate(frame_files):
            timestamp = i * interval

            screenshots.append({
                'timestamp': float(timestamp),
                'filepath': filepath,
                'frame_index': i,
                'extraction_method': 'interval'
            })

        return screenshots

    def _get_frame_timestamp(self, video_path: str, frame_index: int) -> float:
        """Get timestamp for specific frame index."""
        # For simplicity, estimate based on frame rate
        # More accurate: use ffprobe to get exact timestamp
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=r_frame_rate',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            video_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        fps_str = result.stdout.strip()

        if '/' in fps_str:
            num, den = map(float, fps_str.split('/'))
            fps = num / den
        else:
            fps = float(fps_str)

        return frame_index / fps

    def detect_chapters(
        self,
        segments: List[Dict],
        title: str,
        max_chapters: int = 10
    ) -> List[Dict]:
        """
        Use LLM to detect topic changes and create chapters.

        Returns:
            [{
                'title': str,
                'start_time': float,
                'end_time': float,
                'key_concepts': List[str]
            }, ...]
        """
        print(f"📚 Detecting chapters with LLM...")

        # Sample segments if too many (LLM context limit)
        if len(segments) > 100:
            # Take every Nth segment
            step = len(segments) // 100
            sampled_segments = segments[::step]
        else:
            sampled_segments = segments

        # Build transcript with timestamps
        transcript_lines = []
        for seg in sampled_segments:
            timestamp = f"{int(seg['start_time'] // 60)}:{int(seg['start_time'] % 60):02d}"
            transcript_lines.append(f"[{timestamp}] {seg['text']}")

        full_transcript = '\n'.join(transcript_lines)

        prompt = f"""Analyze this video transcript from "{title}".

Identify the major topic changes and create chapters (max {max_chapters}).

Transcript:
{full_transcript}

Return ONLY valid JSON (no markdown, no explanation):
{{
  "chapters": [
    {{
      "title": "Introduction to Topic",
      "start_time": 0,
      "end_time": 120,
      "key_concepts": ["concept1", "concept2"]
    }}
  ]
}}
"""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.3
            )

            result = json.loads(response.choices[0].message.content)
            chapters = result.get('chapters', [])

            print(f"✓ Detected {len(chapters)} chapters")
            return chapters

        except Exception as e:
            print(f"⚠️  Chapter detection failed: {e}. Creating default chapter.")
            # Fallback: single chapter
            return [{
                'title': title,
                'start_time': 0,
                'end_time': segments[-1]['end_time'] if segments else 0,
                'key_concepts': []
            }]

    def convert_to_pdf_format(
        self,
        metadata: Dict,
        segments: List[Dict],
        screenshots: List[Dict],
        chapters: List[Dict]
    ) -> Dict:
        """
        Convert video data to PDF-like format for existing pipeline.

        This is the KEY FUNCTION that allows reuse of PDF processing code!

        Returns structure compatible with DoclingSDKParser output:
            {
                'pages': [...],  # Time-based "pages"
                'pictures': [...],  # Screenshots
                'hierarchy': {...}  # Video structure
            }
        """
        duration = metadata['duration']
        page_duration = 60  # 1 page = 1 minute

        # Create time-based pages
        pages = []
        for page_num in range(0, int(duration / page_duration) + 1):
            start_time = page_num * page_duration
            end_time = min((page_num + 1) * page_duration, duration)

            # Get segments in this time range
            page_segments = [
                s for s in segments
                if start_time <= s['start_time'] < end_time
            ]

            if page_segments:
                elements = []
                for seg in page_segments:
                    elements.append({
                        'type': 'text',
                        'text': seg['text'],
                        'timestamp_start': seg['start_time'],
                        'timestamp_end': seg['end_time'],
                        'label': f"segment-{seg['segment_index']}",
                        'page': page_num,
                        # Fake bbox (not applicable for videos)
                        'bbox': {'l': 0, 't': 0, 'r': 1, 'b': 1}
                    })

                pages.append({
                    'page_no': page_num,
                    'start_time': start_time,
                    'end_time': end_time,
                    'elements': elements
                })

        # Convert screenshots to picture format
        pictures = []
        for screenshot in screenshots:
            pictures.append({
                'timestamp': screenshot['timestamp'],
                'filepath': screenshot['filepath'],
                'page_no': int(screenshot['timestamp'] / page_duration),
                'extraction_method': screenshot.get('extraction_method', 'unknown')
            })

        # Build hierarchy (similar to PDF sections)
        hierarchy = {
            'source_type': 'youtube',
            'youtube_id': metadata['youtube_id'],
            'title': metadata['title'],
            'duration': duration,
            'channel': metadata['channel'],
            'description': metadata['description'],
            'chapters': chapters,
            'total_segments': len(segments),
            'total_screenshots': len(screenshots),
            'total_pages': len(pages)
        }

        return {
            'source_type': 'youtube',
            'metadata': metadata,
            'pages': pages,
            'pictures': pictures,
            'hierarchy': hierarchy,
            'segments': segments  # Keep raw segments for chunking
        }

    def cleanup(self, youtube_id: str):
        """Remove temporary files after processing."""
        import shutil

        files_to_remove = [
            f"{self.output_dir}/{youtube_id}.mp4",
            f"{self.output_dir}/{youtube_id}.wav",
            f"{self.output_dir}/{youtube_id}_compressed.wav",
        ]

        for filepath in files_to_remove:
            if os.path.exists(filepath):
                os.remove(filepath)

        # Remove screenshots directory
        screenshots_dir = f"{self.output_dir}/screenshots_{youtube_id}"
        if os.path.exists(screenshots_dir):
            shutil.rmtree(screenshots_dir)

        print(f"🧹 Cleaned up temporary files for {youtube_id}")
