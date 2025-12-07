# filepath: /home/azureuser/medapp-backend/services/medfiles/app/app.py
import asyncio
import base64
import os
from typing import Optional

import uvicorn
from fastapi import FastAPI, Depends, Form, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse

from models.file_models import FileResponse, FileListResponse, FileMetadata
from services.auth_service import get_current_user
from services.logger_service import LoggerService
from services.minio_service import MinioService

logger = LoggerService()

app = FastAPI(
    title="MedApp Files Service",
    description="Service for handling medical file uploads and storage",
    version="1.0.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

minio_service = MinioService()


@app.on_event("startup")
async def startup_event():
    # Create default buckets if they don't exist
    await minio_service.create_bucket("medicalimages")
    await minio_service.create_bucket("radiologyimages")
    await minio_service.create_bucket("patientdocuments")
    logger.info("MedFiles service started")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


@app.post("/api/files/upload", response_model=FileResponse)
async def upload_file(
        file: UploadFile = File(...),
        bucket: str = Form(...),
        folder: Optional[str] = Form(None),
        metadata: Optional[str] = Form(None),
        user_info: dict = Depends(get_current_user),
):
    """
    Upload a medical file to the specified bucket
    """
    try:
        logger.info(f"Uploading file {file.filename} to bucket {bucket}")

        if metadata is None:
            metadata = {}

        # Add user info to metadata
        metadata["uploaded_by"] = user_info.get("user_id")
        metadata["user_role"] = ",".join(user_info.get("roles", []))

        result = await minio_service.upload_file(
            bucket_name=bucket,
            file_object=file,
            folder_path=folder,
            metadata=metadata,
        )

        logger.info(f"Successfully uploaded file {file.filename}")
        return result
    except Exception as e:
        logger.error(f"Error uploading file: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error uploading file: {str(e)}")


@app.get("/api/files/{bucket}/{object_path:path}", response_model=FileResponse)
async def get_file_info(
        bucket: str,
        object_path: str,
        user_info: dict = Depends(get_current_user),
):
    """
    Get information about a specific file including a download URL
    """
    try:
        logger.info(f"Getting file info for {object_path} from bucket {bucket}")
        file_info = await minio_service.get_file_info(bucket, object_path)

        # Generate streaming URL
        streaming_url = await minio_service.generate_streaming_url(bucket, object_path)
        file_info.download_url = streaming_url

        return file_info
    except Exception as e:
        logger.error(f"Error getting file info: {str(e)}")
        raise HTTPException(status_code=404, detail=f"File not found: {str(e)}")


@app.get("/api/files/{bucket}", response_model=FileListResponse)
async def list_files(
        bucket: str,
        prefix: Optional[str] = Query(None, description="Filter by prefix/folder"),
        recursive: bool = Query(
            False, description="List files recursively including all subfolders"
        ),
        limit: int = Query(100, description="Maximum number of files to return"),
        marker: Optional[str] = Query(None, description="Marker for pagination"),
        user_info: dict = Depends(get_current_user),
):
    """
    List files and folders in a bucket with optional prefix filtering, including download URLs
    """
    try:
        logger.info(f"Listing files in bucket {bucket} with prefix {prefix}")
        result = await minio_service.list_files(
            bucket, prefix, limit, recursive=recursive, marker=marker
        )

        # Generate streaming URLs for each file
        for file in result["files"]:
            file.download_url = await minio_service.generate_streaming_url(
                bucket, file.object_name
            )

        response = FileListResponse(
            files=result["files"],
            folders=result["folders"],
            total_files=len(result["files"]),
            total_folders=len(result["folders"]),
            marker=result.get("marker"),
            bucket=bucket,
            prefix=prefix,
        )
        return response
    except Exception as e:
        logger.error(f"Error listing files: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error listing files: {str(e)}")


@app.delete("/api/files/{bucket}/{object_path:path}")
async def delete_file(
        bucket: str,
        object_path: str,
        user_info: dict = Depends(get_current_user),
):
    """
    Delete a file from storage
    """
    try:
        logger.info(f"Deleting file {object_path} from bucket {bucket}")

        # Check if user has admin role
        if "admin" not in user_info.get("roles", []):
            # Check if user is the owner of the file
            file_info = await minio_service.get_file_info(bucket, object_path)
            if file_info.metadata.get("uploaded_by") != user_info.get("user_id"):
                raise HTTPException(
                    status_code=403, detail="Not authorized to delete this file"
                )

        await minio_service.delete_file(bucket, object_path)
        logger.info(f"Successfully deleted file {object_path}")
        return {"message": "File deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting file: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error deleting file: {str(e)}")


@app.put("/api/files/{bucket}/{object_path:path}/metadata")
async def update_file_metadata(
        bucket: str,
        object_path: str,
        metadata: FileMetadata,
        user_info: dict = Depends(get_current_user),
):
    """
    Update metadata for a specific file
    """
    try:
        logger.info(f"Updating metadata for {object_path} in bucket {bucket}")
        await minio_service.update_metadata(bucket, object_path, metadata.dict())
        return {"message": "Metadata updated successfully"}
    except Exception as e:
        logger.error(f"Error updating metadata: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error updating metadata: {str(e)}"
        )


@app.get("/api/v1/download-shared-object/{encoded_url}")
async def download_shared_object(encoded_url: str):
    """
    Proxy endpoint for downloading shared files using an encoded URL
    This allows sharing files without requiring authentication
    """
    try:
        # Decode the URL from base64
        decoded_bytes = base64.b64decode(encoded_url)
        original_url = decoded_bytes.decode("utf-8")

        logger.info(f"Processing shared download request for: {original_url}")

        # Redirect to the actual presigned URL
        return RedirectResponse(url=original_url)
    except Exception as e:
        logger.error(f"Error processing shared download: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Invalid or expired download link")


@app.post("/api/files/{bucket}/share/{object_path:path}", response_model=dict)
async def create_share_link(
        bucket: str,
        object_path: str,
        expiry_hours: int = Query(24, description="Link expiry in hours"),
        user_info: dict = Depends(get_current_user),
):
    """
    Create a shareable link for a file
    """
    try:
        logger.info(f"Creating share link for {object_path} in bucket {bucket}")

        # Encode the object path in base64 for security/obfuscation
        encoded_object = base64.b64encode(object_path.encode()).decode()

        # Construct the full shareable streaming URL
        host = os.getenv("SERVICE_HOST", "localhost")
        port = os.getenv("PORT", "8088")
        base_url = f"http://{host}:{port}"
        share_url = f"{base_url}/api/v1/stream-shared-object/{bucket}/{encoded_object}"

        return {
            "share_url": share_url,
            "type": "streaming",
            "note": "This link provides direct streaming access to the file"
        }
    except Exception as e:
        logger.error(f"Error creating share link: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error creating share link: {str(e)}"
        )


@app.get("/api/files/{bucket}/stream/{object_path:path}")
async def stream_file(
        bucket: str,
        object_path: str,
        user_info: dict = Depends(get_current_user),
):
    """
    Stream a file directly from storage
    """
    try:
        logger.info(f"Streaming file {object_path} from bucket {bucket}")

        # Get file info first to verify existence and get content type
        stat = await minio_service.get_file_info(bucket, object_path)

        # Get file stream
        file_stream = await minio_service.get_file_stream(bucket, object_path)

        # Return streaming response with appropriate headers
        return StreamingResponse(
            file_stream,
            media_type=stat.content_type,
            headers={
                "Content-Disposition": f"inline; filename=\"{stat.filename}\"",
            }
        )
    except Exception as e:
        logger.error(f"Error streaming file: {str(e)}")
        raise HTTPException(status_code=404, detail=f"File not found: {str(e)}")


@app.get("/api/v1/stream-shared-object/{bucket}/{object_id:path}")
async def stream_shared_object(
        bucket: str,
        object_id: str,
):
    """
    Stream a file without authentication for sharing purposes
    The object_id is expected to be a Base64 encoded string to obfuscate the real object name
    """
    try:
        # Decode the object name from base64
        try:
            decoded_bytes = base64.b64decode(object_id)
            object_path = decoded_bytes.decode("utf-8")
        except:
            raise HTTPException(status_code=400, detail="Invalid object identifier")

        logger.info(f"Processing shared stream request for: {object_path} in {bucket}")

        # Get file info to verify existence and get content type
        try:
            stat = await asyncio.get_event_loop().run_in_executor(
                minio_service.executor,
                lambda: minio_service.client.stat_object(bucket, object_path)
            )
        except:
            raise HTTPException(status_code=404, detail="File not found")

        # Get file stream
        file_stream = await minio_service.get_file_stream(bucket, object_path)

        # Return streaming response with appropriate headers
        filename = stat.metadata.get("filename", object_path.split("/")[-1])
        return StreamingResponse(
            file_stream,
            media_type=stat.content_type,
            headers={
                "Content-Disposition": f"inline; filename=\"{filename}\"",
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error streaming shared file: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing shared stream: {str(e)}")


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8088))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)
