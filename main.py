import os
import pymysql
import random
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

# ========================================================
# 1. KONFIGURASI DATABASE & ENVIRONMENTS
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
    """Membuka koneksi ke MySQL"""
    return pymysql.connect(**DB_CONFIG)

# ========================================================
# 2. LOGIKA OTOMATISASI BUAT TABEL (INITIALIZATION)
# ========================================================
def init_db():
    """Membuat tabel secara otomatis jika belum ada di database"""
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # Buat Tabel Riwayat Harga
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS riwayat_harga (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    harga INT NOT NULL,
                    waktu TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            # Buat Tabel Portofolio User
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS portofolio (
                    username VARCHAR(50) PRIMARY KEY,
                    saldo_tunai DOUBLE NOT NULL DEFAULT 1000000,
                    saldo_unit DOUBLE NOT NULL DEFAULT 0,
                    total_dividen DOUBLE NOT NULL DEFAULT 0
                );
            """)
            
            # Cek jika tabel riwayat_harga masih kosong, isi dengan harga awal awal (misal: Rp10.000)
            cursor.execute("SELECT COUNT(*) as total FROM riwayat_harga")
            result = cursor.fetchone()
            if result["total"] == 0:
                cursor.execute("INSERT INTO riwayat_harga (harga) VALUES (10000)")
                
            connection.commit()
            print("=== DATABASE & TABEL BERHASIL DI-INITIALISASI ===")
    except Exception as e:
        print(f"❌ Gagal menginisialisasi database: {e}")
    finally:
        connection.close()

# Menggunakan Lifespan untuk menjalankan init_db saat FastAPI start
@asynccontextmanager
async def George(app: FastAPI):
    init_db()
    yield

app = FastAPI(lifespan=George)

# Izinkan CORS agar index.html bisa menembak API dari mana saja
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========================================================
# 3. ENDPOINTS API MANAGEMENT
# ========================================================

@app.get("/")
def root():
    return {"status": "Backend Aktif", "database": "Terhubung ke Aiven MySQL"}

# --- ENDPOINT: AMBIL DATA HARGA DAN HISTORI (MAX 50) ---
@app.get("/harga")
def get_harga():
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT harga, waktu FROM riwayat_harga ORDER BY id DESC LIMIT 1")
            latest = cursor.fetchone()
            
            if not latest:
                return {"harga_saat_ini": 10000, "last_update": "N/A", "riwayat_harga": []}

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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        connection.close()

# --- ENDPOINT: GET OR CREATE PORTOFOLIO USER ---
@app.get("/portofolio/{username}")
def get_portofolio(username: str):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM portofolio WHERE username = %s", (username,))
            user = cursor.fetchone()
            
            if not user:
                cursor.execute(
                    "INSERT INTO portofolio (username, saldo_tunai, saldo_unit) VALUES (%s, 1000000, 0)",
                    (username,)
                )
                connection.commit()
                cursor.execute("SELECT * FROM portofolio WHERE username = %s", (username,))
                user = cursor.fetchone()

            cursor.execute("SELECT harga FROM riwayat_harga ORDER BY id DESC LIMIT 1")
            harga_latest = cursor.fetchone()
            harga_sekarang = harga_latest["harga"] if harga_latest else 10000

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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        connection.close()

# --- ENDPOINT: REGISTER AKUN (EKSPLISIT) ---
@app.post("/register")
def register_user(payload: dict):
    username = payload.get("username", "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username tidak boleh kosong")
        
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT username FROM portofolio WHERE username = %s", (username,))
            if cursor.fetchone():
                raise HTTPException(status_code=400, detail="Username sudah terdaftar")
            
            cursor.execute(
                "INSERT INTO portofolio (username, saldo_tunai, saldo_unit) VALUES (%s, 1000000, 0)",
                (username,)
            )
            connection.commit()
            return {"message": f"Akun {username} sukses dibuat dengan modal Rp1.000.000"}
    finally:
        connection.close()

# --- ENDPOINT: EKSEKUSI BELI (POTONG FEE 1%) ---
@app.post("/beli")
def beli_aset(payload: dict):
    username = payload.get("username")
    jumlah_unit = float(payload.get("jumlah_unit", 0))

    if jumlah_unit <= 0:
        raise HTTPException(status_code=400, detail="Jumlah unit harus lebih dari 0")

    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM portofolio WHERE username = %s", (username,))
            user = cursor.fetchone()
            if not user:
                raise HTTPException(status_code=404, detail="User tidak ditemukan")

            cursor.execute("SELECT harga FROM riwayat_harga ORDER BY id DESC LIMIT 1")
            latest_harga = cursor.fetchone()
            harga_sekarang = latest_harga["harga"] if latest_harga else 10000

            biaya_pokok = jumlah_unit * harga_sekarang
            fee = biaya_pokok * 0.01
            total_tagihan = biaya_pokok + fee

            if user["saldo_tunai"] < total_tagihan:
                raise HTTPException(status_code=400, detail=f"Saldo tunai tidak cukup. Butuh Rp{total_tagihan:,.0f}")

            saldo_tunai_baru = user["saldo_tunai"] - total_tagihan
            saldo_unit_baru = user["saldo_unit"] + jumlah_unit

            cursor.execute(
                "UPDATE portofolio SET saldo_tunai = %s, saldo_unit = %s WHERE username = %s",
                (saldo_tunai_baru, saldo_unit_baru, username)
            )
            connection.commit()
            return {"message": "Pembelian berhasil"}
    finally:
        connection.close()

# --- ENDPOINT: EKSEKUSI JUAL (POTONG FEE 1%) ---
@app.post("/jual")
def jual_aset(payload: dict):
    username = payload.get("username")
    jumlah_unit = float(payload.get("jumlah_unit", 0))

    if jumlah_unit <= 0:
        raise HTTPException(status_code=400, detail="Jumlah unit harus lebih dari 0")

    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM portofolio WHERE username = %s", (username,))
            user = cursor.fetchone()
            if not user:
                raise HTTPException(status_code=404, detail="User tidak ditemukan")

            if user["saldo_unit"] < jumlah_unit:
                raise HTTPException(status_code=400, detail="Jumlah unit yang kamu miliki tidak mencukupi")

            cursor.execute("SELECT harga FROM riwayat_harga ORDER BY id DESC LIMIT 1")
            latest_harga = cursor.fetchone()
            harga_sekarang = latest_harga["harga"] if latest_harga else 10000

            pendapatan_kotor = jumlah_unit * harga_sekarang
            fee = pendapatan_kotor * 0.01
            total_diterima = pendapatan_kotor - fee

            saldo_tunai_baru = user["saldo_tunai"] + total_diterima
            saldo_unit_baru = user["saldo_unit"] - jumlah_unit

            cursor.execute(
                "UPDATE portofolio SET saldo_tunai = %s, saldo_unit = %s WHERE username = %s",
                (saldo_tunai_baru, saldo_unit_baru, username)
            )
            connection.commit()
            return {"message": "Penjualan berhasil"}
    finally:
        connection.close()

# --- TRIGGER CRON/SIMULASI ACAK HARGA BARU ---
@app.post("/simulasi-acak-harga")
def simulasi_acak_harga():
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT harga FROM riwayat_harga ORDER BY id DESC LIMIT 1")
            latest = cursor.fetchone()
            harga_sekarang = latest["harga"] if latest else 10000
            
            perubahan = random.randint(-500, 500)
            harga_baru = harga_sekarang + perubahan
            if harga_baru < 1000:
                harga_baru = 1000
                
            cursor.execute("INSERT INTO riwayat_harga (harga) VALUES (%s)", (harga_baru,))
            connection.commit()
            return {"status": "Berhasil memperbarui harga pasar", "harga_baru": harga_baru}
    finally:
        connection.close()
