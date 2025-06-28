const express = require('express');
const cors = require('cors');
const mysql = require('mysql2/promise');
const path = require('path');
const multer = require('multer');
const fs = require('fs');
const bcrypt = require('bcrypt');
const jwt = require('jsonwebtoken');
const http = require('http');
const { Server } = require('socket.io');
require('dotenv').config();

const allowedOrigins = process.env.CORS_ORIGINS?.split(',') || [];
const JWT_SECRET = process.env.JWT_SECRET;

if (!JWT_SECRET) {
  console.error('❌ JWT_SECRET is not defined in environment variables.');
  process.exit(1);
}

// Initialize app and server
const app = express();
const server = http.createServer(app);
const io = new Server(server, {
  cors: {
    origin: allowedOrigins,
    methods: ['GET', 'POST', 'PUT', 'DELETE'],
    credentials: true,
  },
});

// Middleware
app.use(cors({
  origin: allowedOrigins,
  methods: ['GET', 'POST', 'PUT', 'DELETE'],
  credentials: true,
}));
app.use(express.json());

// Ensure uploads directory exists
const uploadDir = path.resolve(__dirname, 'uploads');
if (!fs.existsSync(uploadDir)) fs.mkdirSync(uploadDir);
app.use('/uploads', express.static(uploadDir));

// Multer storage setup
const storage = multer.diskStorage({
  destination: (req, file, cb) => cb(null, uploadDir),
  filename: (req, file, cb) => {
    const sanitized = file.originalname.replace(/\s+/g, '_').replace(/[^\w.-]/g, '');
    cb(null, Date.now() + '-' + sanitized);
  },
});
const upload = multer({ storage });

// MySQL Connection
let db;
async function initDb() {
  try {
    db = await mysql.createConnection({
      host: process.env.DB_HOST,
      user: process.env.DB_USER,
      password: process.env.DB_PASS,
      database: process.env.DB_NAME,
      port: 3306,
    });
    console.log('Connected to MySQL');
  } catch (err) {
    console.error('DB connection error:', err);
    process.exit(1);
  }
}
initDb();

// JWT Auth Middleware
function authenticateToken(req, res, next) {
  const token = req.headers['authorization']?.split(' ')[1];
  if (!token) return res.sendStatus(401);

  jwt.verify(token, JWT_SECRET, (err, user) => {
    if (err) return res.sendStatus(403);
    req.user = user;
    next();
  });
}

// ======= ROUTES START ======= //

// Register
app.post('/api/registerstep2', async (req, res) => {
  const { firstName, lastName, email, password } = req.body;
  if (!firstName || !lastName || !email || !password) {
    return res.status(400).json({ error: 'All fields are required' });
  }

  try {
    const hashedPassword = await bcrypt.hash(password, 10);
    await db.query(
      'INSERT INTO users (first_name, last_name, email, password) VALUES (?, ?, ?, ?)',
      [firstName, lastName, email, hashedPassword]
    );
    res.json({ success: true });
  } catch (err) {
    if (err.code === 'ER_DUP_ENTRY') {
      return res.status(409).json({ error: 'Email already exists' });
    }
    res.status(500).json({ error: err.message });
  }
});

// Login
app.post('/api/login', async (req, res) => {
  try {
    const { email, password } = req.body;
    const [rows] = await db.query('SELECT * FROM users WHERE email = ?', [email]);
    if (!rows.length) return res.status(401).json({ error: 'Invalid email or password' });

    const user = rows[0];
    const match = await bcrypt.compare(password, user.password);
    if (!match) return res.status(401).json({ error: 'Invalid email or password' });

    const [announcements] = await db.query(
      'SELECT * FROM post_announcements WHERE user_id = ? ORDER BY created_at DESC',
      [user.id]
    );

    const token = jwt.sign({ id: user.id, email: user.email }, JWT_SECRET, { expiresIn: '1d' });

    res.json({
      token,
      user: {
        id: user.id,
        email: user.email,
        firstName: user.first_name,
        lastName: user.last_name,
        avatar: user.avatar || null,
        announcements,
      },
    });
  } catch (err) {
    console.error('Login error:', err);
    res.status(500).json({ error: 'Server error' });
  }
});

// Update Avatar
app.put('/api/users/avatar', authenticateToken, upload.single('avatar'), async (req, res) => {
  const userId = req.user.id;
  if (!req.file) return res.status(400).json({ error: 'No file uploaded' });

  const avatarPath = `/uploads/${req.file.filename}`;

  try {
    await db.query('UPDATE users SET avatar = ? WHERE id = ?', [avatarPath, userId]);
    res.json({ avatar: avatarPath });
  } catch (err) {
    console.error('Avatar update error:', err);
    res.status(500).json({ error: 'Failed to update avatar' });
  }
});

