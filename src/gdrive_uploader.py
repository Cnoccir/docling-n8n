"""
Google Drive Uploader
Handles uploading PDFs to Google Drive and retrieving shareable links
"""
import os
import json
from pathlib import Path
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError


class GDriveUploader:
    """Upload PDFs to Google Drive and manage file metadata"""

    def __init__(self, credentials_path: str = None, folder_id: str = None):
        """
        Initialize Google Drive uploader

        Args:
            credentials_path: Path to service account JSON key file
            folder_id: Google Drive folder ID to upload files to
        """
        self.credentials_path = credentials_path or os.getenv('GDRIVE_CREDENTIALS_PATH')
        self.folder_id = folder_id or os.getenv('GDRIVE_FOLDER_ID')

        if not self.credentials_path:
            raise ValueError("GDRIVE_CREDENTIALS_PATH not set")

        if not self.folder_id:
            raise ValueError("GDRIVE_FOLDER_ID not set")

        # Initialize Google Drive service
        self.service = self._build_service()

    def _build_service(self):
        """Build Google Drive API service"""
        creds = service_account.Credentials.from_service_account_file(
            self.credentials_path,
            scopes=['https://www.googleapis.com/auth/drive.file']
        )
        return build('drive', 'v3', credentials=creds)

    def upload_pdf(
        self,
        pdf_path: str,
        doc_title: str,
        doc_id: str = None
    ) -> dict:
        """
        Upload PDF to Google Drive

        Args:
            pdf_path: Local path to PDF file
            doc_title: Title for the file in Google Drive
            doc_id: Optional document ID for metadata

        Returns:
            dict with file_id, link, and folder_id
        """
        try:
            # Prepare file metadata
            file_metadata = {
                'name': f"{doc_title}.pdf",
                'parents': [self.folder_id],
                'description': f'Document ID: {doc_id}' if doc_id else ''
            }

            # Upload file
            media = MediaFileUpload(
                pdf_path,
                mimetype='application/pdf',
                resumable=True
            )

            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, webViewLink, webContentLink'
            ).execute()

            # Make file publicly accessible (anyone with link can view)
            self._set_public_permissions(file['id'])

            return {
                'file_id': file['id'],
                'link': file['webViewLink'],
                'download_link': file.get('webContentLink'),
                'folder_id': self.folder_id
            }

        except HttpError as error:
            print(f'Error uploading to Google Drive: {error}')
            raise

    def _set_public_permissions(self, file_id: str):
        """Make file accessible to anyone with the link"""
        try:
            permission = {
                'type': 'anyone',
                'role': 'reader'
            }
            self.service.permissions().create(
                fileId=file_id,
                body=permission
            ).execute()
        except HttpError as error:
            print(f'Error setting permissions: {error}')
            # Don't fail upload if permissions fail

    def delete_file(self, file_id: str):
        """Delete file from Google Drive"""
        try:
            self.service.files().delete(fileId=file_id).execute()
            return True
        except HttpError as error:
            print(f'Error deleting file: {error}')
            return False

    def get_file_info(self, file_id: str) -> dict:
        """Get file metadata from Google Drive"""
        try:
            file = self.service.files().get(
                fileId=file_id,
                fields='id, name, webViewLink, createdTime, size'
            ).execute()
            return file
        except HttpError as error:
            print(f'Error getting file info: {error}')
            return None

    def check_file_exists(self, doc_title: str) -> dict:
        """Check if file with same name already exists in folder"""
        try:
            query = f"name='{doc_title}.pdf' and '{self.folder_id}' in parents and trashed=false"
            results = self.service.files().list(
                q=query,
                fields='files(id, name, webViewLink)'
            ).execute()

            files = results.get('files', [])
            return files[0] if files else None

        except HttpError as error:
            print(f'Error checking file existence: {error}')
            return None


def test_gdrive_upload():
    """Test Google Drive upload functionality"""
    uploader = GDriveUploader()

    # Test with a sample PDF
    test_pdf = "test_data/sample.pdf"
    if not os.path.exists(test_pdf):
        print(f"Test PDF not found: {test_pdf}")
        return

    result = uploader.upload_pdf(
        pdf_path=test_pdf,
        doc_title="Test Document",
        doc_id="test_123"
    )

    print("Upload successful!")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    test_gdrive_upload()
