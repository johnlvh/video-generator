# ==============================================================================
# Author       : John | Luong Van Huong
# Created Date : Aug 2026
# Description  : Visual Pipeline Video Generator - Automated image sequence to
#                MP4 rendering engine using FFmpeg and Python.
# License      : MIT
# Repository   : https://github.com/johnlvh/video-generator
# ==============================================================================
import json
import logging
import os
import subprocess
import sys
import tempfile
from typing import Any

from dotenv import load_dotenv

# Load the .env file
load_dotenv()

# Access the variables
CONFIG = os.getenv("CONFIG")
DST_VIDEO = os.getenv("DST_VIDEO")
DEFAULT_WIDTH = int(os.getenv("DEFAULT_WIDTH")) if os.getenv("DEFAULT_WIDTH") else 2560
DEFAULT_HEIGHT = (
    int(os.getenv("DEFAULT_HEIGHT")) if os.getenv("DEFAULT_HEIGHT") else 1440
)
DEFAULT_CRF = int(os.getenv("DEFAULT_CRF")) if os.getenv("DEFAULT_CRF") else 18
DEFAULT_DURATION = (
    float(os.getenv("DEFAULT_DURATION")) if os.getenv("DEFAULT_DURATION") else 1.0
)
MAX_IMAGES = int(os.getenv("MAX_IMAGES")) if os.getenv("MAX_IMAGES") else 1000
# Constants
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s - %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

logger.info(f"DST_VIDEO: {DST_VIDEO}")
logger.info(f"DEFAULT_WIDTH: {DEFAULT_WIDTH}")
logger.info(f"DEFAULT_HEIGHT: {DEFAULT_HEIGHT}")
logger.info(f"DEFAULT_CRF: {DEFAULT_CRF}")
logger.info(f"DEFAULT_DURATION: {DEFAULT_DURATION}")
logger.info(f"MAX_IMAGES: {MAX_IMAGES}")


def check_ffmpeg_installed() -> bool:
    """
    Check if FFmpeg is installed and accessible in PATH.

    Returns:
        bool: True if FFmpeg is installed, False otherwise
    """
    try:
        subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, check=True, timeout=5
        )
        logger.debug("FFmpeg is installed and accessible")
        return True
    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        subprocess.TimeoutExpired,
    ):
        logger.error("FFmpeg is not installed or not in PATH")
        return False


def validate_inputs(dst: str, config_path: str) -> bool:
    """
    Validate input parameters.

    Args:
        dst: Destination video file path
        config_path: Path to configuration file

    Returns:
        bool: True if inputs are valid, False otherwise
    """
    if not dst or not dst.strip():
        logger.error("Destination path cannot be empty")
        return False

    if not config_path or not config_path.strip():
        logger.error("Config path cannot be empty")
        return False

    # Check video extension
    ext = os.path.splitext(dst)[1].lower()
    if ext not in ALLOWED_VIDEO_EXTENSIONS:
        logger.warning(
            f"Unusual video extension '{ext}'. Allowed: {ALLOWED_VIDEO_EXTENSIONS}"
        )
        # Still continue but warn user

    # Check if config file exists
    if not os.path.exists(config_path):
        logger.error(f"Config file '{config_path}' not found")
        return False

    # Check if config file is readable
    if not os.access(config_path, os.R_OK):
        logger.error(f"Config file '{config_path}' is not readable")
        return False

    # Check destination directory exists
    dst_dir = os.path.dirname(dst)
    if dst_dir and not os.path.exists(dst_dir):
        try:
            os.makedirs(dst_dir, exist_ok=True)
            logger.info(f"Created output directory: {dst_dir}")
        except OSError as e:
            logger.error(f"Cannot create output directory '{dst_dir}': {e}")
            return False

    return True


def load_config(config_path: str) -> dict[str, Any] | None:
    """
    Load and parse JSON configuration file.

    Args:
        config_path: Path to JSON configuration file

    Returns:
        Dict containing configuration data, or None if error
    """
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config_data = json.load(f)
        logger.debug(f"Config loaded successfully from {config_path}")
        return config_data
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in config file '{config_path}': {e}")
        return None
    except PermissionError as e:
        logger.error(f"Cannot read config file '{config_path}': {e}")
        return None
    except OSError as e:
        logger.error(f"Error opening config file '{config_path}': {e}")
        return None


