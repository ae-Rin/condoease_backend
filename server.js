const express = require("express");
const cors = require("cors");
const sql = require("mssql");
const path = require("path");
const multer = require("multer");
const fs = require("fs");
const bcrypt = require("bcrypt");
const jwt = require("jsonwebtoken");
const http = require("http");
require("dotenv").config();
const JWT_SECRET = process.env.JWT_SECRET;

if (!JWT_SECRET) {
  console.error("❌ JWT_SECRET is not defined in environment variables.");
  process.exit(1);
}

// Initialize app and server
const app = express();
const server = http.createServer(app);
const io = new Server(server, {
  cors: {
    origin: process.env.CORS_ORIGINS?.split(","),
    methods: ["GET", "POST", "PUT", "DELETE"],
    credentials: true,
  },
});

// Middleware
app.use(
  cors({
    origin: process.env.CORS_ORIGINS?.split(","),
    methods: ["GET", "POST", "PUT", "DELETE"],
    credentials: true,
  })
);
app.use(express.json());

// Ensure uploads directory exists
const uploadDir = path.resolve(__dirname, "uploads");
if (!fs.existsSync(uploadDir)) fs.mkdirSync(uploadDir);
app.use("/uploads", express.static(uploadDir));

// Multer storage setup
const storage = multer.diskStorage({
  destination: (_, __, cb) => cb(null, uploadDir),
  filename: (_, file, cb) => {
    const sanitized = file.originalname
      .replace(/\s+/g, "_")
      .replace(/[^\w.-]/g, "");
    cb(null, Date.now() + "-" + sanitized);
  },
});
const upload = multer({ storage });

// Azure SQL Connection
const dbConfig = {
  user: process.env.DB_USER,
  password: process.env.DB_PASS,
  server: process.env.DB_SERVER,
  port: parseInt(process.env.DB_PORT),
  database: process.env.DB_NAME,
  authentication: { type: "default" },
  options: { encrypt: true, trustServerCertificate: false },
};

let db;
async function initDb() {
  try {
    db = await sql.connect(dbConfig);
    console.log("Azure SQL DB connected!");
  } catch (err) {
    console.error("Azure DB Connection Error:", err);
    process.exit(1);
  }
}
initDb();

// JWT Auth Middleware
function authenticateToken(req, res, next) {
  const token = req.headers["authorization"]?.split(" ")[1];
  if (!token) return res.sendStatus(401);
  jwt.verify(token, process.env.JWT_SECRET, (err, user) => {
    if (err) return res.sendStatus(403);
    req.user = user;
    next();
  });
}

// ======= ROUTES START ======= //

