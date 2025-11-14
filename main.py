import shutil
import time
import os
from typing import List, Optional
import uuid
from fastapi import FastAPI, APIRouter, Form, Request, Depends, HTTPException, status, File, UploadFile
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
from datetime import datetime

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

    token = jwt.encode({"id": user['id']}, SECRET_KEY, algorithm=ALGORITHM)
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

    # ✅ Step 1: Check if email is already in users
    cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
    existing_user = cursor.fetchone()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already exists as a user")

    # ✅ Step 2: Save uploaded file
    extension = os.path.splitext(idDocument.filename)[-1]
    filename = f"{uuid4()}{extension}"
    file_path = os.path.join("uploads", "ids", filename)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(idDocument.file, buffer)

    try:
        # ✅ Step 3: Insert new user (role = tenant)
        temp_password = pwd_context.hash("changeme123")  # you can replace this with random gen
        cursor.execute("""
            INSERT INTO users (first_name, last_name, email, password, role, created_at)
            VALUES (%s, %s, %s, %s, 'tenant', GETDATE())
        """, (firstName, lastName, email, temp_password))
        db.commit()

        cursor.execute("SELECT SCOPE_IDENTITY() AS id")
        new_user_id = cursor.fetchone()["id"]

        # ✅ Step 4: Insert tenant profile linked to new user
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
        print("❌ Insert Error:", str(e))
        raise HTTPException(status_code=500, detail="Failed to create tenant")

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
    cursor.execute("SELECT * FROM properties")
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

        query = (
            "SELECT pu.id AS property_unit_id, pu.property_id, pu.unit_number,"
            "pu.unit_type, pu.rent_price, pu.status, p.property_name"
            "FROM property_units pu "
            "JOIN properties p ON pu.property_id = p.id"
            "WHERE pu.status = 'vacant'"
        )

        cursor.execute(query)
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
                mr.created_at,
                mr.updated_at
            FROM maintenance_requests mr
            JOIN users u ON u.id = mr.tenant_id
            WHERE mr.id = %s
        """, (request_id,))
        result = cursor.fetchone()

        if not result:
            raise HTTPException(status_code=404, detail="Maintenance request not found")

        # Fetch the file attachments for this request
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
    token: dict = Depends(verify_token),
):
    tenant_id = token.get("id")
    db = get_db()
    cursor = db.cursor()

    try:
        # 1. Insert into maintenance_requests
        cursor.execute("""
            INSERT INTO maintenance_requests (
                tenant_id, maintenance_type, category, description, status, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, GETDATE(), GETDATE())
        """, (tenant_id, maintenance_type, category, description, "pending"))
        db.commit()

        # 2. Get the inserted request ID
        cursor.execute("SELECT SCOPE_IDENTITY()")
        request_id = cursor.fetchone()[0]

        # 3. Handle attachments (if any)
        saved_files = []
        if files:
            for upload in files:
                filename = f"{uuid.uuid4()}_{upload.filename.replace(' ', '_')}"
                file_path = os.path.join(UPLOAD_DIR, filename)
                with open(file_path, "wb") as buffer:
                    shutil.copyfileobj(upload.file, buffer)

                # Insert into maintenance_attachments
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