def parse_clips(config_data: dict[str, Any]) -> list[tuple[str, float]]:
    """
    Parse and validate image clips from configuration.

    Args:
        config_data: Configuration dictionary

    Returns:
        List of tuples (image_path, duration)
    """
    valid_clips = []

    for key, images_config in config_data.items():
        if not images_config:
            logger.debug(f"Skipping empty config section: {key}")
            continue

        if not isinstance(images_config, list):
            logger.warning(f"Config section '{key}' is not a list, skipping")
            continue

        for idx, item in enumerate(images_config):
            if not isinstance(item, dict):
                logger.warning(f"Item {idx} in section '{key}' is not a dict, skipping")
                continue

            image_path = item.get("img")
            duration_raw = item.get("duration", DEFAULT_DURATION)

            # Validate image path
            if not image_path:
                logger.warning(
                    f"Missing image path in section '{key}', item {idx}, skipping"
                )
                continue

            if not os.path.exists(image_path):
                logger.warning(f"Image '{image_path}' not found, skipping")
                continue

            # Validate and parse duration
            try:
                duration = float(duration_raw)
                if duration <= 0:
                    logger.warning(
                        f"Invalid duration {duration} for '{image_path}', using default {DEFAULT_DURATION}"
                    )
                    duration = DEFAULT_DURATION
            except (TypeError, ValueError):
                logger.warning(
                    f"Invalid duration format '{duration_raw}' for '{image_path}', using default {DEFAULT_DURATION}"
                )
                duration = DEFAULT_DURATION

            valid_clips.append((os.path.abspath(image_path), duration))
            logger.debug(f"Added clip: {image_path} (duration: {duration}s)")
    logger.info(f"Total valid clips found: {len(valid_clips)}")
    # Limit number of images
    if len(valid_clips) > MAX_IMAGES:
        logger.warning(
            f"Too many images ({len(valid_clips)}). Limiting to {MAX_IMAGES}"
        )
        valid_clips = valid_clips[:MAX_IMAGES]

    return valid_clips


def escape_file_path(file_path: str) -> str:
    """
    Escape file path for FFmpeg concat file.

    Args:
        file_path: Original file path

    Returns:
        Escaped file path safe for FFmpeg
    """
    # Replace backslashes with forward slashes for Windows compatibility
    path = file_path.replace("\\", "/")
    # Escape single quotes
    path = path.replace("'", "'\\''")
    # Remove any potential dangerous characters (keep only safe ones)
    # This is a simple approach - for production, consider using json.dumps
    return path


def generate_concat_file(clips: list[tuple[str, float]]) -> str | None:
    """
    Generate FFmpeg concat file from clips.

    Args:
        clips: List of (image_path, duration) tuples

    Returns:
        Path to the generated concat file, or None if error
    """
    if not clips:
        logger.error("No clips provided to generate concat file")
        return None

    try:
        with tempfile.NamedTemporaryFile(
            "w", delete=False, suffix=".txt", encoding="utf-8"
        ) as concat_file:
            concat_file_path = concat_file.name

            for img_path, duration in clips:
                safe_path = escape_file_path(img_path)
                concat_file.write(f"file '{safe_path}'\n")
                concat_file.write(f"duration {duration}\n")

            # FFmpeg requires repeating the last file entry to register its duration
            last_img_path = escape_file_path(clips[-1][0])
            concat_file.write(f"file '{last_img_path}'\n")

            logger.debug(f"Generated concat file: {concat_file_path}")
            return concat_file_path

    except OSError as e:
        logger.error(f"Error creating concat file: {e}")
        return None


def build_ffmpeg_command(
    concat_file_path: str,
    dst: str,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    crf: int = DEFAULT_CRF,
    fps: int | None = None,
    codec: str = "libx264",
    extra_params: list[str] | None = None,
) -> list[str]:
    """
    Build FFmpeg command with specified parameters.

    Args:
        concat_file_path: Path to concat file
        dst: Output video path
        width: Video width
        height: Video height
        crf: CRF value (0-51, lower is better quality)
        fps: Frames per second (optional)
        codec: Video codec
        extra_params: Additional FFmpeg parameters

    Returns:
        FFmpeg command as list of strings
    """
    # Build scale filter
    scale_filter = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
        f"format=yuv420p"
    )

    cmd = [
        "ffmpeg",
        "-y",  # Overwrite output file
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        concat_file_path,
        "-vf",
        scale_filter,
        "-vsync",
        "vfr",
        "-c:v",
        codec,
        "-crf",
        str(crf),
        # "-r", str(fps),  # need to turn off -vsync vfr to turn on fps
    ]

    # Add extra parameters if provided
    if extra_params:
        cmd.extend(extra_params)

    # Add output file
    cmd.append(dst)

    logger.info(f"Built FFmpeg command: {' '.join(cmd)}")
    return cmd


def run_ffmpeg(ffmpeg_cmd: list[str]) -> bool:
    """
    Execute FFmpeg command with progress tracking.

    Args:
        ffmpeg_cmd: FFmpeg command as list of strings

    Returns:
        bool: True if successful, False otherwise
    """
    logger.info("Rendering video with FFmpeg...")
    logger.debug(f"FFmpeg command: {' '.join(ffmpeg_cmd)}")

    try:
        # Use Popen for real-time output
        process = subprocess.Popen(
            ffmpeg_cmd,
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1,
        )

        # Parse and log progress
        frame_count = 0
        for line in process.stderr:
            if "frame=" in line:
                # Extract frame number
                try:
                    frame_str = line.split("frame=")[1].split()[0].strip()
                    if frame_str.isdigit():
                        frame_count = int(frame_str)
                        if frame_count % 30 == 0:  # Log every 30 frames
                            logger.info(f"Rendering frame {frame_count}...")
                except (IndexError, ValueError):
                    pass
            elif "error" in line.lower():
                logger.error(f"FFmpeg error: {line.strip()}")

        # Wait for process to complete
        return_code = process.wait()

        if return_code == 0:
            logger.info("Video saved successfully")
            return True
        else:
            # Get any remaining stderr output
            stderr_output = process.stderr.read() if process.stderr else ""
            logger.error(f"FFmpeg exited with code {return_code}")
            if stderr_output:
                logger.error(f"FFmpeg stderr: {stderr_output}")
            return False

    except subprocess.TimeoutExpired:
        logger.error("FFmpeg process timed out")
        process.kill()
        return False
    except FileNotFoundError:
        logger.error(
            "FFmpeg system binary not found. Please ensure FFmpeg is installed and added to PATH."
        )
        return False
    except ValueError:
        logger.exception("Unexpected error running FFmpeg")
        return False


