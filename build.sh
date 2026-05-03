"""
FFmpeg clipping pipeline.

Responsibilities:
1. Download the YouTube video (yt-dlp)
2. Extract transcript (yt-dlp --write-auto-sub or whisper)
3. Cut clips to 9:16 vertical format with captions burned in
4. Return file paths for each clip
"""

import asyncio
import os
import json
import shutil
from pathlib import Path
from typing import Optional
from app.config import get_settings

settings = get_settings()


class ClippingService:
    def __init__(self):
        self.ffmpeg     = settings.ffmpeg_path
        self.output_dir = Path(settings.clips_output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_jobs)

    # ── Public API ────────────────────────────────────────────────────────────

    async def process_video(
        self,
        youtube_video_id: str,
        clip_suggestions: list[dict],       # from ScoringService
        caption_style: str = "auto",        # "none" | "auto" | "viral"
    ) -> list[dict]:
        """
        Download video, extract each clip, return [{clip_id, file_path, ...}].
        Runs under a semaphore to cap concurrent ffmpeg jobs.
        """
        async with self._semaphore:
            video_path = await self._download_video(youtube_video_id)
            transcript = await self._extract_transcript(youtube_video_id)

            results = []
            for i, suggestion in enumerate(clip_suggestions):
                out_path = self.output_dir / f"{youtube_video_id}_clip{i+1}.mp4"
                await self._cut_clip(
                    src=video_path,
                    dst=out_path,
                    start=suggestion["start_second"],
                    end=suggestion["end_second"],
                    caption_style=caption_style,
                    segment_text=self._get_segment_text(
                        transcript, suggestion["start_second"], suggestion["end_second"]
                    ),
                )
                results.append({
                    "index":     i,
                    "file_path": str(out_path),
                    **suggestion,
                })

            # Clean up the raw download to save disk
            video_path.unlink(missing_ok=True)
            return results

    async def get_transcript(self, youtube_video_id: str) -> list[dict]:
        """Public helper to get transcript for scoring before clipping."""
        return await self._extract_transcript(youtube_video_id)

    # ── Download ──────────────────────────────────────────────────────────────

    async def _download_video(self, video_id: str) -> Path:
        out_path = self.output_dir / f"{video_id}.mp4"
        if out_path.exists():
            return out_path

        url = f"https://www.youtube.com/watch?v={video_id}"
        cmd = [
            "yt-dlp",
            "-f", "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]",
            "--merge-output-format", "mp4",
            "-o", str(out_path),
            "--no-playlist",
            url,
        ]
        await self._run(cmd, label=f"download:{video_id}")
        return out_path

    # ── Transcript ────────────────────────────────────────────────────────────

    async def _extract_transcript(self, video_id: str) -> list[dict]:
        """
        Try yt-dlp auto-subtitles first (free, fast).
        Falls back to openai-whisper if subtitles unavailable.
        Returns list of {start, end, text} dicts.
        """
        sub_path = self.output_dir / f"{video_id}.json"
        if sub_path.exists():
            return json.loads(sub_path.read_text())

        url = f"https://www.youtube.com/watch?v={video_id}"
        vtt_path = self.output_dir / f"{video_id}.en.vtt"

        cmd = [
            "yt-dlp",
            "--skip-download",
            "--write-auto-subs",
            "--sub-lang", "en",
            "--sub-format", "vtt",
            "-o", str(self.output_dir / video_id),
            url,
        ]
        await self._run(cmd, label=f"subtitles:{video_id}")

        if vtt_path.exists():
            segments = self._parse_vtt(vtt_path.read_text())
            sub_path.write_text(json.dumps(segments))
            vtt_path.unlink(missing_ok=True)
            return segments

        # Fallback: whisper (requires `pip install openai-whisper`)
        return await self._whisper_transcribe(video_id)

    async def _whisper_transcribe(self, video_id: str) -> list[dict]:
        """Transcribe using local Whisper model."""
        video_path = self.output_dir / f"{video_id}.mp4"
        if not video_path.exists():
            video_path = await self._download_video(video_id)

        # Run whisper in a thread to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        segments = await loop.run_in_executor(None, self._run_whisper, str(video_path))
        return segments

    @staticmethod
    def _run_whisper(video_path: str) -> list[dict]:
        try:
            import whisper
            model = whisper.load_model("base")
            result = model.transcribe(video_path, verbose=False)
            return [
                {"start": s["start"], "end": s["end"], "text": s["text"]}
                for s in result["segments"]
            ]
        except ImportError:
            return []   # whisper not installed — scoring falls back to heuristic

    # ── Clipping ──────────────────────────────────────────────────────────────

    async def _cut_clip(
        self,
        src: Path,
        dst: Path,
        start: float,
        end: float,
        caption_style: str,
        segment_text: Optional[str],
    ) -> None:
        duration = end - start

        # Base filter: crop to 9:16, scale to 1080x1920
        vf = (
            "crop=ih*9/16:ih,"
            "scale=1080:1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2"
        )

        # Burn captions if requested
        if caption_style != "none" and segment_text:
            # Write subtitle file
            srt_path = dst.with_suffix(".srt")
            srt_path.write_text(
                f"1\n00:00:00,000 --> 00:00:{int(duration):02d},000\n{segment_text}\n"
            )
            style = self._caption_style(caption_style)
            vf += f",subtitles='{srt_path}':force_style='{style}'"

        cmd = [
            self.ffmpeg, "-y",
            "-ss", str(start),
            "-i", str(src),
            "-t", str(duration),
            "-vf", vf,
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            str(dst),
        ]
        await self._run(cmd, label=f"clip:{dst.name}")

    @staticmethod
    def _caption_style(style: str) -> str:
        if style == "viral":
            return (
                "FontName=Impact,FontSize=18,PrimaryColour=&H00FFFFFF,"
                "OutlineColour=&H00000000,Outline=3,Bold=1,"
                "Alignment=2,MarginV=80"
            )
        # auto — clean readable
        return (
            "FontName=Arial,FontSize=14,PrimaryColour=&H00FFFFFF,"
            "BackColour=&H80000000,Outline=1,Alignment=2,MarginV=60"
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_vtt(vtt_text: str) -> list[dict]:
        import re
        pattern = re.compile(
            r"(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3})[^\n]*\n(.*?)(?=\n\n|\Z)",
            re.DOTALL,
        )
        def to_secs(ts: str) -> float:
            h, m, rest = ts.split(":")
            s, ms = rest.split(".")
            return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000

        segments = []
        for m in pattern.finditer(vtt_text):
            text = re.sub(r"<[^>]+>", "", m.group(3)).strip()
            if text:
                segments.append({
                    "start": to_secs(m.group(1)),
                    "end":   to_secs(m.group(2)),
                    "text":  text,
                })
        return segments

    @staticmethod
    def _get_segment_text(
        transcript: list[dict], start: float, end: float
    ) -> Optional[str]:
        texts = [
            s["text"] for s in transcript
            if s["start"] >= start and s["end"] <= end
        ]
        return " ".join(texts).strip() or None

    @staticmethod
    async def _run(cmd: list[str], label: str) -> None:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"[{label}] Command failed (exit {proc.returncode}):\n"
                + stderr.decode()[-2000:]
            )
