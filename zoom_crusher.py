import subprocess
import time
from pathlib import Path
from datetime import timedelta
import re

def get_video_duration(filepath):
    """Returns video duration in seconds using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(filepath)
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return float(result.stdout.strip())

def detect_audio_start(filepath, silence_threshold="-30dB", silence_duration="0.5", probe_duration="600"):
    """Detects first non-silent audio and returns start time in seconds."""
    cmd = [
        "ffmpeg",
        "-t", probe_duration,  # Only scan first 10 minutes
        "-i", str(filepath),
        "-af", f"silencedetect=noise={silence_threshold}:d={silence_duration}",
        "-f", "null",
        "-"
    ]
    result = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True)
    matches = re.findall(r"silence_end: ([\d\.]+)", result.stderr)
    if matches:
        return float(matches[0])
    return 0.0


def run_ffmpeg_with_progress(input_path, output_path, duration, start_time=0):
    """Runs FFmpeg with progress, optionally skipping initial silence."""
    cmd = [
        "ffmpeg",
        "-hwaccel", "cuda",
        "-ss", str(start_time),
        "-i", str(input_path),
        "-c:v", "hevc_nvenc",
        "-preset", "slow",
        "-rc", "vbr",
        "-cq", "28",
        "-b:v", "800k",
        "-maxrate", "1000k",
        "-bufsize", "2000k",
        "-c:a", "aac",
        "-b:a", "64k",
        "-progress", "pipe:1",
        "-y", str(output_path)
    ]

    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    current_time = 0
    start_wall = time.time()

    for line in process.stdout:
        if "out_time=" in line:
            time_str = line.strip().split('=')[1].split('.')[0]
            h, m, s = map(int, time_str.split(':'))
            current_time = h * 3600 + m * 60 + s
            pct = min(100, (current_time / duration) * 100)

            elapsed = time.time() - start_wall
            if current_time > 0:
                est_total = (elapsed / current_time) * duration
                remaining = est_total - elapsed
                eta = str(timedelta(seconds=int(remaining)))
            else:
                eta = "..."

            print(f"\r{input_path.name}: {pct:.1f}% complete | ETA: {eta}", end='')

    process.wait()
    print(f"\nDone: {output_path.name}")

def should_skip(input_file):
    name = input_file.stem.lower()
    return (
        name.startswith("compressed") or
        name.endswith("compressed") or
        input_file.with_name(f"{input_file.stem}_compressed.mp4").exists()
    )

def compress_all_mp4s():
    script_dir = Path(__file__).resolve().parent
    mp4_files = list(script_dir.glob('*.mp4'))
    if not mp4_files:
        print("No .mp4 files found in the current directory.")
        return

    for input_file in mp4_files:
        if should_skip(input_file):
            print(f"Skipping: {input_file.name}")
            continue

        output_file = input_file.with_name(f"{input_file.stem}_compressed.mp4")
        print(f"Analyzing audio start for: {input_file.name}")
        try:
            audio_start = detect_audio_start(input_file)
            print(f"Trimming to start at: {audio_start:.2f}s")
            duration = get_video_duration(input_file) - audio_start
            run_ffmpeg_with_progress(input_file, output_file, duration, start_time=audio_start)
        except Exception as e:
            print(f"Error processing {input_file.name}: {e}")

if __name__ == "__main__":
    compress_all_mp4s()
