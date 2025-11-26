"""Intelligent image filtering for technical documentation."""
import hashlib
import base64
import io
from typing import Dict, Any, Optional, Set, Tuple
from PIL import Image
import numpy as np


class ImageFilter:
    """Filter images to keep technical content, remove decorative elements."""
    
    # Configuration from .env or defaults
    MIN_IMAGE_SIZE = 80  # Skip images smaller than 80x80 (likely logos)
    MAX_REPEAT_COUNT = 3  # If image appears >3 times, likely header/footer
    MIN_ASPECT_RATIO = 0.2  # Skip very thin lines/dividers
    MAX_ASPECT_RATIO = 5.0
    
    # Technical keywords that indicate valuable content
    TECHNICAL_KEYWORDS = [
        # Hardware/Equipment
        'block', 'diagram', 'module', 'slot', 'controller', 'board', 'card',
        'terminal', 'connector', 'port', 'panel', 'enclosure', 'cabinet',
        'sensor', 'actuator', 'valve', 'relay', 'switch',
        
        # Schematics/Wiring
        'wiring', 'schematic', 'circuit', 'connection', 'cable', 'wire',
        'pinout', 'terminal', 'junction', 'harness',
        
        # Software/UI
        'screen', 'interface', 'display', 'menu', 'dialog', 'window',
        'button', 'field', 'form', 'view', 'editor', 'workspace',
        
        # Diagrams
        'flowchart', 'flow', 'topology', 'architecture', 'layout',
        'structure', 'hierarchy', 'tree', 'network', 'map',
        
        # Data visualization
        'chart', 'graph', 'plot', 'table', 'matrix', 'grid',
        'timeline', 'gantt', 'histogram', 'trend',
        
        # Technical drawings
        'drawing', 'blueprint', 'specification', 'dimension', 'elevation',
        'section', 'detail', 'assembly', 'exploded', 'cutaway',
        
        # System components
        'system', 'configuration', 'setup', 'installation', 'mounting',
        'placement', 'location', 'positioning'
    ]
    
    # Non-technical keywords that indicate decorative content
    DECORATIVE_KEYWORDS = [
        'logo', 'trademark', 'copyright', 'watermark', 'banner',
        'header', 'footer', 'icon', 'bullet', 'decoration',
        'divider', 'separator', 'border', 'frame'
    ]
    
    def __init__(self):
        self.image_hashes: Set[str] = set()
        self.image_counts: Dict[str, int] = {}
        self.skipped_count = 0
        self.kept_count = 0
    
    def should_process_image(
        self,
        image_data: str,
        caption: str = "",
        bbox: Optional[Dict[str, Any]] = None,
        page_number: int = 0
    ) -> Tuple[bool, str]:
        """
        Determine if an image should be processed based on intelligent filtering.
        
        Returns:
            (should_process: bool, reason: str)
        """
        # Decode image to analyze
        try:
            img_bytes = base64.b64decode(image_data)
            img = Image.open(io.BytesIO(img_bytes))
            width, height = img.size
        except Exception as e:
            return False, f"Invalid image: {e}"
        
        # Filter 1: Size check - Skip very small images (logos, icons)
        if width < self.MIN_IMAGE_SIZE or height < self.MIN_IMAGE_SIZE:
            self.skipped_count += 1
            return False, f"Too small: {width}x{height} (likely logo/icon)"
        
        # Filter 2: Aspect ratio - Skip lines, dividers
        aspect_ratio = max(width, height) / min(width, height)
        if aspect_ratio < self.MIN_ASPECT_RATIO or aspect_ratio > self.MAX_ASPECT_RATIO:
            self.skipped_count += 1
            return False, f"Extreme aspect ratio: {aspect_ratio:.1f} (likely divider/line)"
        
        # Filter 3: Duplicate detection - Skip repeated images
        img_hash = self._compute_image_hash(img)
        
        if img_hash in self.image_counts:
            self.image_counts[img_hash] += 1
            count = self.image_counts[img_hash]
            
            # If image appears more than MAX_REPEAT_COUNT times, it's likely decorative
            if count > self.MAX_REPEAT_COUNT:
                self.skipped_count += 1
                return False, f"Repeated {count} times (likely header/footer/logo)"
        else:
            self.image_counts[img_hash] = 1
        
        self.image_hashes.add(img_hash)
        
        # Filter 4: Caption analysis - Check for technical content
        caption_lower = caption.lower() if caption else ""
        
        # Check for decorative keywords (negative filter)
        for keyword in self.DECORATIVE_KEYWORDS:
            if keyword in caption_lower:
                self.skipped_count += 1
                return False, f"Decorative content detected: '{keyword}' in caption"
        
        # Check for technical keywords (positive filter)
        has_technical_content = False
        matched_keywords = []
        
        for keyword in self.TECHNICAL_KEYWORDS:
            if keyword in caption_lower:
                has_technical_content = True
                matched_keywords.append(keyword)
        
        # If caption is empty or has no clear markers, analyze image content
        if not caption or len(caption.strip()) < 5:
            # No caption - make decision based on size and complexity
            if width >= 150 and height >= 150:
                # Large enough to potentially be technical diagram
                complexity = self._estimate_image_complexity(img)
                if complexity > 0.1:  # Not blank/simple
                    self.kept_count += 1
                    return True, f"Large image ({width}x{height}) with content complexity"
                else:
                    self.skipped_count += 1
                    return False, "Low complexity (likely blank/simple graphic)"
            else:
                # Medium size, no caption - likely not important
                self.skipped_count += 1
                return False, "No caption and medium size (likely decorative)"
        
        # Has caption - prioritize based on technical keywords
        if has_technical_content:
            self.kept_count += 1
            return True, f"Technical content: {', '.join(matched_keywords[:3])}"
        
        # Caption exists but no clear technical markers
        # Be conservative - keep it if reasonable size
        if width >= 150 and height >= 150:
            self.kept_count += 1
            return True, "Reasonable size with caption (possibly technical)"
        
        # Default: Skip if small and no clear technical markers
        self.skipped_count += 1
        return False, "No clear technical markers"
    
    def _compute_image_hash(self, img: Image.Image) -> str:
        """Compute perceptual hash for duplicate detection."""
        try:
            # Resize to small size for comparison
            img_small = img.resize((8, 8), Image.LANCZOS).convert('L')
            
            # Get pixel data
            pixels = np.array(img_small).flatten()
            
            # Compute average
            avg = pixels.mean()
            
            # Create hash based on whether pixels are above/below average
            hash_bits = ''.join('1' if p > avg else '0' for p in pixels)
            
            # Convert to hex
            hash_hex = hex(int(hash_bits, 2))[2:]
            
            return hash_hex
        except Exception:
            # Fallback to simple hash if perceptual hash fails
            return hashlib.md5(img.tobytes()).hexdigest()[:16]
    
    def _estimate_image_complexity(self, img: Image.Image) -> float:
        """
        Estimate image complexity (edges, variance).
        Higher = more content, Lower = blank/simple.
        """
        try:
            # Convert to grayscale and small size
            img_gray = img.resize((100, 100), Image.LANCZOS).convert('L')
            pixels = np.array(img_gray)
            
            # Calculate variance (how much pixel values differ)
            variance = pixels.var()
            
            # Normalize to 0-1 range (typical variance is 0-10000)
            complexity = min(variance / 10000.0, 1.0)
            
            return complexity
        except Exception:
            return 0.5  # Default medium complexity on error
    
    def get_stats(self) -> Dict[str, Any]:
        """Get filtering statistics."""
        total = self.kept_count + self.skipped_count
        return {
            'total_processed': total,
            'kept': self.kept_count,
            'skipped': self.skipped_count,
            'keep_rate': self.kept_count / total if total > 0 else 0,
            'unique_images': len(self.image_hashes)
        }
    
    def print_stats(self):
        """Print filtering statistics."""
        stats = self.get_stats()
        print(f"\n📊 Image Filtering Statistics:")
        print(f"   Total evaluated: {stats['total_processed']}")
        print(f"   ✅ Kept: {stats['kept']} ({stats['keep_rate']*100:.1f}%)")
        print(f"   ❌ Skipped: {stats['skipped']} ({(1-stats['keep_rate'])*100:.1f}%)")
        print(f"   🔍 Unique images: {stats['unique_images']}")
        
        if stats['skipped'] > 0:
            saved_cost = stats['skipped'] * 0.0004  # ~$0.0004 per image
            print(f"   💰 Estimated savings: ${saved_cost:.4f}")