// Update User Profile
app.put('/api/users/:id', authenticateToken, async (req, res) => {
  const { id } = req.params;
  const { firstName, lastName, email, password, currentPassword } = req.body;

  try {
    const fields = [];
    const values = [];

    const [rows] = await db.query('SELECT password FROM users WHERE id = ?', [id]);
    if (!rows.length) return res.status(404).json({ error: 'User not found' });

    const storedHashedPassword = rows[0].password;

    if (firstName && lastName) {
      fields.push('first_name = ?', 'last_name = ?');
      values.push(firstName, lastName);
    }

    if (email && password) {
      const match = await bcrypt.compare(password, storedHashedPassword);
      if (!match) return res.status(401).json({ error: 'Incorrect password' });
      fields.push('email = ?');
      values.push(email);
    }

    if (currentPassword && password && currentPassword !== password) {
      const match = await bcrypt.compare(currentPassword, storedHashedPassword);
      if (!match) return res.status(401).json({ error: 'Incorrect current password' });
      const hashedNewPassword = await bcrypt.hash(password, 10);
      fields.push('password = ?');
      values.push(hashedNewPassword);
    }

    if (!fields.length) {
      return res.status(400).json({ error: 'No valid fields provided for update' });
    }

    values.push(id);
    await db.query(`UPDATE users SET ${fields.join(', ')} WHERE id = ?`, values);

    res.json({ success: true, updated: { firstName, lastName, email } });
  } catch (err) {
    console.error('User update error:', err);
    res.status(500).json({ error: 'Failed to update user' });
  }
});

// Get All Tenants
app.get('/api/tenants', authenticateToken, async (req, res) => {
  try {
    const [results] = await db.query('SELECT * FROM tenants');
    res.json(results);
  } catch (err) {
    console.error('Fetch tenants error:', err);
    res.status(500).json({ error: 'Database error' });
  }
});

// Get All Property Owners
app.get('/api/property-owners', authenticateToken, async (req, res) => {
  try {
    const [rows] = await db.query('SELECT * FROM property_owners');
    res.json(rows);
  } catch (err) {
    console.error('Error fetching all property owners:', err);
    res.status(500).json({ error: 'Server error' });
  }
});

// GET: All Properties
app.get('/api/properties', authenticateToken, async (req, res) => {
  try {
    const [rows] = await db.query('SELECT * FROM properties');
    res.json(rows);
  } catch (err) {
    console.error('Error fetching properties:', err);
    res.status(500).json({ error: 'Failed to fetch properties' });
  }
});

// GET: Property Units (with joined property name)
app.get('/api/property-units', authenticateToken, async (req, res) => {
  try {
    const [rows] = await db.query(`
      SELECT 
        property_units.property_unit_id,
        property_units.property_id,
        property_units.unit_type,
        property_units.unit_number,
        property_units.rent_price,
        property_units.status,
        properties.property_name
      FROM property_units
      JOIN properties ON property_units.property_id = properties.property_id
    `);
    res.json(rows);
  } catch (err) {
    console.error('Error fetching property units:', err);
    res.status(500).json({ error: 'Failed to fetch property units' });
  }
});

// GET: All Lease Records
app.get('/api/leases', authenticateToken, async (req, res) => {
  try {
    const [rows] = await db.query(`
      SELECT 
        lt.*, 
        p.property_name, 
        pu.unit_number, 
        pu.unit_type, 
        t.email
      FROM leases lt
      LEFT JOIN properties p ON lt.property_id = p.property_id
      LEFT JOIN property_units pu ON lt.property_unit_id = pu.property_unit_id
      LEFT JOIN tenants t ON lt.tenant_id = t.tenant_id
      ORDER BY lt.created_at DESC
    `);
    res.json(rows);
  } catch (err) {
    console.error('Error fetching leases:', err);
    res.status(500).json({ error: 'Failed to fetch leases' });
  }
});

// Insert Tenant
app.post('/api/tenants', authenticateToken, upload.single('id_document'), async (req, res) => {
  try {
    const user_id = req.user.id;
    const {
      last_name, first_name, email, contact_number, street, barangay, city, province,
      id_type, id_number, occupation_status, occupation_place,
      emergency_contact_name, emergency_contact_number,
      unit_number, move_in_date, lease_term, monthly_rent
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
      user_id, last_name, first_name, email, contact_number, street, barangay, city, province,
      id_type, id_number, id_document, occupation_status, occupation_place,
      emergency_contact_name, emergency_contact_number, unit_number, move_in_date, lease_term, monthly_rent
    ];

    await db.query(query, values);
    res.json({ success: true, message: 'Tenant record inserted.' });
  } catch (err) {
    console.error('Insert tenant error:', err);
    if (err.code === 'ER_DUP_ENTRY') {
      return res.status(409).json({ error: 'This user already has a tenant record.' });
    }
    res.status(500).json({ error: 'Failed to insert tenant data.' });
  }
});

// GET: ID Types
app.get('/api/id-types', authenticateToken, async (req, res) => {
  try {
    const [rows] = await db.query('SELECT id, type FROM id_types');
    res.json(rows);
  } catch (err) {
    console.error('Error fetching ID types:', err);
    res.status(500).json({ error: 'Failed to fetch ID types' });
  }
});

