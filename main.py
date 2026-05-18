import os
import pymysql
import hashlib
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import asynccontextmanager

# ========================================================
# 1. DATABASE CONFIGURATION (SINKRON KE AIVEN/RAILWAY ENV)
# ========================================================
DB_CONFIG = {
    "host": os.getenv("MYSQLHOST", "localhost"),
    "port": int(os.getenv("MYSQLPORT", 3306)),
    "user": os.getenv("MYSQLUSER", "root"),
    "password": os.getenv("MYSQLPASSWORD", ""),
    "database": os.getenv("MYSQLDATABASE", "defaultdb"),
    "cursorclass": pymysql.cursors.DictCursor
}

def get_db_connection():
    return pymysql.connect(**DB_CONFIG)

# ========================================================
# 2. SEED DATABASE & GERBANG AWAL HARGA Rp100
# ========================================================
def init_db():
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # Tabel Histori Pergerakan Harga Efek/Aset
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS riwayat_harga (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    harga DOUBLE NOT NULL,
                    waktu TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            # Tabel Portofolio & Akun Keamanan Investor
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS portofolio (
                    username VARCHAR(50) PRIMARY KEY,
                    password_hash VARCHAR(255) NOT NULL,
                    saldo_tunai DOUBLE NOT NULL DEFAULT 0,
                    saldo_unit DOUBLE NOT NULL DEFAULT 0,
                    total_dividen DOUBLE NOT NULL DEFAULT 0
                );
            """)
            
            # Mengunci Harga Awal Sistem Tepat di Rp100 jika database kosong
            cursor.execute("SELECT COUNT(*) as total FROM riwayat_harga")
            if cursor.fetchone()["total"] == 0:
                cursor.execute("INSERT INTO riwayat_harga (harga) VALUES (100.0)")
                
            connection.commit()
            print("=== SISTEM INVESTASI REAL AUTOMATIC VOLUMETRIK ONLINE ===")
    except Exception as e:
        print(f"❌ Gagal Inisialisasi Database: {e}")
    finally:
        connection.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(lifespan=lifespan)

# Pengaman CORS agar file index.html dari lokal/hosting lain bisa mengakses API ini
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========================================================
# 3. PYDANTIC MODEL SCHEMAS (VALIDASI STRUKTUR REQ JSON)
# ========================================================
class AuthModel(BaseModel):
    username: str
    password: str

class OrderModel(BaseModel):
    username: str
    jumlah_unit: float

class AdminKelolaSaldoModel(BaseModel):
    username: str
    nominal: float
    aksi: str  # Nilai wajib: "deposit" atau "withdrawal"
    admin_secret_key: str

# Kunci Token Pengaman Eksekusi API Admin kamu
ADMIN_SECRET_TOKEN = "LibertyAdminSuperSecret2026"

# Helper Enkripsi Rahasia Password User
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

# ========================================================
# 4. ALGORITMA MEKANISME HARGA BERBASIS VOLUMETRIK
# ========================================================
def hitung_perubahan_harga(cursor, jumlah_unit, aksi):
    """
    Sistem murni otomatis: Harga bergerak real-time berdasarkan volume transaksi.
    Setiap 1 unit transaksi menggeser nilai aset sebesar Rp0.5 (Dapat diubah sesuai preferensi).
    """
    cursor.execute("SELECT harga FROM riwayat_harga ORDER BY id DESC LIMIT 1")
    harga_sekarang = cursor.fetchone()["harga"]
    
    SENSITIVITAS = 0.5 
    
    if aksi == "beli":
        # Permintaan Naik = Harga Terdongkrak Naik
        harga_baru = harga_sekarang + (jumlah_unit * SENSITIVITAS)
    elif aksi == "jual":
        # Aset Banjir di Pasar = Harga Tertekan Turun
        harga_baru = harga_sekarang - (jumlah_unit * SENSITIVITAS)
        
    # Batas bawah psikologis sistem agar harga tidak menyentuh Rp0 atau minus
    if harga_baru < 1.0:
        harga_baru = 1.0
        
    cursor.execute("INSERT INTO riwayat_harga (harga) VALUES (%s)", (harga_baru,))

# ========================================================
# 5. PUBLIC INVESTOR ENDPOINTS
# ========================================================

@app.get("/")
def root():
    return {"status": "Platform Active", "system": "Liberty Volumetric Trading Engine"}

# --- PENDAFTARAN AKUN INVESTOR BARU ---
@app.post("/register")
def register_investor(user_data: AuthModel):
    username = user_data.username.strip()
    if not username or len(user_data.password) < 6:
        raise HTTPException(status_code=400, detail="Username valid & Password minimal 6 karakter!")
        
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT username FROM portofolio WHERE username = %s", (username,))
            if cursor.fetchone():
                raise HTTPException(status_code=400, detail="Username sudah terdaftar di sistem!")
            
            p_hash = hash_password(user_data.password)
            # Saldo awal 0 rupiah (Investor wajib deposit dana riil terlebih dahulu via Admin)
            cursor.execute(
                "INSERT INTO portofolio (username, password_hash, saldo_tunai) VALUES (%s, %s, 0)",
                (username, p_hash)
            )
            connection.commit()
            return {"status": "success", "message": f"Investor {username} berhasil didaftarkan."}
    finally:
        connection.close()

# --- VERIFIKASI LOGIN INVESTOR ---
@app.post("/login")
def login_investor(user_data: AuthModel):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT password_hash FROM portofolio WHERE username = %s", (user_data.username,))
            user = cursor.fetchone()
            if not user or user["password_hash"] != hash_password(user_data.password):
                raise HTTPException(status_code=401, detail="Username atau Password salah!")
            return {"status": "success", "username": user_data.username}
    finally:
        connection.close()

# --- FETCH DATA HARGA & HISTORI GRAPH ---
@app.get("/harga")
def get_harga():
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT harga, waktu FROM riwayat_harga ORDER BY id DESC LIMIT 1")
            latest = cursor.fetchone()
            if not latest:
                return {"harga_saat_ini": 100, "last_update": "N/A", "riwayat_harga": []}

            cursor.execute("SELECT harga, waktu FROM riwayat_harga ORDER BY id DESC LIMIT 50")
            chart_data = cursor.fetchall()
            chart_data.reverse() 

            for d in chart_data:
                d["waktu"] = d["waktu"].strftime("%H:%M:%S")

            return {
                "harga_saat_ini": latest["harga"],
                "last_update": latest["waktu"].strftime("%H:%M:%S"),
                "riwayat_harga": chart_data
            }
    finally:
        connection.close()

# --- FETCH NERACA SALDO & PORTOFOLIO USER ---
@app.get("/portofolio/{username}")
def get_portofolio(username: str):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT username, saldo_tunai, saldo_unit, total_dividen FROM portofolio WHERE username = %s", (username,))
            user = cursor.fetchone()
            if not user:
                raise HTTPException(status_code=404, detail="Akun Investor tidak ditemukan")

            cursor.execute("SELECT harga FROM riwayat_harga ORDER BY id DESC LIMIT 1")
            latest_harga = cursor.fetchone()
            harga_sekarang = latest_harga["harga"] if latest_harga else 100

            nilai_unit = user["saldo_unit"] * harga_sekarang
            total_kekayaan = user["saldo_tunai"] + nilai_unit

            return {
                "username": user["username"],
                "saldo_tunai": user["saldo_tunai"],
                "saldo_unit": user["saldo_unit"],
                "total_dividen": user["total_dividen"],
                "nilai_unit": nilai_unit,
                "total_kekayaan": total_kekayaan
            }
    finally:
        connection.close()

# --- EKSEKUSI PEMBELIAN (DANA BERKURANG -> HARGA NAIK) ---
@app.post("/beli")
def beli_aset(order: OrderModel):
    if order.jumlah_unit <= 0:
        raise HTTPException(status_code=400, detail="Volume unit order tidak valid!")

    connection = get_db_connection()
    try:
        connection.begin() # Kunci database untuk transaksi ACID
        with connection.cursor() as cursor:
            # Mengunci baris user agar tidak terjadi Race Condition manipulasi saldo ganda
            cursor.execute("SELECT saldo_tunai, saldo_unit FROM portofolio WHERE username = %s FOR UPDATE", (order.username,))
            user = cursor.fetchone()
            if not user:
                raise HTTPException(status_code=404, detail="User tidak ditemukan")

            cursor.execute("SELECT harga FROM riwayat_harga ORDER BY id DESC LIMIT 1")
            harga_sekarang = cursor.fetchone()["harga"]

            total_tagihan = order.jumlah_unit * harga_sekarang

            if user["saldo_tunai"] < total_tagihan:
                raise HTTPException(status_code=400, detail="Gagal Beli: Dana kas tunai Anda tidak mencukupi")

            # 1. Update Akun Saldo Kas Tunai dan Volume Unit Investor
            cursor.execute(
                "UPDATE portofolio SET saldo_tunai = saldo_tunai - %s, saldo_unit = saldo_unit + %s WHERE username = %s",
                (total_tagihan, order.jumlah_unit, order.username)
            )
            
            # 2. Jalankan Pergeseran Algoritma Harga Sistem (UP)
            hitung_perubahan_harga(cursor, order.jumlah_unit, "beli")
            
            connection.commit()
            return {"status": "success", "message": "Eksekusi Order Pembelian Berhasil"}
    except Exception as e:
        connection.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        connection.close()

# --- EKSEKUSI PENJUALAN (DANA BERTAMBAH -> HARGA TURUN) ---
@app.post("/jual")
def jual_aset(order: OrderModel):
    if order.jumlah_unit <= 0:
        raise HTTPException(status_code=400, detail="Volume unit order tidak valid!")

    connection = get_db_connection()
    try:
        connection.begin()
        with connection.cursor() as cursor:
            cursor.execute("SELECT saldo_tunai, saldo_unit FROM portofolio WHERE username = %s FOR UPDATE", (order.username,))
            user = cursor.fetchone()
            if not user:
                raise HTTPException(status_code=404, detail="User tidak ditemukan")

            if user["saldo_unit"] < order.jumlah_unit:
                raise HTTPException(status_code=400, detail="Gagal Jual: Kepemilikan Unit Aset tidak mencukupi")

            cursor.execute("SELECT harga FROM riwayat_harga ORDER BY id DESC LIMIT 1")
            harga_sekarang = cursor.fetchone()["harga"]

            total_dana_diterima = order.jumlah_unit * harga_sekarang

            # 1. Update Akun Kas Tunai (Bertambah) dan Volume Unit Investor (Berkurang)
            cursor.execute(
                "UPDATE portofolio SET saldo_tunai = saldo_tunai + %s, saldo_unit = saldo_unit - %s WHERE username = %s",
                (total_dana_diterima, order.jumlah_unit, order.username)
            )
            
            # 2. Jalankan Pergeseran Algoritma Harga Sistem (DOWN)
            hitung_perubahan_harga(cursor, order.jumlah_unit, "jual")
            
            connection.commit()
            return {"status": "success", "message": "Eksekusi Order Penjualan Berhasil"}
    except Exception as e:
        connection.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        connection.close()

# ========================================================
# 6. ADMIN PRIVATE CONTROL ENDPOINTS (DEPOSIT & WITHDRAWAL)
# ========================================================
@app.post("/admin/kelola-saldo")
def admin_kelola_saldo(data: AdminKelolaSaldoModel):
    # Verifikasi Autentikasi Secret Key Admin API
    if data.admin_secret_key != ANAKMIJAN11:
        raise HTTPException(status_code=403, detail="Akses Ditolak: Secret Key Admin Tidak Valid!")
        
    if data.nominal <= 0:
        raise HTTPException(status_code=400, detail="Nominal saldo harus lebih besar dari 0!")
        
    aksi_tipe = data.aksi.strip().lower()
    if aksi_tipe not in ["deposit", "withdrawal"]:
        raise HTTPException(status_code=400, detail="Aksi gagal: Gunakan 'deposit' atau 'withdrawal'")

    connection = get_db_connection()
    try:
        connection.begin()
        with connection.cursor() as cursor:
            cursor.execute("SELECT username, saldo_tunai FROM portofolio WHERE username = %s FOR UPDATE", (data.username,))
            user = cursor.fetchone()
            if not user:
                raise HTTPException(status_code=404, detail="Nama user tidak terdaftar dalam database!")

            if aksi_tipe == "deposit":
                cursor.execute(
                    "UPDATE portofolio SET saldo_tunai = saldo_tunai + %s WHERE username = %s",
                    (data.nominal, data.username)
                )
                msg = f"Sukses sanksi DEPOSIT Rp{data.nominal:,} ke user {data.username}"
                
            elif aksi_tipe == "withdrawal":
                if user["saldo_tunai"] < data.nominal:
                    raise HTTPException(status_code=400, detail="Gagal WD: Dana kas tunai user tidak mencukupi!")
                    
                cursor.execute(
                    "UPDATE portofolio SET saldo_tunai = saldo_tunai - %s WHERE username = %s",
                    (data.nominal, data.username)
                )
                msg = f"Sukses sanksi WITHDRAWAL Rp{data.nominal:,} dari user {data.username}"

            connection.commit()
            return {"status": "success", "message": msg}
            
    except HTTPException as he:
        connection.rollback()
        raise he
    except Exception as e:
        connection.rollback()
        raise HTTPException(status_code=500, detail=f"Sistem Crash Internal: {str(e)}")
    finally:
        connection.close()
