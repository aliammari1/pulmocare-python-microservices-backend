import asyncio
import os
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import aiofiles
import magic
from fastapi import UploadFile
from minio import Minio
from minio.error import S3Error

from config import Config
from models.file_models import FileInfo, FileResponse
from services.logger_service import LoggerService

logger = LoggerService()


class MinioService:
    """Service for interacting with MinIO S3 Storage"""

    def __init__(self):
        self.client = Minio(
            f"{Config.MINIO_HOST}:{Config.MINIO_PORT}",
            access_key=Config.MINIO_ACCESS_KEY,
            secret_key=Config.MINIO_SECRET_KEY,
            region=Config.MINIO_REGION,
            secure=Config.MINIO_SECURE.lower() == "true",
        )

        self.executor = ThreadPoolExecutor(max_workers=4)

    async def create_bucket(self, bucket_name: str) -> bool:
        """Create a bucket if it doesn't exist"""
        try:
            exists = await asyncio.get_event_loop().run_in_executor(self.executor, lambda: self.client.bucket_exists(bucket_name))
            if not exists:
                await asyncio.get_event_loop().run_in_executor(self.executor, lambda: self.client.make_bucket(bucket_name))
                logger.info(f"Created bucket: {bucket_name}")
            return True
        except S3Error as e:
            logger.error(f"Error creating bucket {bucket_name}: {e!s}")
            return False

    async def upload_file(
        self,
        bucket_name: str,
        file_object: UploadFile,
        folder_path: str | None = None,
        metadata: dict | None = None,
    ) -> FileResponse:
        """
        Upload a file to MinIO

        Args:
            bucket_name: Name of the bucket
            file_object: FastAPI UploadFile object
            folder_path: Optional folder path within the bucket
            metadata: Optional metadata to attach to the file

        Returns:
            FileResponse with file information
        """
        try:
            # Generate a unique object name
            file_uuid = str(uuid.uuid4())
            file_ext = os.path.splitext(file_object.filename)[1].lower()

            if folder_path:
                # Remove leading and trailing slashes, ensure single trailing slash
                folder_path = folder_path.strip("/")
                object_name = f"{folder_path}/{file_uuid}{file_ext}"
            else:
                object_name = f"{file_uuid}{file_ext}"

            # Create temporary file to get content type and file size
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                # Read file content
                content = await file_object.read()
                await file_object.seek(0)

                # Write to temp file
                temp_file.write(content)
                temp_filename = temp_file.name

            try:
                # Detect file type with python-magic
                content_type = magic.from_file(temp_filename, mime=True)
                file_size = os.path.getsize(temp_filename)

                # Prepare metadata
                if metadata is None:
                    metadata = {}

                metadata.update(
                    {
                        "filename": file_object.filename,
                        "content_type": content_type,
                        "size": str(file_size),
                        "uuid": file_uuid,
                    }
                )

                # Upload file from temp file
                await asyncio.get_event_loop().run_in_executor(
                    self.executor,
                    lambda: self.client.fput_object(
                        bucket_name,
                        object_name,
                        temp_filename,
                        content_type=content_type,
                        metadata=metadata,
                    ),
                )

                # Create presigned URL for temporary access
                presigned_url = await asyncio.get_event_loop().run_in_executor(
                    self.executor,
                    lambda: self.client.presigned_get_object(bucket_name, object_name, expires=timedelta(hours=1)),
                )

                logger.info(f"File uploaded: {object_name} to bucket {bucket_name}")

                return FileResponse(
                    bucket=bucket_name,
                    object_name=object_name,
                    filename=file_object.filename,
                    content_type=content_type,
                    size=file_size,
                    url=presigned_url,
                    metadata=metadata,
                )
            finally:
                # Clean up temp file
                if os.path.exists(temp_filename):
                    os.unlink(temp_filename)

        except S3Error as e:
            logger.error(f"S3 error uploading file: {e!s}")
            raise
        except Exception as e:
            logger.error(f"Error uploading file: {e!s}")
            raise

    async def get_file_info(self, bucket_name: str, object_name: str) -> FileResponse:
        """Get information about a specific file"""
        try:
            # Get object stats
            stat = await asyncio.get_event_loop().run_in_executor(self.executor, lambda: self.client.stat_object(bucket_name, object_name))

            # Create presigned URL for temporary access
            presigned_url = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: self.client.presigned_get_object(bucket_name, object_name, expires=timedelta(hours=1)),
            )

            # Extract original filename from metadata
            filename = stat.metadata.get("filename", object_name.split("/")[-1])

            return FileResponse(
                bucket=bucket_name,
                object_name=object_name,
                filename=filename,
                content_type=stat.content_type,
                size=stat.size,
                url=presigned_url,
                metadata=stat.metadata,
                created_at=stat.last_modified.isoformat(),
            )
        except S3Error as e:
            logger.error(f"S3 error getting file info: {e!s}")
            raise
        except Exception as e:
            logger.error(f"Error getting file info: {e!s}")
            raise

    async def list_files(
        self,
        bucket_name: str,
        prefix: str | None = None,
        limit: int = 100,
        recursive: bool = False,
        marker: str | None = None,
        download_expiry: int = 3600,  # Default 1 hour for download links
    ) -> dict:
        """
        List files in a bucket with optional prefix filtering

        Args:
            bucket_name: Name of the bucket
            prefix: Optional folder path prefix to filter results
            limit: Maximum number of results to return
            recursive: If True, lists all objects recursively (including nested folders)
            marker: Object name to start listing after (for pagination)
            download_expiry: Expiration time in seconds for download URLs (default: 1 hour)

        Returns:
            Dictionary with files, folders, and pagination information
        """
        try:
            files = []
            folders = set()
            delimiter = "/" if not recursive else ""

            # Ensure prefix ends with / if it's provided and doesn't already and not in recursive mode
            if prefix and not prefix.endswith("/") and not recursive:
                prefix = f"{prefix}/"

            # Use list_objects_v2 with delimiter for better folder handling
            objects = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: list(
                    self.client.list_objects(
                        bucket_name,
                        prefix=prefix or "",
                        recursive=recursive,
                        start_after=marker,
                    )
                ),
            )

            count = 0
            last_object = None

            # Process each item up to the limit
            for item in objects:
                last_object = item.object_name

                if count >= limit:
                    break

                # Check if this is a folder indicator (common prefix)
                if not recursive and item.is_dir:
                    folders.add(item.object_name)
                    count += 1
                    continue

                # Check if this is a nested path that should be interpreted as a folder
                if not recursive and "/" in item.object_name[len(prefix or "") :]:
                    # Extract folder name
                    rest_path = item.object_name[len(prefix or "") :]
                    folder_name = rest_path.split("/")[0]

                    if prefix:
                        folder_path = f"{prefix}{folder_name}/"
                    else:
                        folder_path = f"{folder_name}/"

                    folders.add(folder_path)
                else:
                    # This is a file - get metadata
                    try:
                        # Get object stats
                        stat = await asyncio.get_event_loop().run_in_executor(
                            self.executor,
                            lambda: self.client.stat_object(bucket_name, item.object_name),
                        )

                        # Extract original filename from metadata if available
                        filename = stat.metadata.get("filename", item.object_name.split("/")[-1])

                        # Generate streaming URL instead of download URL
                        streaming_url = await self.generate_streaming_url(bucket_name, item.object_name, expires=download_expiry)

                        # Generate regular download URL as well for direct downloads
                        download_url = await self.generate_presigned_url(bucket_name, item.object_name, expires=download_expiry)

                        # Add file info to results with streaming URL as the download URL
                        files.append(
                            FileInfo(
                                bucket=bucket_name,
                                object_name=item.object_name,
                                filename=filename,
                                content_type=stat.content_type,
                                size=item.size,
                                last_modified=item.last_modified.isoformat(),
                                download_url=streaming_url,  # Use streaming URL
                                metadata=stat.metadata,
                            )
                        )
                    except Exception as e:
                        # Handle case where metadata retrieval fails
                        logger.warning(f"Error getting metadata for {item.object_name}: {e!s}")

                        # Generate basic streaming URL instead of download URL
                        streaming_url = await self.generate_streaming_url(bucket_name, item.object_name, expires=download_expiry)

                        # Add file with limited info, using streaming URL
                        files.append(
                            FileInfo(
                                bucket=bucket_name,
                                object_name=item.object_name,
                                filename=item.object_name.split("/")[-1],
                                size=item.size,
                                last_modified=item.last_modified.isoformat(),
                                download_url=streaming_url,  # Use streaming URL
                            )
                        )

                    count += 1

            # Convert folders set to list of dicts with name and path
            folder_list = [{"name": f.rstrip("/").split("/")[-1], "path": f} for f in sorted(folders)]

            return {
                "files": files,
                "folders": folder_list,
                "marker": last_object if count >= limit else None,
                "prefix": prefix,
            }
        except S3Error as e:
            logger.error(f"S3 error listing files: {e!s}")
            raise
        except Exception as e:
            logger.error(f"Error listing files: {e!s}")
            raise

    async def delete_file(self, bucket_name: str, object_name: str) -> bool:
        """Delete a file from storage"""
        try:
            await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: self.client.remove_object(bucket_name, object_name),
            )
            logger.info(f"File deleted: {object_name} from bucket {bucket_name}")
            return True
        except S3Error as e:
            logger.error(f"S3 error deleting file: {e!s}")
            raise
        except Exception as e:
            logger.error(f"Error deleting file: {e!s}")
            raise

    async def update_metadata(self, bucket_name: str, object_name: str, metadata: dict) -> bool:
        """
        Update metadata for a specific file
        This requires copying the object with new metadata as S3 doesn't support direct metadata updates
        """
        try:
            # Get current object info
            stat = await asyncio.get_event_loop().run_in_executor(self.executor, lambda: self.client.stat_object(bucket_name, object_name))

            # Merge existing metadata with new metadata
            current_metadata = stat.metadata
            current_metadata.update(metadata)

            # Copy object to itself with new metadata
            await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: self.client.copy_object(
                    bucket_name,
                    object_name,
                    f"{bucket_name}/{object_name}",
                    metadata=current_metadata,
                ),
            )

            logger.info(f"Updated metadata for {object_name} in bucket {bucket_name}")
            return True
        except S3Error as e:
            logger.error(f"S3 error updating metadata: {e!s}")
            raise
        except Exception as e:
            logger.error(f"Error updating metadata: {e!s}")
            raise

    async def generate_presigned_url(self, bucket_name: str, object_name: str, expires=43200) -> str:
        """
        Generate a presigned URL for an object

        Args:
            bucket_name: Name of the bucket
            object_name: Name of the object
            expires: Expiration time in seconds (default: 12 hours)

        Returns:
            Presigned URL string
        """
        try:
            # Convert seconds to timedelta for MinIO client
            expires_delta = timedelta(hours=2)

            # Generate URL using MinIO client
            url = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: self.client.get_presigned_url("GET", bucket_name, object_name, expires=expires_delta),
            )
            print(f"Presigned URL: {self.client.get_presigned_url('GET', bucket_name, object_name, expires=expires_delta)}")
            logger.info(f"Generated presigned URL for {bucket_name}/{object_name} " + f"with expiry {expires} seconds")

            return url
        except S3Error as e:
            logger.error(f"S3 error generating presigned URL: {e!s}")
            raise Exception(f"Failed to generate download link: {e!s}")
        except Exception as e:
            logger.error(f"Error generating presigned URL: {e!s}")
            raise Exception(f"Failed to generate download link: {e!s}")

    async def generate_streaming_url(self, bucket_name: str, object_name: str, expires=43200) -> str:
        """
        Generate a streaming URL for an object

        This URL will be used to send the object as a stream to the frontend

        Args:
            bucket_name: Name of the bucket
            object_name: Name of the object
            expires: Expiration time in seconds (default: 12 hours)

        Returns:
            Streaming URL string
        """
        try:
            # Instead of generating a presigned URL, we'll create a URL to our stream endpoint
            host = os.getenv("SERVICE_HOST", "localhost")
            port = os.getenv("PORT", "8088")

            # Construct API URL to our streaming endpoint with the new path format
            stream_url = f"http://{host}:{port}/api/files/{bucket_name}/stream/{object_name}"

            logger.info(f"Generated streaming URL for {bucket_name}/{object_name}")

            return stream_url
        except Exception as e:
            logger.error(f"Error generating streaming URL: {e!s}")
            raise Exception(f"Failed to generate streaming link: {e!s}")

    async def get_file_stream(self, bucket_name: str, object_name: str):
        """
        Get a file stream directly from storage using fget_object

        Args:
            bucket_name: Name of the bucket
            object_name: Name of the object

        Returns:
            AsyncGenerator yielding file content in chunks
        """
        try:
            # Create a temporary file to store the object
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                temp_file_path = temp_file.name

            # Get object data using fget_object
            await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: self.client.fget_object(bucket_name, object_name, temp_file_path),
            )

            # Define async generator to yield file content in chunks
            async def file_generator():
                try:
                    async with aiofiles.open(temp_file_path, "rb") as f:
                        chunk = await f.read(8192)  # Read 8KB chunks
                        while chunk:
                            yield chunk
                            chunk = await f.read(8192)
                finally:
                    # Clean up the temporary file
                    if os.path.exists(temp_file_path):
                        os.unlink(temp_file_path)

            logger.info(f"Streaming file {object_name} from bucket {bucket_name}")
            return file_generator()

        except S3Error as e:
            logger.error(f"S3 error getting file stream: {e!s}")
            raise Exception(f"Failed to get file stream: {e!s}")
        except Exception as e:
            logger.error(f"Error getting file stream: {e!s}")
            raise Exception(f"Failed to get file stream: {e!s}")
