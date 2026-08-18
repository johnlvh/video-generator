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
import sys
from typing import Any

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

CONFIG = os.getenv("CONFIG")
SRC_IMAGE_DIRS = os.getenv("SRC_IMAGE_DIRS")
DEFAULT_DURATION = (
    float(os.getenv("DEFAULT_DURATION")) if os.getenv("DEFAULT_DURATION") else 1.0
)
FIRST_DURATION = (
    float(os.getenv("FIRST_DURATION")) if os.getenv("FIRST_DURATION") else 3.0
)
LAST_DURATION = float(os.getenv("LAST_DURATION")) if os.getenv("LAST_DURATION") else 3.0
MAX_IMAGES = int(os.getenv("MAX_IMAGES")) if os.getenv("MAX_IMAGES") else 1000

# Constants
IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".tiff",
    ".webp",
    ".tif",
    ".jfif",
    ".pjpeg",
}

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s - %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

logger.info(f"DEFAULT_DURATION: {DEFAULT_DURATION}")
logger.info(f"FIRST_DURATION: {FIRST_DURATION}")
logger.info(f"LAST_DURATION: {LAST_DURATION}")
logger.info(f"MAX_IMAGES: {MAX_IMAGES}")


def validate_directory(path: str) -> bool:
    """
    Validate if directory exists and is accessible.

    Args:
        path: Directory path to validate

    Returns:
        bool: True if valid, False otherwise
    """
    if not path or not path.strip():
        logger.error("Directory path cannot be empty")
        return False

    if not os.path.exists(path):
        logger.error(f"Directory does not exist: {path}")
        return False

    if not os.path.isdir(path):
        logger.error(f"Path is not a directory: {path}")
        return False

    if not os.access(path, os.R_OK):
        logger.error(f"No read permission for directory: {path}")
        return False

    return True


def get_image_files(folder_path: str, extensions: set[str] | None = None) -> list[str]:
    """
    Get all image files from a folder.

    Args:
        folder_path: Path to folder
        extensions: Set of allowed extensions

    Returns:
        Sorted list of image filenames
    """
    if extensions is None:
        extensions = IMAGE_EXTENSIONS

    images = []
    try:
        with os.scandir(folder_path) as entries:
            for entry in entries:
                if entry.is_file():
                    name = entry.name
                    ext = os.path.splitext(name)[1].lower()
                    if ext in extensions:
                        images.append(name)
    except OSError as e:
        logger.error(f"Cannot scan directory '{folder_path}': {e}")
        return []

    return sorted(images)


def get_subfolders(
    rootdir: str, recursive: bool = False, exclude_hidden: bool = True
) -> list[str]:
    """
    Get all subfolders in a directory.

    Args:
        rootdir: Root directory
        recursive: Whether to include subfolders recursively
        exclude_hidden: Whether to exclude hidden folders

    Returns:
        List of folder paths
    """
    folders = []

    if recursive:
        for dirpath, dirnames, _ in os.walk(rootdir):
            if exclude_hidden:
                dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for d in dirnames:
                folders.append(os.path.join(dirpath, d))
    else:
        try:
            for item in os.listdir(rootdir):
                if exclude_hidden and item.startswith("."):
                    continue
                item_path = os.path.join(rootdir, item)
                if os.path.isdir(item_path):
                    folders.append(item_path)
        except OSError as e:
            logger.error(f"Cannot list directory '{rootdir}': {e}")
            return []

    return sorted(folders)


