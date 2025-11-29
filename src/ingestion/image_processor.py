"""Cost-optimized image processing with S3 storage."""
import os
import base64
import io
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from PIL import Image
from openai import OpenAI
import sys
sys.path.append('..')
from storage.s3_client import S3ImageStorage
from .image_filter import ImageFilter


@dataclass
class ImageReference:
    """Lightweight image reference stored in database."""
    id: str
    doc_id: str
    page_number: int
    bbox: Optional[Dict[str, Any]] = None
    
    # S3 storage (not base64!)
    s3_url: str = None
    
    # Free metadata from Docling
    caption: Optional[str] = None
    ocr_text: Optional[str] = None
    
    # Tier 1: Basic classification (cheap, generated during ingestion)
    image_type: Optional[str] = None  # "diagram", "screenshot", "chart", "photo"
    basic_summary: Optional[str] = None  # 1-sentence summary
    
    # Tier 2: Detailed description (expensive, generated on-demand)
    detailed_description: Optional[str] = None
    
    # Cost tracking
    tokens_used: int = 0
    description_generated: bool = False


class ImageProcessor:
    """Process images with cost optimization."""
    
    def __init__(self):
        self.openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.s3_storage = S3ImageStorage()
        self.model = os.getenv('VISION_MODEL', 'gpt-4o-mini')
        
        # Intelligent filtering (enabled by default for production)
        self.enable_filtering = os.getenv('ENABLE_IMAGE_FILTERING', 'true').lower() == 'true'
        self.image_filter = ImageFilter() if self.enable_filtering else None
    
    def process_images(
        self,
        doc_json: Dict[str, Any],
        doc_id: str,
        skip_indices: List[int] = None,
        progress_callback = None
    ) -> List[ImageReference]:
        """
        Process all images from Docling output.

        Strategy:
        1. Compress images
        2. Upload to S3
        3. Generate basic summaries (batch, low cost)
        4. Store only URLs + metadata in database

        Args:
            doc_json: Parsed document JSON
            doc_id: Document ID
            skip_indices: List of image indices to skip (already processed)
            progress_callback: Optional callback(current, total, step_name) for progress
        """
        if skip_indices is None:
            skip_indices = []
        pictures = doc_json.get("pictures", [])
        
        if not pictures:
            return []
        
        total_images = len(pictures)
        skipped_from_checkpoint = len(skip_indices)
        print(f"Processing {total_images} images (skipping {skipped_from_checkpoint} already done)...")

        # Step 1: Prepare images (compress + extract metadata + filter)
        prepared_images = []
        filtered_count = 0

        for idx, picture in enumerate(pictures):
            # RESUME: Skip already processed images
            if idx in skip_indices:
                continue

            prov = picture.get("prov", [])
            if not prov:
                continue

            page = prov[0].get("page_no", 1)  # FIXED: Use 'page_no' not 'page'
            bbox = prov[0].get("bbox")

            # Get base64 from Docling
            image_data = picture.get("data")
            if not image_data:
                continue

            # Extract free metadata
            caption = picture.get("text", "").strip()

            # INTELLIGENT FILTERING: Skip decorative/repeated images
            if self.enable_filtering and self.image_filter:
                should_process, reason = self.image_filter.should_process_image(
                    image_data=image_data,
                    caption=caption,
                    bbox=bbox,
                    page_number=page
                )

                if not should_process:
                    filtered_count += 1
                    if filtered_count <= 5:  # Show first 5 filtered images
                        print(f"   ⏭️  Skipping image {idx} on page {page}: {reason}")
                    continue

            # Compress image for cost optimization
            compressed_data = self._compress_image(image_data, max_size=512)

            prepared_images.append({
                'original_data': compressed_data,
                'page_number': page,
                'bbox': bbox,
                'caption': caption,
                'index': idx
            })
        
        if filtered_count > 0:
            print(f"   📊 Filtered out {filtered_count}/{len(pictures)} images ({filtered_count/len(pictures)*100:.1f}%)")

        if not prepared_images:
            return []

        # Step 2: Upload to S3 (batch)
        print(f"Uploading {len(prepared_images)} images to S3...")
        if progress_callback:
            progress_callback(0, len(prepared_images), "uploading_images")
        s3_urls = self._upload_to_s3_batch(prepared_images, doc_id)

        # Step 3: Generate basic summaries (batch, low detail)
        print(f"Generating basic summaries (batch mode)...")
        summaries = self._generate_basic_summaries_batch(
            prepared_images,
            progress_callback=progress_callback
        )
        
        # Step 4: Create image references
        image_refs = []
        for img_data, s3_url, summary in zip(prepared_images, s3_urls, summaries):
            if not s3_url:  # Skip failed uploads
                continue
            
            image_ref = ImageReference(
                id=f"{doc_id}_img_{img_data['page_number']}_{img_data['index']:02d}",
                doc_id=doc_id,
                page_number=img_data['page_number'],
                bbox=img_data['bbox'],
                s3_url=s3_url,
                caption=img_data['caption'],
                image_type=summary.get('type'),
                basic_summary=summary.get('summary'),
                tokens_used=summary.get('tokens', 0)
            )
            image_refs.append(image_ref)
        
        total_tokens = sum(img.tokens_used for img in image_refs)
        print(f"✅ Processed {len(image_refs)} images. Total tokens: {total_tokens}")
        
        # Print filtering statistics
        if self.enable_filtering and self.image_filter:
            self.image_filter.print_stats()
        
        return image_refs
    
    def _compress_image(self, base64_data: str, max_size: int = 512) -> str:
        """
        Compress image to reduce token cost.
        
        GPT-4o-mini pricing:
        - 512x512: ~2833 tokens (~85 tokens in low detail mode)
        - 1024x1024: ~5667 tokens (~170 tokens in low detail mode)
        """
        try:
            # Decode
            img_bytes = base64.b64decode(base64_data)
            img = Image.open(io.BytesIO(img_bytes))
            
            # Resize maintaining aspect ratio
            img.thumbnail((max_size, max_size), Image.LANCZOS)
            
            # Convert to JPEG (smaller than PNG)
            buffer = io.BytesIO()
            img.convert('RGB').save(buffer, format='JPEG', quality=85, optimize=True)
            
            # Re-encode
            return base64.b64encode(buffer.getvalue()).decode()
        
        except Exception as e:
            print(f"Error compressing image: {e}")
            return base64_data  # Return original if compression fails
    
    def _upload_to_s3_batch(
        self,
        images: List[Dict[str, Any]],
        doc_id: str
    ) -> List[str]:
        """Upload all images to S3."""
        upload_data = [
            {
                'base64': img['original_data'],
                'page_number': img['page_number'],
                'image_index': img['index'],
                'format': 'jpeg'
            }
            for img in images
        ]
        
        return self.s3_storage.upload_batch(upload_data, doc_id)
    
    def _generate_basic_summaries_batch(
        self,
        images: List[Dict[str, Any]],
        batch_size: int = 5,
        progress_callback = None
    ) -> List[Dict[str, Any]]:
        """
        Generate basic summaries for all images using batch processing.

        Uses "low" detail mode for cost optimization:
        - Each image: ~85 tokens input
        - 5 images per batch: ~425 tokens input
        - Output: ~150 tokens (30 per image)
        - Total per batch: ~575 tokens (~$0.0002 per batch)
        """
        all_summaries = []
        total_batches = (len(images) + batch_size - 1) // batch_size

        # Process in batches of 5
        for batch_idx, i in enumerate(range(0, len(images), batch_size)):
            batch = images[i:i+batch_size]

            # Report progress
            if progress_callback:
                progress_callback(batch_idx, total_batches, "generating_image_summaries")
            
            # Build multi-image prompt
            content = [{
                "type": "text",
                "text": """For each image, provide a brief analysis in this format:
[Image N]
Type: [diagram/screenshot/chart/photo/table]
Summary: [One sentence describing what it shows]

Be concise and technical."""
            }]
            
            # Add images with low detail mode
            for j, img in enumerate(batch, 1):
                content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{img['original_data']}",
                        "detail": "low"  # Low detail = ~85 tokens per image
                    }
                })
            
            try:
                response = self.openai_client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": content}],
                    max_tokens=150,  # Limit output tokens
                    temperature=0.3
                )
                
                # Parse response
                result_text = response.choices[0].message.content
                tokens_used = response.usage.total_tokens
                
                # Parse summaries from response
                summaries = self._parse_batch_summaries(result_text, len(batch))
                
                # Add token count to each summary
                tokens_per_image = tokens_used // len(batch)
                for summary in summaries:
                    summary['tokens'] = tokens_per_image
                
                all_summaries.extend(summaries)
                
            except Exception as e:
                print(f"Error generating summaries for batch: {e}")
                # Add empty summaries for failed batch
                all_summaries.extend([
                    {'type': 'unknown', 'summary': '', 'tokens': 0}
                    for _ in batch
                ])
        
        return all_summaries
    
    def _parse_batch_summaries(
        self,
        text: str,
        expected_count: int
    ) -> List[Dict[str, str]]:
        """Parse batch summary response."""
        summaries = []
        lines = text.strip().split('\n')
        
        current_type = None
        current_summary = None
        
        for line in lines:
            line = line.strip()
            
            if line.startswith('Type:'):
                current_type = line.replace('Type:', '').strip().lower()
            elif line.startswith('Summary:'):
                current_summary = line.replace('Summary:', '').strip()
                
                if current_type and current_summary:
                    summaries.append({
                        'type': current_type,
                        'summary': current_summary
                    })
                    current_type = None
                    current_summary = None
        
        # Fill in missing summaries
        while len(summaries) < expected_count:
            summaries.append({'type': 'unknown', 'summary': ''})
        
        return summaries[:expected_count]
    
    def generate_detailed_description(
        self,
        s3_url: str,
        context: Optional[str] = None
    ) -> str:
        """
        Generate detailed description for a specific image (on-demand).
        
        This is EXPENSIVE (~340 tokens per image with high detail).
        Only call when user query explicitly needs visual understanding.
        """
        try:
            # Download image from S3
            # For public images, we can use the URL directly
            # For private images, use presigned URL
            
            prompt = """Describe this technical image in detail. Include:
1. Type of image (diagram, screenshot, chart, etc.)
2. Key components or elements shown
3. Purpose and what it's explaining
4. Any text, labels, or annotations visible
5. Technical concepts illustrated

Be specific and technical."""
            
            if context:
                prompt += f"\n\nContext from surrounding text:\n{context}"
            
            response = self.openai_client.chat.completions.create(
                model=self.model,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": s3_url,
                                "detail": "high"  # High detail = ~340 tokens
                            }
                        }
                    ]
                }],
                max_tokens=300
            )
            
            return response.choices[0].message.content
        
        except Exception as e:
            print(f"Error generating detailed description: {e}")
            return ""
