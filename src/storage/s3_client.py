"""S3 storage client for images."""
import os
import boto3
import base64
from typing import Optional
from botocore.exceptions import ClientError


class S3ImageStorage:
    """Handle image storage in S3."""
    
    def __init__(self):
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name=os.getenv('AWS_REGION', 'us-east-1')
        )
        # Use S3_BUCKET (not S3_BUCKET_NAME) to match your .env
        self.bucket_name = os.getenv('S3_BUCKET')
        self.public_base = os.getenv('S3_PUBLIC_BASE')
        
        if not self.bucket_name:
            raise ValueError("S3_BUCKET environment variable not set")
    
    def upload_image(
        self,
        image_base64: str,
        doc_id: str,
        page_number: int,
        image_index: int,
        image_format: str = 'jpeg'
    ) -> str:
        """
        Upload image to S3 and return URL.
        
        Args:
            image_base64: Base64 encoded image
            doc_id: Document ID
            page_number: Page number
            image_index: Image index on page
            image_format: Image format (jpeg, png)
        
        Returns:
            S3 URL of uploaded image
        """
        # Decode base64
        image_bytes = base64.b64decode(image_base64)
        
        # Build S3 key with organized structure
        s3_key = f"documents/{doc_id}/images/page_{page_number:04d}_img_{image_index:02d}.{image_format}"
        
        try:
            # Upload to S3 (without ACL - bucket doesn't support ACLs)
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=image_bytes,
                ContentType=f'image/{image_format}',
                CacheControl='max-age=31536000'  # 1 year cache
                # Removed ACL='public-read' - bucket doesn't allow ACLs
            )
            
            # Generate URL using public base if available
            if self.public_base:
                url = f"{self.public_base}/{s3_key}"
            else:
                url = f"https://{self.bucket_name}.s3.amazonaws.com/{s3_key}"
            
            return url
        
        except ClientError as e:
            print(f"Error uploading image to S3: {e}")
            raise
    
    def get_presigned_url(self, s3_url: str, expiration: int = 3600) -> str:
        """
        Generate a presigned URL for private images.
        
        Args:
            s3_url: Full S3 URL
            expiration: URL expiration time in seconds (default 1 hour)
        
        Returns:
            Presigned URL
        """
        # Extract key from URL
        if self.public_base and self.public_base in s3_url:
            s3_key = s3_url.replace(f"{self.public_base}/", "")
        else:
            s3_key = s3_url.split(f'{self.bucket_name}.s3.amazonaws.com/')[-1]
        
        try:
            presigned_url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.bucket_name,
                    'Key': s3_key
                },
                ExpiresIn=expiration
            )
            return presigned_url
        
        except ClientError as e:
            print(f"Error generating presigned URL: {e}")
            return s3_url  # Fallback to original URL
    
    def delete_image(self, s3_url: str) -> bool:
        """
        Delete image from S3.
        
        Args:
            s3_url: Full S3 URL
        
        Returns:
            True if successful
        """
        # Extract key from URL
        if self.public_base and self.public_base in s3_url:
            s3_key = s3_url.replace(f"{self.public_base}/", "")
        else:
            s3_key = s3_url.split(f'{self.bucket_name}.s3.amazonaws.com/')[-1]
        
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )
            return True
        
        except ClientError as e:
            print(f"Error deleting image from S3: {e}")
            return False
    
    def delete_document_images(self, doc_id: str) -> int:
        """
        Delete all images for a document.
        
        Args:
            doc_id: Document ID
        
        Returns:
            Number of images deleted
        """
        prefix = f"documents/{doc_id}/images/"
        
        try:
            # List objects with prefix
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix
            )
            
            if 'Contents' not in response:
                return 0
            
            # Delete all objects
            objects_to_delete = [{'Key': obj['Key']} for obj in response['Contents']]
            
            if objects_to_delete:
                self.s3_client.delete_objects(
                    Bucket=self.bucket_name,
                    Delete={'Objects': objects_to_delete}
                )
            
            return len(objects_to_delete)
        
        except ClientError as e:
            print(f"Error deleting document images from S3: {e}")
            return 0
    
    def upload_batch(
        self,
        images_data: list[dict],
        doc_id: str
    ) -> list[str]:
        """
        Upload multiple images in batch.
        
        Args:
            images_data: List of dicts with keys: base64, page_number, image_index, format
            doc_id: Document ID
        
        Returns:
            List of S3 URLs
        """
        urls = []
        
        for img_data in images_data:
            try:
                url = self.upload_image(
                    image_base64=img_data['base64'],
                    doc_id=doc_id,
                    page_number=img_data['page_number'],
                    image_index=img_data['image_index'],
                    image_format=img_data.get('format', 'jpeg')
                )
                urls.append(url)
            except Exception as e:
                print(f"Error uploading image {img_data.get('image_index')}: {e}")
                urls.append(None)
        
        return urls