def build_config_data(
    folders: list[str],
    default_duration: float = DEFAULT_DURATION,
    first_duration: float = FIRST_DURATION,
    last_duration: float = LAST_DURATION,
    extensions: set[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """
    Build configuration data from folders.

    Args:
        folders: List of folder paths
        default_duration: Duration for normal images
        first_duration: Duration for first image
        last_duration: Duration for last image
        extensions: Set of allowed image extensions

    Returns:
        Dictionary with folder name as key and image configs as value
    """
    if extensions is None:
        extensions = IMAGE_EXTENSIONS

    config_data = {}
    total_images = 0
    processed_images: set[str] = set()

    for folder_path in folders:
        folder_name = os.path.basename(folder_path)

        # Get images
        images = get_image_files(folder_path, extensions)

        if not images:
            logger.warning(f"No images found in '{folder_name}', skipping...")
            continue

        # Build config for this folder
        folder_config = []
        duplicate_count = 0

        for idx, img_name in enumerate(images):
            img_path = os.path.join(folder_path, img_name)

            # Check for duplicates
            if img_path in processed_images:
                logger.warning(f"Duplicate image: {img_path}")
                duplicate_count += 1
                continue

            # Calculate duration
            if idx == 0:
                duration = first_duration
            elif idx == len(images) - 1:
                duration = last_duration
            else:
                duration = default_duration

            folder_config.append({"img": img_path, "duration": float(duration)})

            processed_images.add(img_path)

        if folder_config:
            config_data[folder_name] = folder_config
            total_images += len(folder_config)

            # Log folder summary
            logger.info(
                f"Folder '{folder_name}': {len(folder_config)} images "
                f"(duplicates: {duplicate_count})"
            )
    logger.info(f"Total unique images processed: {total_images}")
    # Check for large number of images
    if total_images > MAX_IMAGES:
        logger.warning(
            f"Large number of images ({total_images}). "
            f"This may consume significant memory."
        )

    return config_data


def save_config(config_data: dict[str, list[dict[str, Any]]], output_path: str) -> bool:
    """
    Save configuration to JSON file.

    Args:
        config_data: Configuration dictionary
        output_path: Output file path

    Returns:
        bool: True if successful, False otherwise
    """
    # Create output directory if needed
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir, exist_ok=True)
            logger.debug(f"Created output directory: {output_dir}")
        except OSError as e:
            logger.error(f"Cannot create directory '{output_dir}': {e}")
            return False

    # Save config
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)
        logger.info(f"Successfully saved config to: {output_path}")
        return True
    except PermissionError as e:
        logger.error(f"No permission to write to '{output_path}': {e}")
        return False
    except OSError as e:
        logger.error(f"Error writing to '{output_path}': {e}")
        return False


def generate_config(
    rootdir: str,
    output_config_path: str = "config.json",
    default_duration: float = DEFAULT_DURATION,
    first_duration: float = FIRST_DURATION,
    last_duration: float = LAST_DURATION,
    recursive: bool = False,
    exclude_hidden: bool = True,
    extensions: set[str] | None = None,
) -> bool:
    """
    Scan folders for images and generate a JSON configuration file.

    This function scans a root directory for image files, organizes them by
    folder, and creates a configuration file for video generation.

    Args:
        rootdir (str): Root directory containing image folders
        output_config_path (str): Output JSON file path
        default_duration (float): Duration for normal images (seconds)
        first_duration (float): Duration for first image in each folder
        last_duration (float): Duration for last image in each folder
        recursive (bool): Whether to scan subdirectories recursively
        exclude_hidden (bool): Whether to exclude hidden folders/files
        extensions (set): Set of allowed image extensions

    Returns:
        bool: True if successful, False otherwise

    Example:
        >>> generate_config(
        ...     rootdir="./images",
        ...     output_config_path="config.json",
        ...     default_duration=1.0,
        ...     first_duration=3.0,
        ...     last_duration=3.0,
        ...     recursive=True
        ... )
        True
    """
    logger.info("Starting configuration generation...")
    logger.info(f"Root directory: {rootdir}")
    logger.info(f"Output config: {output_config_path}")
    logger.info(f"Recursive: {recursive}")
    logger.info(f"Exclude hidden: {exclude_hidden}")

    # 1. Validate root directory
    if not validate_directory(rootdir):
        return False

    # 2. Get subfolders
    folders = get_subfolders(rootdir, recursive, exclude_hidden)
    if not folders:
        logger.warning(f"No subfolders found in '{rootdir}'")
        return False

    logger.info(f"Found {len(folders)} subfolder(s)")

    # 3. Build configuration data
    config_data = build_config_data(
        folders=folders,
        default_duration=default_duration,
        first_duration=first_duration,
        last_duration=last_duration,
        extensions=extensions,
    )

    if not config_data:
        logger.warning("No valid folders with images found")
        return False

    # 4. Save configuration
    success = save_config(config_data, output_config_path)

    # 5. Log summary
    if success:
        total_folders = len(config_data)
        total_images = sum(len(v) for v in config_data.values())
        logger.info(
            f"Configuration generation completed: "
            f"{total_folders} folders, {total_images} images"
        )

    return success


def main() -> None:
    """Main entry point."""
    logger.info("Config Generator starting...")

    try:
        success = generate_config(
            rootdir=SRC_IMAGE_DIRS or "./images",
            output_config_path=CONFIG or "config.json",
            default_duration=DEFAULT_DURATION,
            first_duration=FIRST_DURATION,
            last_duration=LAST_DURATION,
            recursive=False,  # Set to True to scan subfolders
            exclude_hidden=True,
        )

        if success:
            logger.info("Config generation completed successfully!")
        else:
            logger.error("Config generation failed!")
            sys.exit(1)

    except KeyboardInterrupt:
        logger.info("Config generation interrupted by user")
        sys.exit(130)
    except ValueError:
        logger.exception("Exception occurred")
        sys.exit(1)


if __name__ == "__main__":
    main()