# Temporary file with the new method to add to ImageProcessor

    def process_and_save_image(
        self,
        image_path: str,
        doc_id: str,
        page_number: int,
        image_type: str = 'screenshot',
        timestamp: Optional[float] = None,
        image_index: int = 0
    ) -> Optional[str]:
        """
        Process a single image from filepath (used for video screenshots).

        Args:
            image_path: Path to image file
            doc_id: Document/Video ID
            page_number: Page number (or minute number for videos)
            image_type: Type of image (screenshot, diagram, etc.)
            timestamp: Optional timestamp for video screenshots
            image_index: Index of image on page (for S3 upload)

        Returns:
            Image ID if successful, None otherwise
        """
        try:
            from database.db_client import DatabaseClient
            import uuid

            # Read and encode image
            with open(image_path, 'rb') as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')

            # Compress image
            compressed_data = self._compress_image(image_data, max_size=512)

            # Generate image ID
            image_id = f"{doc_id}_img_{uuid.uuid4().hex[:12]}"

            # Upload to S3 (match S3ImageStorage.upload_image() signature)
            s3_url = self.s3_storage.upload_image(
                image_base64=compressed_data,
                doc_id=doc_id,
                page_number=page_number,
                image_index=image_index,
                image_format='jpeg'
            )

            if not s3_url:
                print(f"⚠️  Failed to upload image to S3: {image_path}")
                return None

            # Generate basic summary AND extract OCR text (like Docling does!)
            ocr_text = None
            try:
                # First call: Basic visual summary
                summary_prompt = """Briefly describe this image in 1-2 sentences.
Focus on what's shown and its purpose (e.g., 'Settings menu screenshot', 'Code editor with Python file')."""

                summary_response = self.openai_client.chat.completions.create(
                    model=self.model,
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": summary_prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{compressed_data}",
                                    "detail": "low"
                                }
                            }
                        ]
                    }],
                    max_tokens=100
                )

                basic_summary = summary_response.choices[0].message.content
                tokens_used = summary_response.usage.total_tokens

                # Second call: OCR text extraction (critical for multimodal RAG!)
                ocr_prompt = """Extract ALL visible text from this image.
Return ONLY the text content, preserving layout and structure.
If no text is visible, return 'No text detected'."""

                ocr_response = self.openai_client.chat.completions.create(
                    model=self.model,
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": ocr_prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{compressed_data}",
                                    "detail": "high"  # High detail for OCR accuracy!
                                }
                            }
                        ]
                    }],
                    max_tokens=500
                )

                ocr_text = ocr_response.choices[0].message.content
                tokens_used += ocr_response.usage.total_tokens

                # Clean up OCR text
                if ocr_text and ocr_text.strip().lower() != 'no text detected':
                    ocr_text = ocr_text.strip()
                else:
                    ocr_text = None

            except Exception as e:
                print(f"WARNING: Failed to generate summary/OCR for {image_path}: {e}")
                basic_summary = None
                ocr_text = None
                tokens_used = 0

                ocr_prompt = """Extract ALL visible text from this image.
Return ONLY the text content, preserving layout and structure.
If no text is visible, return 'No text detected'."""

                ocr_response = self.openai_client.chat.completions.create(
                    model=self.model,
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": ocr_prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{compressed_data}",
                                    "detail": "high"  # High detail for OCR accuracy!
                                }
                            }
                        ]
                    }],
                    max_tokens=500
                )

                ocr_text = ocr_response.choices[0].message.content
                tokens_used += ocr_response.usage.total_tokens

                # Clean up OCR text
                if ocr_text and ocr_text.strip().lower() != 'no text detected':
                    ocr_text = ocr_text.strip()
                else:
                    ocr_text = None

            except Exception as e:
                print(f"⚠️  Failed to generate summary/OCR for {image_path}: {e}")
                basic_summary = None
                ocr_text = None
                tokens_used = 0

            # Save to database
            db = DatabaseClient()
            try:
                with db.conn.cursor() as cur:
                    # Insert image with timestamp
                    cur.execute("""
                        INSERT INTO images (
                            id, doc_id, page_number, s3_url, image_type,
                            basic_summary, ocr_text, tokens_used, timestamp
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO NOTHING
                    """, (
                        image_id, doc_id, page_number, s3_url, image_type,
                        basic_summary, ocr_text, tokens_used, timestamp
                    ))
                    db.conn.commit()

                print(f"   > Saved screenshot: {image_id}")
                if ocr_text:
                    preview = ocr_text[:80] + '...' if len(ocr_text) > 80 else ocr_text
                    print(f"     OCR: {preview}")

                return image_id

            finally:
                db.conn.close()

        except Exception as e:
            print(f"⚠️  Failed to process image {image_path}: {e}")
            import traceback
            traceback.print_exc()
            return None
