import os
import hashlib
from typing import Optional, Tuple
from PIL import Image, ImageOps
from io import BytesIO
import mimetypes
from logging_config import logger


class ImageProcessor:
    """Image processing and optimization for Telegram bot."""
    
    # Allowed image formats
    ALLOWED_FORMATS = {'JPEG', 'PNG', 'WEBP'}
    ALLOWED_MIME_TYPES = {'image/jpeg', 'image/png', 'image/webp'}
    
    # Size limits
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    MAX_DIMENSION = 2048
    THUMBNAIL_SIZE = (300, 300)
    
    def __init__(self, storage_path: str = 'images'):
        self.storage_path = storage_path
        os.makedirs(storage_path, exist_ok=True)
        os.makedirs(os.path.join(storage_path, 'thumbnails'), exist_ok=True)
    
    def validate_image(self, file_data: bytes, filename: str) -> Tuple[bool, str]:
        """Validate image file format and size."""
        try:
            # Check file size
            if len(file_data) > self.MAX_FILE_SIZE:
                return False, f"File too large: {len(file_data)} bytes (max: {self.MAX_FILE_SIZE})"
            
            # Check MIME type
            mime_type, _ = mimetypes.guess_type(filename)
            if mime_type not in self.ALLOWED_MIME_TYPES:
                return False, f"Invalid file type: {mime_type}"
            
            # Try to open and validate image
            try:
                with Image.open(BytesIO(file_data)) as img:
                    if img.format not in self.ALLOWED_FORMATS:
                        return False, f"Invalid image format: {img.format}"
                    
                    # Check dimensions
                    if max(img.size) > self.MAX_DIMENSION:
                        return False, f"Image too large: {img.size} (max dimension: {self.MAX_DIMENSION})"
                        
            except Exception as e:
                return False, f"Invalid image file: {str(e)}"
            
            return True, "Valid image"
            
        except Exception as e:
            logger.error(f"Image validation failed: {str(e)}")
            return False, f"Validation error: {str(e)}"
    
    def process_and_save(self, file_data: bytes, filename: str) -> Optional[dict]:
        """Process image and save original + thumbnail. Returns file info or None."""
        try:
            # Validate first
            is_valid, message = self.validate_image(file_data, filename)
            if not is_valid:
                logger.warning(f"Invalid image rejected: {message}")
                return None
            
            # Generate unique filename based on content hash
            file_hash = hashlib.md5(file_data).hexdigest()
            file_ext = os.path.splitext(filename)[1].lower()
            unique_name = f"{file_hash}{file_ext}"
            
            original_path = os.path.join(self.storage_path, unique_name)
            thumbnail_path = os.path.join(self.storage_path, 'thumbnails', unique_name)
            
            # Check if already exists
            if os.path.exists(original_path):
                logger.info(f"Image already exists: {unique_name}")
                return {
                    'filename': unique_name,
                    'original_path': original_path,
                    'thumbnail_path': thumbnail_path,
                    'file_size': len(file_data)
                }
            
            # Open and process image
            with Image.open(BytesIO(file_data)) as img:
                # Convert to RGB if necessary (for JPEG compatibility)
                if img.mode in ('RGBA', 'LA', 'P'):
                    rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    rgb_img.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                    img = rgb_img
                
                # Optimize and save original (with compression)
                img.save(original_path, format='JPEG', quality=85, optimize=True)
                
                # Create thumbnail
                thumbnail = img.copy()
                thumbnail.thumbnail(self.THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
                thumbnail.save(thumbnail_path, format='JPEG', quality=80, optimize=True)
            
            file_info = {
                'filename': unique_name,
                'original_path': original_path,
                'thumbnail_path': thumbnail_path,
                'file_size': len(file_data),
                'dimensions': img.size
            }
            
            logger.info(f"Image processed successfully: {unique_name}")
            return file_info
            
        except Exception as e:
            logger.error(f"Image processing failed: {str(e)}")
            return None
    
    def get_image_url(self, filename: str, thumbnail: bool = False) -> Optional[str]:
        """Get URL for accessing image (placeholder - would integrate with actual file serving)."""
        if not filename:
            return None
        
        subdir = 'thumbnails/' if thumbnail else ''
        path = os.path.join(self.storage_path, subdir, filename)
        
        if os.path.exists(path):
            # In production, this would return actual URL from CDN/file server
            return f"/images/{subdir}{filename}"
        
        return None
    
    def delete_image(self, filename: str) -> bool:
        """Delete image and its thumbnail."""
        try:
            original_path = os.path.join(self.storage_path, filename)
            thumbnail_path = os.path.join(self.storage_path, 'thumbnails', filename)
            
            deleted = False
            if os.path.exists(original_path):
                os.unlink(original_path)
                deleted = True
            
            if os.path.exists(thumbnail_path):
                os.unlink(thumbnail_path)
                deleted = True
            
            if deleted:
                logger.info(f"Image deleted: {filename}")
            
            return deleted
            
        except Exception as e:
            logger.error(f"Failed to delete image {filename}: {str(e)}")
            return False
    
    def cleanup_unused_images(self, active_filenames: set) -> int:
        """Clean up images not in the active set. Returns count of deleted files."""
        try:
            deleted_count = 0
            
            # Check original images
            for filename in os.listdir(self.storage_path):
                if filename not in active_filenames and os.path.isfile(os.path.join(self.storage_path, filename)):
                    if self.delete_image(filename):
                        deleted_count += 1
            
            logger.info(f"Cleanup completed: {deleted_count} unused images deleted")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Image cleanup failed: {str(e)}")
            return 0


# Global instance
image_processor = ImageProcessor()


def process_telegram_photo(file_data: bytes, filename: str) -> Optional[str]:
    """Helper function to process photo from Telegram bot. Returns filename or None."""
    result = image_processor.process_and_save(file_data, filename)
    return result['filename'] if result else None