def create_video_from_config(
    dst: str = "video.mp4",
    config_path: str = "config.json",
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    crf: int = DEFAULT_CRF,
    fps: int | None = None,
    codec: str = "libx264",
    extra_params: list[str] | None = None,
) -> bool:
    """
    Create a video from a configuration file using FFmpeg.

    This function reads a JSON configuration file containing image paths and
    durations, then creates a video by concatenating these images using FFmpeg.

    Args:
        dst (str): Output video file path. Default: "video.mp4"
        config_path (str): Path to JSON configuration file. Default: "config.json"
        width (int): Output video width in pixels. Default: 2560
        height (int): Output video height in pixels. Default: 1440
        crf (int): Constant Rate Factor for video quality (0-51, lower is better).
                  Default: 18 (high quality)
        fps (int, optional): Frames per second for output video.
                           If None, uses source frame rate.
        codec (str): Video codec to use. Default: "libx264"
        extra_params (list, optional): Additional FFmpeg parameters.
                                      Example: ["-b:v", "5M"]

    Returns:
        bool: True if video created successfully, False otherwise.

    Raises:
        ValueError: If inputs are invalid

    Example:
        >>> create_video_from_config(
        ...     dst="output.mp4",
        ...     config_path="my_config.json",
        ...     width=1920,
        ...     height=1080,
        ...     crf=23,
        ...     fps=30
        ... )
        True
    """
    logger.info(f"Starting video creation: config='{config_path}', destination='{dst}'")

    # 1. Validate inputs
    if not validate_inputs(dst, config_path):
        return False

    # 2. Check FFmpeg installation
    if not check_ffmpeg_installed():
        return False

    # 3. Load configuration
    config_data = load_config(config_path)
    if config_data is None:
        return False

    # 4. Parse and validate clips
    valid_clips = parse_clips(config_data)
    if not valid_clips:
        logger.warning("No valid images found in configuration. Video not created.")
        return False

    logger.info(f"Found {len(valid_clips)} valid images for video creation")

    # 5. Generate concat file
    concat_file_path = generate_concat_file(valid_clips)
    if concat_file_path is None:
        logger.error("Failed to generate concat file")
        return False

    try:
        # 6. Build FFmpeg command
        ffmpeg_cmd = build_ffmpeg_command(
            concat_file_path=concat_file_path,
            dst=dst,
            width=width,
            height=height,
            crf=crf,
            fps=fps,
            codec=codec,
            extra_params=extra_params,
        )

        # 7. Run FFmpeg
        success = run_ffmpeg(ffmpeg_cmd)

        if success:
            # Verify output file exists
            if os.path.exists(dst):
                file_size = os.path.getsize(dst)
                logger.info(
                    f"Video created successfully: {dst} ({file_size / (1024 * 1024):.2f} MB)"
                )
            else:
                logger.warning(
                    f"Video creation reported success but output file '{dst}' not found"
                )
                success = False

        return success

    finally:
        # 8. Clean up temporary concat file
        if concat_file_path and os.path.exists(concat_file_path):
            try:
                os.remove(concat_file_path)
                logger.debug(f"Removed temporary concat file: {concat_file_path}")
            except OSError as e:
                logger.warning(
                    f"Could not remove temporary file '{concat_file_path}': {e}"
                )


def main():
    """
    Main entry point for the script.
    Handles environment variable loading and error handling.
    """
    logger.info("Video Creator starting...")

    # Get configuration from environment or use defaults
    config_path = CONFIG
    dst_video = DST_VIDEO

    try:
        success = create_video_from_config(
            dst=dst_video,
            config_path=config_path,
            width=2560,
            height=1440,
            crf=18,
            # fps=30,  # need to turn off -vsync vfr to turn on fps
            # codec="libx265",  # Uncomment to use H.265
            # extra_params=["-b:v", "10M"]  # Uncomment for bitrate control
        )

        if success:
            logger.info("Video creation completed successfully!")
        else:
            logger.error("Video creation failed!")
            sys.exit(1)

    except KeyboardInterrupt:
        logger.info("Video creation interrupted by user")
        sys.exit(130)
    except ValueError:
        logger.exception("Exception occurred")
        sys.exit(1)


if __name__ == "__main__":
    main()
