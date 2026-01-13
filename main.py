import shutil
import time
import os       
from typing import List, Optional
import uuid
from fastapi import FastAPI, APIRouter, Form, Request, Depends, HTTPException, status, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from jose import JWTError, jwt
from passlib.context import CryptContext
import pymssql
from dotenv import load_dotenv
import uvicorn
from uuid import uuid4
from datetime import datetime, timedelta
from decimal import Decimal
from azure_blob import upload_to_blob

# Load .env
load_dotenv()
SECRET_KEY = os.getenv("JWT_SECRET")
ALGORITHM = "HS256"

# Bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Azure SQL config for pymssql
def get_db():
    try:
        conn = pymssql.connect(
            server=os.getenv("DB_SERVER"),
            port=int(os.getenv("DB_PORT")),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASS"),
            database=os.getenv("DB_NAME"),
        )
        return conn
    except Exception as e:
        print("Database connection failed:", e)
        raise

def clean_row(row):
    safe = {}
    for k, v in row.items():
        if isinstance(v, datetime):
            safe[k] = v.isoformat()
        elif isinstance(v, Decimal):
            safe[k] = float(v)
        else:
            safe[k] = v
    return safe
# App instance
app = FastAPI()

# CORS
origins = os.getenv("CORS_ORIGINS", "").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static uploads
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# Auth Schemas
class RegisterRequest(BaseModel):
    firstName: str
    lastName: str
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str
    
class MaintenanceRequest(BaseModel):
    maintenance_type: str
    category: str
    description: str
    attachment: Optional[str] = None
    