// GET: Occupation Statuses
app.get('/api/occupation-statuses', authenticateToken, async (req, res) => {
  try {
    const [rows] = await db.query('SELECT id, status FROM occupation_statuses');
    res.json(rows);
  } catch (err) {
    console.error('Error fetching occupation statuses:', err);
    res.status(500).json({ error: 'Failed to fetch occupation statuses' });
  }
});

// GET: Units (Only available units)
app.get('/api/units', authenticateToken, async (req, res) => {
  try {
    const [rows] = await db.query('SELECT id, unit_number FROM units WHERE is_occupied = 0');
    res.json(rows);
  } catch (err) {
    console.error('Error fetching units:', err);
    res.status(500).json({ error: 'Failed to fetch units' });
  }
});

// GET: Emergency Contact Relations
app.get('/api/emergency-contact-relations', authenticateToken, async (req, res) => {
  try {
    const [rows] = await db.query('SELECT id, relation FROM emergency_contact_relations');
    res.json(rows);
  } catch (err) {
    console.error('Error fetching emergency contact relations:', err);
    res.status(500).json({ error: 'Failed to fetch emergency contact relations' });
  }
});

// Announcements CRUD
app.post('/api/announcements', authenticateToken, upload.single('file'), async (req, res) => {
  try {
    const { title, description } = req.body;
    const fileUrl = req.file ? `/uploads/${req.file.filename}` : null;
    const userId = req.user.id;

    const [result] = await db.query(
      'INSERT INTO post_announcements (title, description, file_url, user_id) VALUES (?, ?, ?, ?)',
      [title, description, fileUrl, userId]
    );

    const [newPost] = await db.query('SELECT * FROM post_announcements WHERE id = ?', [result.insertId]);
    io.emit('new_announcement', newPost[0]);
    res.json(newPost[0]);
  } catch (err) {
    console.error('Announcement insert error:', err);
    res.status(500).json({ error: err.message });
  }
});

app.get('/api/announcements', authenticateToken, async (req, res) => {
  try {
    const [rows] = await db.query(
      'SELECT * FROM post_announcements WHERE user_id = ? ORDER BY created_at DESC',
      [req.user.id]
    );
    res.json(rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.put('/api/announcements/:id', authenticateToken, upload.single('file'), async (req, res) => {
  const { id } = req.params;
  const { title, description } = req.body;
  const newFile = req.file ? `/uploads/${req.file.filename}` : null;

  try {
    const [rows] = await db.query('SELECT file_url FROM post_announcements WHERE id = ?', [id]);
    if (!rows.length) return res.status(404).json({ error: 'Announcement not found' });

    const oldFileUrl = rows[0].file_url;
    const fileToUse = newFile || oldFileUrl;

    await db.query(
      'UPDATE post_announcements SET title = ?, description = ?, file_url = ? WHERE id = ?',
      [title, description, fileToUse, id]
    );

    if (newFile && oldFileUrl && oldFileUrl !== newFile) {
      const filePath = path.join(__dirname, oldFileUrl);
      fs.unlink(filePath, (err) => {
        if (err) console.error('Failed to delete old file:', err);
      });
    }

    const [updated] = await db.query('SELECT * FROM post_announcements WHERE id = ?', [id]);
    io.emit('announcement_updated', updated[0]);
    res.json(updated[0]);
  } catch (err) {
    res.status(500).json({ error: 'Failed to update announcement.' });
  }
});

app.delete('/api/announcements/:id', authenticateToken, async (req, res) => {
  const { id } = req.params;
  try {
    const [rows] = await db.query('SELECT file_url FROM post_announcements WHERE id = ?', [id]);
    const fileUrl = rows[0]?.file_url;

    await db.query('DELETE FROM post_announcements WHERE id = ?', [id]);

    if (fileUrl) {
      const filePath = path.join(__dirname, fileUrl);
      fs.unlink(filePath, (err) => {
        if (err) console.error('File delete error:', err);
      });
    }

    io.emit('announcement_deleted', { id: parseInt(id) });
    res.json({ success: true });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Get All Users
app.get('/api/users', authenticateToken, async (req, res) => {
  try {
    const [rows] = await db.query('SELECT id, first_name, last_name, email, avatar FROM users');
    res.json(rows);
  } catch (err) {
    console.error('Fetch users error:', err);
    res.status(500).json({ error: 'Server error' });
  }
});

// Fallback 404
app.use((req, res) => {
  res.status(404).json({ error: 'Route not found' });
});

// Socket.IO listeners
io.on('connection', (socket) => {
  console.log('Client connected:', socket.id);
  socket.on('disconnect', () => {
    console.log('Client disconnected:', socket.id);
  });
});

// Server listener
const PORT = process.env.PORT || 5000;
server.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});

// Optional export for socket reuse
module.exports = io;
