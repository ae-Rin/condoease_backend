from azure.storage.blob import BlobServiceClient
import os
import uuid

account = os.getenv("AZURE_STORAGE_ACCOUNT")
key = os.getenv("AZURE_STORAGE_KEY")
blob_service = BlobServiceClient.from_connection_string(
     f"DefaultEndpointsProtocol=https;"
     f"AccountName={account};"
     f"AccountKey={key};"
     f"EndpointSuffix=core.windows.net"
)

def upload_to_blob(file, container: str, user_id: str | int):
     ext = os.path.splitext(file.filename)[1]
     filename = f"{user_id}/{uuid.uuid4()}{ext}"
     blob_client = blob_service.get_blob_client(container=container, blob=filename)
     blob_client.upload_blob(file.file, overwrite=True)
     return f"https://{account}.blob.core.windows.net/{container}/{filename}"

def delete_from_blob(blob_url: str):
     """
     Deletes a file from Azure Blob Storage using its full URL
     """
     parts = blob_url.split("/")
     container = parts[-2]
     blob_name = parts[-1]
     blob_client = blob_service.get_blob_client(
          container=container,
          blob=blob_name
     )
     blob_client.delete_blob()