// Register
app.post("/api/registerstep2", async (req, res) => {
  const { firstName, lastName, email, password } = req.body;
  if (!firstName || !lastName || !email || !password)
    return res.status(400).json({ error: "All fields are required" });

  try {
    const hashedPassword = await bcrypt.hash(password, 10);
    await db
      .request()
      .input("firstName", sql.VarChar, firstName)
      .input("lastName", sql.VarChar, lastName)
      .input("email", sql.VarChar, email)
      .input("password", sql.VarChar, hashedPassword).query(`
        INSERT INTO users (first_name, last_name, email, password)
        VALUES (@firstName, @lastName, @email, @password)
      `);
    res.json({ success: true });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Login
app.post("/api/login", async (req, res) => {
  const { email, password } = req.body;

  try {
    const pool = await sql.connect(dbConfig);
    const result = await pool
      .request()
      .input("email", sql.VarChar, email)
      .query("SELECT * FROM users WHERE email = @email");

    const user = result.recordset[0];
    if (!user)
      return res.status(401).json({ error: "Invalid email or password" });

    const match = await bcrypt.compare(password, user.password);
    if (!match) return res.status(401).json({ error: "Incorrect password" });

    const token = jwt.sign({ id: user.id }, process.env.JWT_SECRET, {
      expiresIn: "2h",
    });

    res.json({ token, user });
  } catch (err) {
    res.status(500).json({ error: "Server error" });
  }
});

// Update Avatar
app.put(
  "/api/users/avatar",
  authenticateToken,
  upload.single("avatar"),
  async (req, res) => {
    const userId = req.user.id;
    if (!req.file) return res.status(400).json({ error: "No file uploaded" });

    const avatarPath = `/uploads/${req.file.filename}`;
    try {
      await db
        .request()
        .input("avatar", sql.VarChar, avatarPath)
        .input("userId", sql.Int, userId)
        .query("UPDATE users SET avatar = @avatar WHERE id = @userId");
      res.json({ avatar: avatarPath });
    } catch (err) {
      res.status(500).json({ error: "Failed to update avatar" });
    }
  }
);

// Update User Profile
app.put("/api/users/:id", authenticateToken, async (req, res) => {
  const { id } = req.params;
  const { firstName, lastName, email, password, currentPassword } = req.body;

  try {
    const result = await db
      .request()
      .input("id", sql.Int, id)
      .query("SELECT password FROM users WHERE id = @id");

    const storedHashedPassword = result.recordset[0]?.password;
    if (!storedHashedPassword)
      return res.status(404).json({ error: "User not found" });

    const fields = [];
    const updates = {};

    if (firstName && lastName) {
      fields.push("first_name = @firstName", "last_name = @lastName");
      updates.firstName = firstName;
      updates.lastName = lastName;
    }

    if (email && password) {
      const match = await bcrypt.compare(password, storedHashedPassword);
      if (!match) return res.status(401).json({ error: "Incorrect password" });
      fields.push("email = @newEmail");
      updates.newEmail = email;
    }

    if (currentPassword && password && currentPassword !== password) {
      const match = await bcrypt.compare(currentPassword, storedHashedPassword);
      if (!match)
        return res.status(401).json({ error: "Incorrect current password" });
      const hashed = await bcrypt.hash(password, 10);
      fields.push("password = @newPassword");
      updates.newPassword = hashed;
    }

    if (!fields.length)
      return res.status(400).json({ error: "No fields to update" });

    let updateReq = db.request().input("id", sql.Int, id);
    if (updates.firstName)
      updateReq = updateReq.input("firstName", sql.VarChar, updates.firstName);
    if (updates.lastName)
      updateReq = updateReq.input("lastName", sql.VarChar, updates.lastName);
    if (updates.newEmail)
      updateReq = updateReq.input("newEmail", sql.VarChar, updates.newEmail);
    if (updates.newPassword)
      updateReq = updateReq.input(
        "newPassword",
        sql.VarChar,
        updates.newPassword
      );

    await updateReq.query(
      `UPDATE users SET ${fields.join(", ")} WHERE id = @id`
    );
    res.json({ success: true });
  } catch (err) {
    res.status(500).json({ error: "Update failed" });
  }
});

// Get All Tenants
app.get("/api/tenants", authenticateToken, async (req, res) => {
  try {
    const result = await db.request().query("SELECT * FROM tenants");
    res.json(result.recordset);
  } catch (err) {
    res.status(500).json({ error: "Database error" });
  }
});

// Get All Property Owners
app.get("/api/property-owners", authenticateToken, async (req, res) => {
  try {
    const result = await db.request().query("SELECT * FROM property_owners");
    res.json(result.recordset);
  } catch (err) {
    res.status(500).json({ error: "Server error" });
  }
});

// GET: All Properties
app.get("/api/properties", authenticateToken, async (req, res) => {
  try {
    const result = await db.request().query("SELECT * FROM properties");
    res.json(result.recordset);
  } catch (err) {
    res.status(500).json({ error: "Failed to fetch properties" });
  }
});

// GET: Property Units (with joined property name)
app.get("/api/property-units", authenticateToken, async (req, res) => {
  try {
    const result = await db.request().query(`
      SELECT pu.*, p.property_name
      FROM property_units pu
      JOIN properties p ON pu.property_id = p.property_id
    `);
    res.json(result.recordset);
  } catch (err) {
    res.status(500).json({ error: "Failed to fetch units" });
  }
});

// GET: All Lease Records
app.get("/api/leases", authenticateToken, async (req, res) => {
  try {
    const result = await db.request().query(`
      SELECT lt.*, p.property_name, pu.unit_number, pu.unit_type, t.email
      FROM leases lt
      LEFT JOIN properties p ON lt.property_id = p.property_id
      LEFT JOIN property_units pu ON lt.property_unit_id = pu.property_unit_id
      LEFT JOIN tenants t ON lt.tenant_id = t.tenant_id
      ORDER BY lt.created_at DESC
    `);
    res.json(result.recordset);
  } catch (err) {
    res.status(500).json({ error: "Failed to fetch leases" });
  }
});

// Insert Tenant
app.post(
  "/api/tenants",
  authenticateToken,
  upload.single("id_document"),
  async (req, res) => {
    try {
      const user_id = req.user.id;
      const {
        last_name,
        first_name,
        email,
        contact_number,
        street,
        barangay,
        city,
        province,
        id_type,
        id_number,
        occupation_status,
        occupation_place,
        emergency_contact_name,
        emergency_contact_number,
        unit_number,
        move_in_date,
        lease_term,
        monthly_rent,
      } = req.body;

      const id_document = req.file ? `/uploads/${req.file.filename}` : null;

      const query = `
      INSERT INTO tenants (
        user_id, last_name, first_name, email, contact_number,
        street, barangay, city, province, id_type, id_number, id_document,
        occupation_status, occupation_place, emergency_contact_name, emergency_contact_number,
        unit_number, move_in_date, lease_term, monthly_rent
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `;

      const values = [
        user_id,
        last_name,
        first_name,
        email,
        contact_number,
        street,
        barangay,
        city,
        province,
        id_type,
        id_number,
        id_document,
        occupation_status,
        occupation_place,
        emergency_contact_name,
        emergency_contact_number,
        unit_number,
        move_in_date,
        lease_term,
        monthly_rent,
      ];

      await db.request().query(query, values);
      res.json({ success: true, message: "Tenant record inserted." });
    } catch (err) {
      console.error("Insert tenant error:", err);
      if (err.code === "ER_DUP_ENTRY") {
        return res
          .status(409)
          .json({ error: "This user already has a tenant record." });
      }
      res.status(500).json({ error: "Failed to insert tenant data." });
    }
  }
);

// Announcements CRUD
app.post(
  "/api/announcements",
  authenticateToken,
  upload.single("file"),
  async (req, res) => {
    try {
      const { title, description } = req.body;
      const fileUrl = req.file ? `/uploads/${req.file.filename}` : null;
      const userId = req.user.id;

      const [result] = await db
        .request()
        .query(
          "INSERT INTO post_announcements (title, description, file_url, user_id) VALUES (?, ?, ?, ?)",
          [title, description, fileUrl, userId]
        );

      const [newPost] = await db
        .request()
        .query("SELECT * FROM post_announcements WHERE id = ?", [
          result.insertId,
        ]);
      io.emit("new_announcement", newPost[0]);
      res.json(newPost[0]);
    } catch (err) {
      console.error("Announcement insert error:", err);
      res.status(500).json({ error: err.message });
    }
  }
);

app.get("/api/announcements", authenticateToken, async (req, res) => {
  try {
    const [rows] = await db
      .request()
      .query(
        "SELECT * FROM post_announcements WHERE user_id = ? ORDER BY created_at DESC",
        [req.user.id]
      );
    res.json(rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.put(
  "/api/announcements/:id",
  authenticateToken,
  upload.single("file"),
  async (req, res) => {
    const { id } = req.params;
    const { title, description } = req.body;
    const newFile = req.file ? `/uploads/${req.file.filename}` : null;

    try {
      const [rows] = await db
        .request()
        .query("SELECT file_url FROM post_announcements WHERE id = ?", [id]);
      if (!rows.length)
        return res.status(404).json({ error: "Announcement not found" });

      const oldFileUrl = rows[0].file_url;
      const fileToUse = newFile || oldFileUrl;

      await db
        .request()
        .query(
          "UPDATE post_announcements SET title = ?, description = ?, file_url = ? WHERE id = ?",
          [title, description, fileToUse, id]
        );

      if (newFile && oldFileUrl && oldFileUrl !== newFile) {
        const filePath = path.join(__dirname, oldFileUrl);
        fs.unlink(filePath, (err) => {
          if (err) console.error("Failed to delete old file:", err);
        });
      }

      const [updated] = await db
        .request()
        .query("SELECT * FROM post_announcements WHERE id = ?", [id]);
      io.emit("announcement_updated", updated[0]);
      res.json(updated[0]);
    } catch (err) {
      res.status(500).json({ error: "Failed to update announcement." });
    }
  }
);

app.delete("/api/announcements/:id", authenticateToken, async (req, res) => {
  const { id } = req.params;
  try {
    const [rows] = await db
      .request()
      .query("SELECT file_url FROM post_announcements WHERE id = ?", [id]);
    const fileUrl = rows[0]?.file_url;

    await db
      .request()
      .query("DELETE FROM post_announcements WHERE id = ?", [id]);

    if (fileUrl) {
      const filePath = path.join(__dirname, fileUrl);
      fs.unlink(filePath, (err) => {
        if (err) console.error("File delete error:", err);
      });
    }

    io.emit("announcement_deleted", { id: parseInt(id) });
    res.json({ success: true });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Fallback 404
app.use((req, res) => {
  res.status(404).json({ error: "Route not found" });
});

// Server listener
const PORT = process.env.PORT || 10000;
server.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});