class MaintenanceDecision(BaseModel):
    status: str
    comment: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    def _clean(self, data):
        if isinstance(data, dict):
            return {k: self._clean(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._clean(v) for v in data]
        elif isinstance(data, datetime):
            return data.isoformat()
        elif isinstance(data, Decimal):
            return float(data)
        else:
            return data

    async def broadcast(self, message: dict):
        safe_message = self._clean(message)

        for connection in self.active_connections:
            try:
                await connection.send_json(safe_message)
            except Exception:
                self.disconnect(connection)

ws_manager = ConnectionManager()

@app.websocket("/ws/announcements")
async def announcement_ws(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)

# Token Auth Dependency
def verify_token(request: Request):
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = auth.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(status_code=403, detail="Invalid token")

@app.post("/api/registerstep2")
def register_user(body: RegisterRequest):
    db = get_db()
    cursor = db.cursor()
    hashed = pwd_context.hash(body.password)
    try:
        cursor.execute("""
            INSERT INTO users (first_name, last_name, email, password, role)
            VALUES (%s, %s, %s, %s, %s)
        """, (body.firstName, body.lastName, body.email, hashed, "tenant"))
        db.commit()
        return {"success": True}
    except Exception as e:
        print("Registration error:", e)
        raise HTTPException(status_code=500, detail="Registration failed")

@app.post("/api/login")
def login_user(body: LoginRequest):
    db = get_db()
    cursor = db.cursor(as_dict=True)
    cursor.execute("SELECT * FROM users WHERE email = %s", (body.email,))
    user = cursor.fetchone()

    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not pwd_context.verify(body.password, user['password']):
        raise HTTPException(status_code=401, detail="Incorrect password")

    token = jwt.encode(
        {
            "id": user['id'],
            "role": user['role'],
            "exp": datetime.utcnow() + timedelta(hours=12)
        },
        SECRET_KEY,
        algorithm=ALGORITHM
    )
    return {"token": token, "user": {
        "id": user['id'],
        "email": user['email'],
        "first_name": user['first_name'],
        "last_name": user['last_name'],
        "role": user['role']
    }}

@app.put("/api/users/avatar")
def update_avatar(avatar: UploadFile = File(...), token: dict = Depends(verify_token)):
    user_id = token.get("id")
    filename = f"{int(time.time())}-{avatar.filename.replace(' ', '_')}"
    file_path = os.path.join(UPLOAD_DIR, filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(avatar.file, buffer)

    db = get_db()
    cursor = db.cursor()
    cursor.execute("UPDATE users SET avatar = %s WHERE id = %s", (f"/uploads/{filename}", user_id))
    db.commit()
    return {"avatar": f"/uploads/{filename}"}

@app.put("/api/users/{user_id}")
def update_user_profile(user_id: int, firstName: Optional[str] = Form(None), lastName: Optional[str] = Form(None), email: Optional[str] = Form(None), password: Optional[str] = Form(None), currentPassword: Optional[str] = Form(None), token: dict = Depends(verify_token)):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT password FROM users WHERE id = %s", (user_id,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    stored_hashed_password = row[0]
    updates = []
    params = []

    if firstName and lastName:
        updates += ["first_name = %s", "last_name = %s"]
        params += [firstName, lastName]

    if email:
        updates.append("email = %s")
        params.append(email)

    if currentPassword and password and currentPassword != password:
        if not pwd_context.verify(currentPassword, stored_hashed_password):
            raise HTTPException(status_code=401, detail="Incorrect current password")
        new_hashed = pwd_context.hash(password)
        updates.append("password = %s")
        params.append(new_hashed)

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    params.append(user_id)
    cursor.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = %s", tuple(params))
    db.commit()
    return {"success": True}

@app.put("/api/maintenance-requests/{request_id}")
def update_maintenance_request(
    request_id: int,
    body: MaintenanceDecision,
    token: dict = Depends(verify_token),
):
    role = token.get("role")
    if role not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Unauthorized")

    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("""
            SELECT id FROM maintenance_requests WHERE id = %s
        """, (request_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Maintenance request not found")

        cursor.execute("""
            UPDATE maintenance_requests
            SET
                status = %s,
                admin_comment = %s,
                scheduled_at = %s,
                updated_at = GETDATE()
            WHERE id = %s
        """, (
            body.status,
            body.comment,
            body.scheduled_at,
            request_id
        ))

        db.commit()
        return {"success": True, "message": "Maintenance request updated"}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print("❌ Update maintenance error:", str(e))
        raise HTTPException(status_code=500, detail="Failed to update maintenance request")
    
@app.put("/api/maintenance-ongoing/{request_id}/complete")
def complete_maintenance_request(
    request_id: int,
    resolution_summary: str = Form(...),
    total_cost: Optional[float] = Form(None),
    warranty_info: Optional[str] = Form(None),
    invoice: Optional[UploadFile] = File(None),
    token: dict = Depends(verify_token),
):
    role = token.get("role")
    if role not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Unauthorized")

    db = get_db()
    cursor = db.cursor()

    try:
        cursor.execute("""
            SELECT status FROM maintenance_requests WHERE id = %s
        """, (request_id,))
        row = cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Maintenance request not found")

        if row[0] != "ongoing":
            raise HTTPException(
                status_code=400,
                detail="Only ongoing requests can be completed"
            )

        cursor.execute("""
            UPDATE maintenance_requests
            SET
                status = 'completed',
                resolution_summary = %s,
                completed_at = GETDATE(),
                total_cost = %s,
                warranty_info = %s,
                updated_at = GETDATE()
            WHERE id = %s
        """, (
            resolution_summary,
            total_cost,
            warranty_info,
            request_id
        ))

        if invoice:
            ext = os.path.splitext(invoice.filename)[-1]
            filename = f"invoice_{uuid.uuid4()}{ext}"
            file_path = os.path.join(UPLOAD_DIR, filename)

            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(invoice.file, buffer)

            cursor.execute("""
                INSERT INTO maintenance_attachments
                (request_id, file_url, file_type, uploaded_at)
                VALUES (%s, %s, %s, GETDATE())
            """, (
                request_id,
                f"/uploads/{filename}",
                invoice.content_type
            ))

        db.commit()
        return {
            "success": True,
            "message": "Maintenance request marked as completed"
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print("❌ Completion error:", str(e))
        raise HTTPException(status_code=500, detail="Failed to complete maintenance request")
    
@app.get("/api/maintenance-completed/{request_id}")
def get_completed_maintenance_request_by_id(request_id: int, token: dict = Depends(verify_token)):
    db = get_db()
    cursor = db.cursor(as_dict=True)
    try:
        cursor.execute("""
            SELECT 
                mr.id AS maintenance_request_id,
                mr.tenant_id,
                u.first_name,
                u.last_name,
                mr.maintenance_type,
                mr.category,
                mr.description,
                mr.status,
                mr.scheduled_at,
                mr.completed_at,
                mr.admin_comment,
                mr.resolution_summary,
                mr.total_cost,
                mr.warranty_info,
                mr.created_at,
                mr.updated_at
            FROM maintenance_requests mr
            JOIN users u ON u.id = mr.tenant_id
            WHERE mr.id = %s
        """, (request_id,))
        result = cursor.fetchone()
        
        if not result:
            raise HTTPException(status_code=404, detail="Maintenance request not found")
        cursor.execute("""
            SELECT 
                id AS attachment_id,
                file_url,
                file_type,
                uploaded_at
            FROM maintenance_attachments
            WHERE request_id = %s
        """, (request_id,))
        attachments = cursor.fetchall()
        result["attachments"] = attachments
        return result

    except Exception as e:
        print("❌ Error fetching request by ID:", str(e))
        raise HTTPException(status_code=500, detail="Failed to fetch maintenance request")

@app.post("/api/announcements")
async def create_announcement(
    title: str = Form(...),
    description: str = Form(...),
    file: UploadFile = File(None),
    token: dict = Depends(verify_token)
):
    user_id = token.get("id")
    db = get_db()
    cursor = db.cursor(as_dict=True)

    file_url = None
    if file:
        file.file.seek(0)
        file_url = upload_to_blob(file, "announcements")

    cursor.execute("""
        INSERT INTO post_announcements (title, description, file_url, user_id, created_at)
        VALUES (%s, %s, %s, %s, GETDATE())
    """, (title, description, file_url, user_id))
    db.commit()

    cursor.execute("SELECT SCOPE_IDENTITY() AS id")
    ann_id = cursor.fetchone()["id"]

    cursor.execute("SELECT * FROM post_announcements WHERE id = %s", (ann_id,))
    row = cursor.fetchone()
    new_post = clean_row(row)

    await ws_manager.broadcast({
        "event": "new_announcement",
        "data": new_post
    })

    return new_post

@app.get("/api/announcements")
def get_announcements(token: dict = Depends(verify_token)):
    user_id = token.get("id")
    db = get_db()
    cursor = db.cursor(as_dict=True)

    cursor.execute("""
        SELECT * FROM post_announcements
        WHERE user_id = %s
        ORDER BY created_at DESC
    """, (user_id,))
    return cursor.fetchall()

router = APIRouter()

UPLOAD_DIR = "uploads/ids"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/api/tenants")
async def create_tenant(
    lastName: str = Form(...),
    firstName: str = Form(...),
    email: str = Form(...),
    contactNumber: str = Form(...),
    street: str = Form(...),
    barangay: str = Form(...),
    city: str = Form(...),
    province: str = Form(...),
    idType: str = Form(...),
    idNumber: str = Form(...),
    idDocument: UploadFile = File(...),
    occupationStatus: str = Form(...),
    occupationPlace: str = Form(...),
    emergencyContactName: str = Form(...),
    emergencyContactNumber: str = Form(...),
    token: dict = Depends(verify_token),
):
    db = get_db()
    cursor = db.cursor(as_dict=True)

    cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
    existing_user = cursor.fetchone()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already has an account")

    extension = os.path.splitext(idDocument.filename)[-1]
    filename = f"{uuid4()}{extension}"
    file_path = os.path.join("uploads", "id", "tenants", filename)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(idDocument.file, buffer)

    try:
        temp_password = pwd_context.hash("changeme123")
        cursor.execute("""
            INSERT INTO users (first_name, last_name, email, password, role, created_at)
            VALUES (%s, %s, %s, %s, 'tenant', GETDATE())
        """, (firstName, lastName, email, temp_password))
        db.commit()

        cursor.execute("SELECT @@IDENTITY AS id")
        new_user_id = cursor.fetchone()["id"]

        cursor.execute("""
            INSERT INTO tenants (
                user_id, last_name, first_name, email, contact_number,
                street, barangay, city, province,
                id_type, id_number, id_document,
                occupation_status, occupation_place,
                emergency_contact_name, emergency_contact_number,
                created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, GETDATE(), GETDATE())
        """, (
            new_user_id, lastName, firstName, email, contactNumber,
            street, barangay, city, province,
            idType, idNumber, filename,
            occupationStatus, occupationPlace,
            emergencyContactName, emergencyContactNumber
        ))
        db.commit()
        return {"message": "Tenant created successfully", "user_id": new_user_id}

    except Exception as e:
        db.rollback()
        print("TenantInsert Error:", str(e))
        raise HTTPException(status_code=500, detail="Failed to create tenant. Please try again.")
    
@router.put("/api/tenants/{tenant_id}")
async def update_tenant(
    tenant_id: int,
    lastName: str = Form(...),
    firstName: str = Form(...),
    email: str = Form(...),
    contactNumber: str = Form(...),
    street: str = Form(...),
    barangay: str = Form(...),
    city: str = Form(...),
    province: str = Form(...),
    idType: str = Form(...),
    idNumber: str = Form(...),
    occupationStatus: str = Form(...),
    occupationPlace: str = Form(...),
    emergencyContactName: str = Form(...),
    emergencyContactNumber: str = Form(...),
    idDocument: UploadFile = File(None),
    token: dict = Depends(verify_token),
):
    db = get_db()
    cursor = db.cursor(as_dict=True)

    cursor.execute("SELECT * FROM tenants WHERE id = %s", (tenant_id,))
    tenant = cursor.fetchone()
    if not tenant:
        raise HTTPException(404, "Tenant not found")

    new_doc = tenant["id_document"]

    if idDocument:
        ext = os.path.splitext(idDocument.filename)[-1]
        filename = f"{uuid4()}{ext}"
        upload_path = f"uploads/id/tenants/{filename}"

        with open(upload_path, "wb") as f:
            shutil.copyfileobj(idDocument.file, f)

        old_path = f"uploads/id/tenants/{tenant['id_document']}"
        if os.path.exists(old_path):
            os.remove(old_path)

        new_doc = filename

    try:
        cursor.execute("""
            UPDATE tenants SET
                last_name=%s, first_name=%s, email=%s, contact_number=%s,
                street=%s, barangay=%s, city=%s, province=%s,
                id_type=%s, id_number=%s, id_document=%s,
                occupation_status=%s, occupation_place=%s,
                emergency_contact_name=%s, emergency_contact_number=%s,
                updated_at=GETDATE()
            WHERE id=%s
        """, (
            lastName, firstName, email, contactNumber,
            street, barangay, city, province,
            idType, idNumber, new_doc,
            occupationStatus, occupationPlace,
            emergencyContactName, emergencyContactNumber,
            tenant_id
        ))
        db.commit()
        return {"message": "Tenant updated successfully"}

    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Update failed: {e}")
    
@router.delete("/api/tenants/{tenant_id}")
async def delete_tenant(tenant_id: int, token: dict = Depends(verify_token)):
    db = get_db()
    cursor = db.cursor(as_dict=True)

    cursor.execute("SELECT * FROM tenants WHERE id=%s", (tenant_id,))
    tenant = cursor.fetchone()
    if not tenant:
        raise HTTPException(404, "Tenant not found")

    try:
        file_path = f"uploads/id/tenants/{tenant['id_document']}"
        if os.path.exists(file_path):
            os.remove(file_path)

        cursor.execute("DELETE FROM tenants WHERE id=%s", (tenant_id,))
        cursor.execute("DELETE FROM users WHERE id=%s", (tenant["user_id"]))
        db.commit()

        return {"message": "Tenant deleted successfully"}

    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Delete failed: {e}")

@router.post("/api/property-owners")
async def create_property_owner(
    lastName: str = Form(...),
    firstName: str = Form(...),
    email: str = Form(...),
    contactNumber: str = Form(...),
    street: str = Form(...),
    barangay: str = Form(...),
    city: str = Form(...),
    province: str = Form(...),
    idType: str = Form(...),
    idNumber: str = Form(...),
    idDocument: UploadFile = File(...),
    bankAssociated: str = Form(...),
    bankAccountNumber: str = Form(...),
    token: dict = Depends(verify_token)
):
    db = get_db()
    cursor = db.cursor(as_dict=True)
    
    cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
    existing_user = cursor.fetchone()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already has an account")

    temp_password = pwd_context.hash("changeme123")
    cursor.execute("""
        INSERT INTO users (first_name, last_name, email, password, role, created_at)
        VALUES (%s, %s, %s, %s, 'owner', GETDATE())
    """, (firstName, lastName, email, temp_password))
    db.commit()

    cursor.execute("SELECT @@IDENTITY AS id")
    user_id = cursor.fetchone()["id"]

    upload_dir = "uploads/id/property-owners"
    os.makedirs(upload_dir, exist_ok=True)
    file_extension = idDocument.filename.split(".")[-1]
    new_filename = f"owner_{user_id}_{uuid.uuid4()}.{file_extension}"
    file_path = os.path.join(upload_dir, new_filename)

    with open(file_path, "wb") as f:
        f.write(await idDocument.read())
    saved_file_path = f"/uploads/id/property-owners/{new_filename}"

    try:
        cursor.execute("""
            INSERT INTO property_owners (
                user_id, last_name, first_name, email,
                contact_number, street, barangay, city, province,
                id_type, id_number, id_document,
                bank_associated, bank_account_number,
                created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, GETDATE(), GETDATE())
        """, (
            user_id, lastName, firstName, email,
            contactNumber, street, barangay, city, province,
            idType, idNumber, saved_file_path,
            bankAssociated, bankAccountNumber
        ))
        db.commit()
        return {
            "success": True,
            "message": "Property owner created successfully",
            "user_id": user_id,
            "file": saved_file_path
        }

    except Exception as e:
        db.rollback()
        print(" Property Owner Insert Error:", str(e))
        raise HTTPException(status_code=500, detail="Failed to create property owner. Please try again.")
    
@router.put("/api/property-owners/{owner_id}")
async def update_property_owner(
    owner_id: int,
    lastName: str = Form(...),
    firstName: str = Form(...),
    email: str = Form(...),
    contactNumber: str = Form(...),
    street: str = Form(...),
    barangay: str = Form(...),
    city: str = Form(...),
    province: str = Form(...),
    idType: str = Form(...),
    idNumber: str = Form(...),
    bankAssociated: str = Form(...),
    bankAccountNumber: str = Form(...),
    idDocument: UploadFile = File(None),
    token: dict = Depends(verify_token)
):
    db = get_db()
    cursor = db.cursor(as_dict=True)

    cursor.execute("SELECT * FROM property_owners WHERE owner_id=%s", (owner_id,))
    owner = cursor.fetchone()
    if not owner:
        raise HTTPException(404, "Owner not found")

    new_doc = owner["id_document"]

    if idDocument:
        ext = os.path.splitext(idDocument.filename)[-1]
        filename = f"owner_{owner_id}_{uuid4()}{ext}"
        upload_path = f"uploads/id/property-owners/{filename}"

        with open(upload_path, "wb") as f:
            f.write(await idDocument.read())

        old_path = owner["id_document"].lstrip("/")
        if os.path.exists(old_path):
            os.remove(old_path)

        new_doc = f"/uploads/id/property-owners/{filename}"

    try:
        cursor.execute("""
            UPDATE property_owners SET
                last_name=%s, first_name=%s, email=%s, contact_number=%s,
                street=%s, barangay=%s, city=%s, province=%s,
                id_type=%s, id_number=%s, id_document=%s,
                bank_associated=%s, bank_account_number=%s,
                updated_at=GETDATE()
            WHERE owner_id=%s
        """, (
            lastName, firstName, email, contactNumber,
            street, barangay, city, province,
            idType, idNumber, new_doc,
            bankAssociated, bankAccountNumber,
            owner_id
        ))
        db.commit()
        return {"message": "Property owner updated successfully"}

    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Update failed: {e}")
    
@router.delete("/api/property-owners/{owner_id}")
async def delete_property_owner(owner_id: int, token: dict = Depends(verify_token)):
    db = get_db()
    cursor = db.cursor(as_dict=True)

    cursor.execute("SELECT * FROM property_owners WHERE owner_id=%s", (owner_id,))
    owner = cursor.fetchone()
    if not owner:
        raise HTTPException(404, "Owner not found")

    try:
        old_doc = owner["id_document"].lstrip("/")
        if os.path.exists(old_doc):
            os.remove(old_doc)

        cursor.execute("DELETE FROM property_owners WHERE owner_id=%s", (owner_id,))
        cursor.execute("DELETE FROM users WHERE id=%s", (owner["user_id"]))
        db.commit()

        return {"message": "Property owner deleted successfully"}

    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Delete failed: {e}")
    
@router.post("/api/properties")
async def create_property(
    propertyName: str = Form(...),
    registeredOwner: str = Form(...),
    areaMeasurement: str = Form(...),
    description: str = Form(...),
    street: str = Form(...),
    barangay: str = Form(...),
    city: str = Form(...),
    province: str = Form(...),
    propertyNotes: str = Form(""),
    units: int = Form(...),
    selectedFeatures: str = Form(""),
    propertyImages: List[UploadFile] = File([]),
    token: dict = Depends(verify_token)
):
    upload_dir = "uploads/properties"
    os.makedirs(upload_dir, exist_ok=True)
    saved_images = []
    for img in propertyImages:
        ext = img.filename.split(".")[-1]
        filename = f"prop_{uuid.uuid4()}.{ext}"
        filepath = os.path.join(upload_dir, filename)
        with open(filepath, "wb") as f:
            f.write(await img.read())
        saved_images.append(f"/uploads/properties/{filename}")
        
    db = get_db()
    cursor = db.cursor(as_dict=True)
    cursor.execute("""
        SELECT id FROM properties
        WHERE property_name = %s
        AND registered_owner = %s
        AND street = %s
        AND barangay = %s
        AND city = %s
        AND province = %s
    """, (
        propertyName,
        registeredOwner,
        street,
        barangay,
        city,
        province
    ))
    existing = cursor.fetchone()
    if existing:
        raise HTTPException(
            status_code=400,
            detail="Property already exists for this owner and address."
        )
    
    try:
        cursor.execute("""
            INSERT INTO properties (
                property_name, registered_owner, area_measurement,
                description, street, barangay, city,
                province, property_notes, units, selected_features,
                created_at
            ) VALUES (
                %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                GETDATE()
            )
        """, (
            propertyName, registeredOwner, areaMeasurement,
            description, street, barangay, city,
            province, propertyNotes, units, selectedFeatures
        ))
        db.commit()
        cursor.execute("SELECT @@IDENTITY AS id")
        property_id = cursor.fetchone()["id"]

    except Exception as e:
        db.rollback()
        print("Property Insert Error →", e)
        raise HTTPException(status_code=500, detail="Failed to save property details")

    try:
        for i in range(1, units + 1):
            cursor.execute("""
                INSERT INTO property_units (property_id, unit_number, status, created_at, updated_at)
                VALUES (%s, %s, 'vacant', GETDATE(), GETDATE())
            """, (property_id, f"Unit {i}"))

        db.commit()
    except Exception as e:
        db.rollback()
        print("Unit Insert Error →", e)

    return {
        "success": True,
        "message": "Property created successfully",
        "property_id": property_id,
        "uploaded_images": saved_images,
    }
    
@router.put("/api/properties/{property_id}")
async def update_property(
    property_id: int,
    propertyName: str = Form(...),
    registeredOwner: str = Form(...),
    areaMeasurement: str = Form(...),
    description: str = Form(...),
    street: str = Form(...),
    barangay: str = Form(...),
    city: str = Form(...),
    province: str = Form(...),
    propertyNotes: str = Form(""),
    units: int = Form(...),
    selectedFeatures: str = Form(""),
    token: dict = Depends(verify_token),
):
    db = get_db()
    cursor = db.cursor(as_dict=True)

    cursor.execute("SELECT * FROM properties WHERE id=%s", (property_id,))
    prop = cursor.fetchone()
    if not prop:
        raise HTTPException(404, "Property not found")

    cursor.execute("""
        SELECT id FROM properties
        WHERE property_name=%s AND registered_owner=%s AND
            street=%s AND barangay=%s AND city=%s AND province=%s
            AND id != %s
    """, (
        propertyName, registeredOwner,
        street, barangay, city, province,
        property_id
    ))
    dup = cursor.fetchone()
    if dup:
        raise HTTPException(400, "Another property already exists with this address")

    try:
        cursor.execute("""
            UPDATE properties SET
                property_name=%s, registered_owner=%s, area_measurement=%s,
                description=%s, street=%s, barangay=%s, city=%s, province=%s,
                property_notes=%s, units=%s, selected_features=%s,
                updated_at=GETDATE()
            WHERE id=%s
        """, (
            propertyName, registeredOwner, areaMeasurement,
            description, street, barangay, city, province,
            propertyNotes, units, selectedFeatures,
            property_id
        ))
        db.commit()

        return {"message": "Property updated successfully"}

    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Update failed: {e}")
    
@router.delete("/api/properties/{property_id}")
async def delete_property(property_id: int, token: dict = Depends(verify_token)):
    db = get_db()
    cursor = db.cursor(as_dict=True)

    cursor.execute("SELECT * FROM properties WHERE id=%s", (property_id,))
    prop = cursor.fetchone()
    if not prop:
        raise HTTPException(404, "Property not found")

    try:
        cursor.execute("DELETE FROM property_units WHERE property_id=%s", (property_id,))
        cursor.execute("DELETE FROM properties WHERE id=%s", (property_id,))
        db.commit()

        return {"message": "Property deleted successfully"}

    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Delete failed: {e}")
    
@router.post("/api/property-units")
async def create_property_unit(
    propertyId: str = Form(...),
    unitType: str = Form(...),
    unitNumber: str = Form(...),
    commissionPercentage: float = Form(...),
    rentPrice: float = Form(...),
    depositPrice: float = Form(...),
    floor: str = Form(...),
    size: float = Form(...),
    description: str = Form(...),
    unitImages: List[UploadFile] = File(...),
    token: dict = Depends(verify_token)
):
    db = get_db()
    cursor = db.cursor(as_dict=True)
    cursor.execute("""
        SELECT id FROM property_units
        WHERE property_id = %s AND unit_number = %s
    """, (propertyId, unitNumber))
    existing_unit = cursor.fetchone()
    if existing_unit:
        raise HTTPException(
            status_code=400,
            detail=f"Unit '{unitNumber}' already exists for this property."
        )
    
    upload_dir = "uploads/unit-images"
    os.makedirs(upload_dir, exist_ok=True)
    saved_images = []
    
    try:
        cursor.execute("""
            INSERT INTO property_units
            (property_id, unit_type, unit_number, commission_percentage,
            rent_price, deposit_price, floor, size, description, status, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'vacant', GETDATE())
        """, (
            propertyId, unitType, unitNumber, commissionPercentage,
            rentPrice, depositPrice, floor, size, description
        ))
        db.commit()

        cursor.execute("SELECT SCOPE_IDENTITY() AS id")
        new_unit_id = cursor.fetchone()["id"]
        for file in unitImages:
            ext = os.path.splitext(file.filename)[-1]
            new_name = f"{uuid4()}{ext}"
            file_path = os.path.join(upload_dir, new_name)
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            cursor.execute("""
                INSERT INTO unit_images (unit_id, image_path)
                VALUES (%s, %s)
            """, (new_unit_id, new_name))
            saved_images.append(new_name)
        db.commit()
        return {
            "message": "Property unit created successfully",
            "unit_id": new_unit_id,
            "images": saved_images
        }

    except Exception as e:
        db.rollback()
        print("CreateUnit Error:", str(e))
        raise HTTPException(status_code=400, detail=str(e))
        # raise HTTPException(status_code=500, detail="Failed to create property unit.")
        
@router.put("/api/property-units/{unit_id}")
async def update_property_unit(
    unit_id: int,
    unitType: str = Form(...),
    unitNumber: str = Form(...),
    commissionPercentage: float = Form(...),
    rentPrice: float = Form(...),
    depositPrice: float = Form(...),
    floor: str = Form(...),
    size: float = Form(...),
    description: str = Form(...),
    unitImages: List[UploadFile] = File(None),
    token: dict = Depends(verify_token)
):
    db = get_db()
    cursor = db.cursor(as_dict=True)

    cursor.execute("SELECT * FROM property_units WHERE id=%s", (unit_id,))
    unit = cursor.fetchone()
    if not unit:
        raise HTTPException(404, "Unit not found")

    cursor.execute("""
        SELECT id FROM property_units
        WHERE property_id=%s AND unit_number=%s AND id != %s
    """, (unit["property_id"], unitNumber, unit_id))
    dup = cursor.fetchone()
    if dup:
        raise HTTPException(400, "Unit number already exists")

    try:
        cursor.execute("""
            UPDATE property_units SET
                unit_type=%s, unit_number=%s, commission_percentage=%s,
                rent_price=%s, deposit_price=%s, floor=%s,
                size=%s, description=%s, updated_at=GETDATE()
            WHERE id=%s
        """, (
            unitType, unitNumber, commissionPercentage,
            rentPrice, depositPrice, floor,
            size, description, unit_id
        ))
        db.commit()

        if unitImages:
            cursor.execute("SELECT * FROM unit_images WHERE unit_id=%s", (unit_id,))
            old_imgs = cursor.fetchall()
            for img in old_imgs:
                old_path = f"uploads/unit-images/{img['image_path']}"
                if os.path.exists(old_path):
                    os.remove(old_path)

            cursor.execute("DELETE FROM unit_images WHERE unit_id=%s", (unit_id,))

            upload_dir = "uploads/unit-images"
            os.makedirs(upload_dir, exist_ok=True)

            for file in unitImages:
                ext = os.path.splitext(file.filename)[-1]
                new_name = f"{uuid4()}{ext}"
                file_path = os.path.join(upload_dir, new_name)
                with open(file_path, "wb") as f:
                    shutil.copyfileobj(file.file, f)

                cursor.execute("""
                    INSERT INTO unit_images (unit_id, image_path)
                    VALUES (%s, %s)
                """, (unit_id, new_name))

            db.commit()

        return {"message": "Unit updated successfully"}

    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Update failed: {e}")
    
@router.delete("/api/property-units/{unit_id}")
async def delete_property_unit(unit_id: int, token: dict = Depends(verify_token)):
    db = get_db()
    cursor = db.cursor(as_dict=True)

    cursor.execute("SELECT * FROM property_units WHERE id=%s", (unit_id,))
    unit = cursor.fetchone()
    if not unit:
        raise HTTPException(404, "Unit not found")

    try:
        cursor.execute("SELECT * FROM unit_images WHERE unit_id=%s", (unit_id,))
        imgs = cursor.fetchall()

        for img in imgs:
            path = f"uploads/unit-images/{img['image_path']}"
            if os.path.exists(path):
                os.remove(path)

        cursor.execute("DELETE FROM unit_images WHERE unit_id=%s", (unit_id,))
        cursor.execute("DELETE FROM property_units WHERE id=%s", (unit_id,))
        db.commit()

        return {"message": "Unit deleted successfully"}

    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Delete failed: {e}")

UPLOAD_DIR = "uploads/leases"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/api/leases")
async def create_lease(
    property: int = Form(...),
    leaseUnits: bool = Form(False),
    unit: Optional[int] = Form(None),
    rentPrice: float = Form(...),
    depositPrice: float = Form(...),
    tenant: int = Form(...),
    tenantEmail: str = Form(...),
    startDate: str = Form(...),
    endDate: str = Form(...),
    tenancyTerms: str = Form(...),
    bills_gas: bool = Form(False),
    bills_gasAmount: Optional[float] = Form(None),
    bills_electricity: bool = Form(False),
    bills_electricityAmount: Optional[float] = Form(None),
    bills_internet: bool = Form(False),
    bills_internetAmount: Optional[float] = Form(None),
    bills_tax: bool = Form(False),
    bills_taxAmount: Optional[float] = Form(None),
    leaseDocuments: List[UploadFile] = File([]),
    token: dict = Depends(verify_token),
):
    db = get_db()
    cursor = db.cursor()

    # Save uploaded docs
    saved_files = []
    for doc in leaseDocuments:
        filename = f"{uuid.uuid4()}-{doc.filename}"
        filepath = os.path.join(UPLOAD_DIR, filename)
        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(doc.file, buffer)
        saved_files.append(f"/{UPLOAD_DIR}/{filename}")

    # Insert into leases table
    query = """
    INSERT INTO leases (
        property_id, property_unit_id, tenant_id,
        rent_price, deposit_price, start_date, end_date,
        tenancy_terms, lease_documents,
        bill_gas, bill_gas_amount,
        bill_electricity, bill_electricity_amount,
        bill_internet, bill_internet_amount,
        bill_tax, bill_tax_amount
    )
    VALUES (
        %(property_id)s, %(unit)s, %(tenant_id)s,
        %(rent_price)s, %(deposit_price)s, %(start_date)s, %(end_date)s,
        %(tenancy_terms)s, %(lease_documents)s,
        %(bill_gas)s, %(bill_gas_amount)s,
        %(bill_electricity)s, %(bill_electricity_amount)s,
        %(bill_internet)s, %(bill_internet_amount)s,
        %(bill_tax)s, %(bill_tax_amount)s
    )
    """
    params = {
        "property_id": property,
        "unit": unit,
        "tenant_id": tenant,
        "rent_price": rentPrice,
        "deposit_price": depositPrice,
        "start_date": startDate,
        "end_date": endDate,
        "tenancy_terms": tenancyTerms,
        "lease_documents": ",".join(saved_files),
        "bill_gas": bills_gas,
        "bill_gas_amount": bills_gasAmount,
        "bill_electricity": bills_electricity,
        "bill_electricity_amount": bills_electricityAmount,
        "bill_internet": bills_internet,
        "bill_internet_amount": bills_internetAmount,
        "bill_tax": bills_tax,
        "bill_tax_amount": bills_taxAmount,
    }

    try:
        cursor.execute(query, params)
        db.commit()
        return {"message": "Lease created successfully"}
    except Exception as e:
        db.rollback()
        return {"error": str(e)}
    
@app.get("/api/tenants")
def get_all_tenants(token: dict = Depends(verify_token)):
    try:
        db = get_db()
        cursor = db.cursor(as_dict=True)
        cursor.execute("SELECT * FROM tenants")
        return cursor.fetchall()
    except Exception as e:
        print("❌ /api/tenants error:", str(e))
        raise HTTPException(status_code=500, detail="Database error: " + str(e))
    
@app.get("/api/tenants/{tenant_id}")
def get_tenant_by_id(tenant_id: int, token: dict = Depends(verify_token)):
    db = get_db()
    cursor = db.cursor(as_dict=True)
    try:
        cursor.execute("""
            SELECT
                t.tenant_id,
                t.last_name, 
                t.first_name, 
                t.email, 
                t.contact_number,
                t.street, 
                t.barangay, 
                t.city, 
                t.province,
                t.id_type, 
                t.id_number,
                t.id_document,
                t.occupation_status,
                t.occupation_place,
                t.emergency_contact_name,
                t.emergency_contact_number,
                t.created_at,
                t.updated_at
            FROM tenants t
            WHERE t.tenant_id = %s
        """, (tenant_id,))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Database error: " + str(e))
    tenant = cursor.fetchone()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant

@app.get("/api/property-owners")
def get_all_property_owners(token: dict = Depends(verify_token)):
    db = get_db()
    cursor = db.cursor(as_dict=True)
    cursor.execute("SELECT * FROM property_owners")
    return cursor.fetchall()

@app.get("/api/properties")
def get_all_properties(token: dict = Depends(verify_token)):
    db = get_db()
    cursor = db.cursor(as_dict=True)
    cursor.execute("""
    SELECT 
        p.*,
        CONCAT(po.first_name, ' ', po.last_name) AS owner_full_name
    FROM properties p
    LEFT JOIN property_owners po 
        ON p.registered_owner = po.owner_id;""")
    return cursor.fetchall()

@app.get("/api/property-units")
def get_property_units(token: dict = Depends(verify_token)):
    db = get_db()
    cursor = db.cursor(as_dict=True)
    cursor.execute("""
        SELECT pu.*, p.property_name
        FROM property_units pu
        JOIN properties p ON pu.property_id = p.id
    """)
    return cursor.fetchall()

@app.get("/api/property-units/vacant")
def get_vacant_property_units(token: dict = Depends(verify_token)):
    try:
        db = get_db()
        cursor = db.cursor(as_dict=True)
        cursor.execute("""
            SELECT pu.*, p.property_name
            FROM property_units pu
            JOIN properties p ON pu.property_id = p.id
            WHERE pu.status = 'vacant'
        """)
        return cursor.fetchall()

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/leases")
def get_all_leases(token: dict = Depends(verify_token)):
    db = get_db()
    cursor = db.cursor(as_dict=True)
    cursor.execute("""
        SELECT lt.*, p.property_name, pu.unit_number, pu.unit_type, t.email
        FROM leases lt
        LEFT JOIN properties p ON lt.property_id = p.property_id
        LEFT JOIN property_units pu ON lt.property_unit_id = pu.property_unit_id
        LEFT JOIN tenants t ON lt.tenant_id = t.tenant_id
        ORDER BY lt.created_at DESC
    """)
    return cursor.fetchall()

@app.get("/api/maintenance-requests")
def get_maintenance_requests(token: dict = Depends(verify_token)):
    db = get_db()
    cursor = db.cursor(as_dict=True)
    try:
        cursor.execute("""
            SELECT 
                mr.id AS maintenance_request_id,
                mr.tenant_id,
                u.first_name,
                u.last_name,
                mr.maintenance_type,
                mr.category,
                mr.description,
                mr.status,
                mr.created_at,
                mr.updated_at
            FROM maintenance_requests mr
            JOIN users u ON u.id = mr.tenant_id
            ORDER BY mr.created_at DESC
        """)
        return {"requests": cursor.fetchall()}
    except Exception as e:
        print("❌ Error fetching maintenance requests:", str(e))
        raise HTTPException(status_code=500, detail="Failed to fetch maintenance requests")
    
@app.get("/api/maintenance-requests/{request_id}")
def get_maintenance_request_by_id(request_id: int, token: dict = Depends(verify_token)):
    db = get_db()
    cursor = db.cursor(as_dict=True)
    try:
        cursor.execute("""
            SELECT 
                mr.id AS maintenance_request_id,
                mr.tenant_id,
                u.first_name,
                u.last_name,
                mr.maintenance_type,
                mr.category,
                mr.description,
                mr.status,
                mr.scheduled_at,
                mr.admin_comment,
                mr.created_at,
                mr.updated_at
            FROM maintenance_requests mr
            JOIN users u ON u.id = mr.tenant_id
            WHERE mr.id = %s
        """, (request_id,))
        result = cursor.fetchone()

        if not result:
            raise HTTPException(status_code=404, detail="Maintenance request not found")

        cursor.execute("""
            SELECT 
                id AS attachment_id,
                file_url,
                file_type,
                uploaded_at
            FROM maintenance_attachments
            WHERE request_id = %s
        """, (request_id,))
        attachments = cursor.fetchall()

        result["attachments"] = attachments

        return result

    except Exception as e:
        print("❌ Error fetching request by ID:", str(e))
        raise HTTPException(status_code=500, detail="Failed to fetch maintenance request")
    
@app.get("/api/maintenance-ongoing/{request_id}")
def get_ongoing_maintenance_request_by_id(request_id: int, token: dict = Depends(verify_token)):
    db = get_db()
    cursor = db.cursor(as_dict=True)
    try:
        cursor.execute("""
            SELECT 
                mr.id AS maintenance_request_id,
                mr.tenant_id,
                u.first_name,
                u.last_name,
                mr.maintenance_type,
                mr.category,
                mr.description,
                mr.status,
                mr.scheduled_at,
                mr.admin_comment,
                mr.created_at,
                mr.updated_at
            FROM maintenance_requests mr
            JOIN users u ON u.id = mr.tenant_id
            WHERE mr.id = %s
        """, (request_id,))
        result = cursor.fetchone()
        
        if not result:
            raise HTTPException(status_code=404, detail="Maintenance request not found")
        cursor.execute("""
            SELECT 
                id AS attachment_id,
                file_url,
                file_type,
                uploaded_at
            FROM maintenance_attachments
            WHERE request_id = %s
        """, (request_id,))
        attachments = cursor.fetchall()
        result["attachments"] = attachments
        return result

    except Exception as e:
        print("❌ Error fetching request by ID:", str(e))
        raise HTTPException(status_code=500, detail="Failed to fetch maintenance request")

# Specific Mobile Routes
@app.post("/api/maintenance-requests")
async def submit_maintenance_request(
    maintenance_type: str = Form(...),
    category: str = Form(...),
    description: str = Form(...),
    files: Optional[List[UploadFile]] = File(None),
    scheduled_at: Optional[str] = Form(None),
    token: dict = Depends(verify_token),
):
    tenant_id = token.get("id")
    db = get_db()
    cursor = db.cursor()

    try:
        scheduled_dt = None
        if scheduled_at:
            scheduled_dt = datetime.fromisoformat(scheduled_at.replace("Z", ""))
        cursor.execute("""
            INSERT INTO maintenance_requests (
                tenant_id, maintenance_type, category, description, status, scheduled_at, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, GETDATE(), GETDATE())
        """, (tenant_id, maintenance_type, category, description, "pending", scheduled_dt))
        db.commit()

        cursor.execute("SELECT SCOPE_IDENTITY()")
        request_id = cursor.fetchone()[0]

        saved_files = []
        if files:
            for upload in files:
                filename = f"{uuid.uuid4()}_{upload.filename.replace(' ', '_')}"
                file_path = os.path.join(UPLOAD_DIR, filename)
                with open(file_path, "wb") as buffer:
                    shutil.copyfileobj(upload.file, buffer)

                cursor.execute("""
                    INSERT INTO maintenance_attachments (request_id, file_url, file_type, uploaded_at)
                    VALUES (%s, %s, %s, GETDATE())
                """, (request_id, f"/uploads/{filename}", upload.content_type))
                saved_files.append(filename)

        db.commit()
        return {
            "success": True,
            "message": "Maintenance request submitted",
            "request_id": request_id,
            "attachments": saved_files
        }

    except Exception as e:
        print("❌ Maintenance request error:", str(e))
        raise HTTPException(status_code=500, detail="Failed to submit maintenance request")
    
app.include_router(router)

# 404 Fallback Middleware
@app.middleware("http")
async def not_found_middleware(request: Request, call_next):
    try:
        response = await call_next(request)
        if response.status_code == 404:
            return JSONResponse(status_code=404, content={"error": "Route not found"})
        return response
    except Exception:
        return JSONResponse(status_code=500, content={"error": "Internal server error"})

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
