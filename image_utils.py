import os
import io
from typing import Optional, Tuple
from PIL import Image, ImageOps
import hashlib

from logging_config import logger


def validate_image(file_data: bytes, max_size_mb: int = 10) -> bool:
    """Validate image format, size, and basic security checks."""
    try:
        # Size check
        if len(file_data) > max_size_mb * 1024 * 1024:
            return False
        
        # Try to open with PIL
        with Image.open(io.BytesIO(file_data)) as img:
            # Check format
            if img.format not in ['JPEG', 'PNG', 'WEBP']:
                return False
            
            # Check dimensions
            width, height = img.size
            if width > 4096 or height > 4096 or width < 32 or height < 32:
                return False
        
        return True
    except Exception:
        return False


def create_thumbnail(file_data: bytes, size: Tuple[int, int] = (300, 300)) -> Optional[bytes]:
    """Create a thumbnail from image data."""
    try:
        with Image.open(io.BytesIO(file_data)) as img:
            # Convert to RGB if necessary (for JPEG output)
            if img.mode in ('RGBA', 'LA', 'P'):
                img = img.convert('RGB')
            
            # Create thumbnail while maintaining aspect ratio
            img.thumbnail(size, Image.Resampling.LANCZOS)
            
            # Save to bytes
            output = io.BytesIO()
            img.save(output, format='JPEG', quality=85, optimize=True)
            return output.getvalue()
            
    except Exception as e:
        logger.exception("Thumbnail creation failed: %s", e)
        return None


def get_image_hash(file_data: bytes) -> str:
    """Get SHA-256 hash of image data for deduplication."""
    return hashlib.sha256(file_data).hexdigest()


def save_image(file_data: bytes, filename: str, upload_dir: str = 'uploads') -> Optional[str]:
    """Save image to disk with validation and thumbnail creation."""
    try:
        # Validate image
        if not validate_image(file_data):
            return None
        
        # Create upload directory if it doesn't exist
        os.makedirs(upload_dir, exist_ok=True)
        
        # Generate safe filename
        image_hash = get_image_hash(file_data)
        ext = '.jpg'  # Always save as JPEG for consistency
        safe_filename = f"{image_hash}{ext}"
        thumb_filename = f"{image_hash}_thumb{ext}"
        
        file_path = os.path.join(upload_dir, safe_filename)
        thumb_path = os.path.join(upload_dir, thumb_filename)
        
        # Save original (if not already exists)
        if not os.path.exists(file_path):
            # Convert to standard format
            with Image.open(io.BytesIO(file_data)) as img:
                if img.mode in ('RGBA', 'LA', 'P'):
                    img = img.convert('RGB')
                
                # Optimize and save
                img.save(file_path, format='JPEG', quality=90, optimize=True)
        
        # Create thumbnail (if not already exists)
        if not os.path.exists(thumb_path):
            thumb_data = create_thumbnail(file_data)
            if thumb_data:
                with open(thumb_path, 'wb') as f:
                    f.write(thumb_data)
        
        return safe_filename
        
    except Exception as e:
        logger.exception("Image save failed: %s", e)
        return None


def cleanup_old_images(upload_dir: str = 'uploads', days_old: int = 30):
    """Clean up images older than specified days."""
    try:
        import time
        cutoff_time = time.time() - (days_old * 24 * 3600)
        
        count = 0
        for filename in os.listdir(upload_dir):
            file_path = os.path.join(upload_dir, filename)
            if os.path.isfile(file_path) and os.path.getmtime(file_path) < cutoff_time:
                os.remove(file_path)
                count += 1
        
        logger.info("Cleaned up %s old images", count)
        return count
        
    except Exception as e:
        logger.exception("Image cleanup failed: %s", e)
        return 0