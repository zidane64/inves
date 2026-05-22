import os
import hashlib
import pymysql
import asyncio
from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import asynccontextmanager
from datetime import datetime

# ==========================================
# 1. KONEKSI DATABASE & INITIALIZATION (AIVEN)
# ==========================================
def get_db_connection():
    return pymysql.connect(
        host=os.getenv("MYSQLHOST"),
        port=int(os.getenv("MYSQLPORT", 3306)),
        user=os.getenv("MYSQLUSER"),
        password=os.getenv("MYSQLPASSWORD"),
        database=os.getenv("MYSQLDATABASE", "defaultdb"),
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True
    )

def init_db():
    """Membuat semua tabel yang dibutuhkan jika belum ada saat startup"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Tabel Investor
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS investor (
                    username VARCHAR(50) PRIMARY KEY,
                    password_hash VARCHAR(255) NOT NULL,
                    saldo_tunai DOUBLE NOT NULL DEFAULT 0.0,
                    saldo_unit DOUBLE NOT NULL DEFAULT 0.0
                )
            """)
            # Tabel Histori Harga
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS histori_harga (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    harga DOUBLE NOT NULL,
                    waktu TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Tabel Permintaan Dana (Topup/Withdraw)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS permintaan_dana (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(50) NOT NULL,
                    tipe VARCHAR(10) NOT NULL,
                    nominal DOUBLE NOT NULL,
                    metode VARCHAR(20) NOT NULL,
                    catatan TEXT,
                    nama_pengirim VARCHAR(100),
                    nomor_referensi VARCHAR(100),
                    nomor_ewallet VARCHAR(50),
                    nama_pemilik VARCHAR(100),
                    status VARCHAR(20) NOT NULL DEFAULT 'pending',
                    waktu TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    waktu_diproses TIMESTAMP NULL
                )
            """)
            
            # Seeding harga awal jika kosong
            cursor.execute("SELECT COUNT(*) AS total FROM histori_harga")
            res = cursor.fetchone()
            if res['total'] == 0:
                cursor.execute("INSERT INTO histori_harga (harga) VALUES (100.0)")
                print("=== SEEDING: Harga awal aset berhasil diset ke Rp100 ===")
    finally:
        conn.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("=== SISTEM INVESTASI REAL AUTOMATIC VOLUMETRIK ONLINE ===")
    loop = asyncio.get_running_loop()
    # Menjalankan seluruh inisialisasi database di dalam lifespan (Aman & Sinkron)
    await loop.run_in_executor(None, init_db)
    yield

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# 2. VALIDASI DATA VALIDATOR (PYDANTIC SCHEMAS)
# ==========================================
class AuthModel(BaseModel):
    username: str
    password: str

class TradeModel(BaseModel):
    username: str
    jumlah_unit: float

class AdminControlModel(BaseModel):
    username: str
    nominal: float
    aksi: str  # "deposit" atau "withdrawal"
    admin_secret_key: str

class RequestModel(BaseModel):
    username: str
    tipe: str        # "topup" atau "withdraw"
    nominal: float
    metode: str      # dana / gopay / ovo
    catatan: str = ""
    nama_pengirim: str = ""
    nomor_referensi: str = ""
    nomor_ewallet: str = ""
    nama_pemilik: str = ""

class UpdateRequestModel(BaseModel):
    request_id: int
    status: str      # "approved" / "rejected"
    admin_secret_key: str

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def verify_admin(secret_key: str):
    # Mengambil token admin dari environment variable demi keamanan
    expected = os.getenv("ADMIN_SECRET_KEY", "LibertyAdminSuperSecret2026")
    if secret_key != expected:
        raise HTTPException(status_code=403, detail="Token admin tidak valid!")

# ==========================================
# 3. CORE ENDPOINTS ROUTER (BACKEND API)
# ==========================================

@app.post("/register")
def register_investor(data: AuthModel):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT username FROM investor WHERE username = %s", (data.username,))
            if cursor.fetchone():
                raise HTTPException(status_code=400, detail="Username sudah terdaftar di sistem!")

            p_hash = hash_password(data.password)
            cursor.execute(
                "INSERT INTO investor (username, password_hash, saldo_tunai, saldo_unit) VALUES (%s, %s, 500.0, 0.0)",
                (data.username, p_hash)
            )
            return {"message": "Registrasi sukses! Saldo bonus Rp 500 telah ditambahkan."}
    finally:
        conn.close()

@app.post("/login")
def login_investor(data: AuthModel):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            p_hash = hash_password(data.password)
            cursor.execute(
                "SELECT username FROM investor WHERE username = %s AND password_hash = %s",
                (data.username, p_hash)
            )
            user = cursor.fetchone()
            if not user:
                raise HTTPException(status_code=401, detail="Username atau Password salah!")
            return {"message": "Login berhasil", "username": user["username"]}
    finally:
        conn.close()

@app.get("/harga")
def get_harga_terkini():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT harga, waktu FROM histori_harga ORDER BY id DESC LIMIT 1")
            current = cursor.fetchone()
            cursor.execute("SELECT harga, DATE_FORMAT(waktu, '%%H:%%i:%%s') as waktu FROM histori_harga ORDER BY id DESC LIMIT 50")
            history = cursor.fetchall()
            history.reverse()
            return {
                "harga_saat_ini": current["harga"] if current else 100.0,
                "last_update": current["waktu"].strftime("%H:%M:%S") if current else "--:--:--",
                "riwayat_harga": history
            }
    finally:
        conn.close()

@app.get("/portofolio/{username}")
def get_portofolio(username: str):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT saldo_tunai, saldo_unit FROM investor WHERE username = %s", (username,))
            user = cursor.fetchone()
            if not user:
                raise HTTPException(status_code=404, detail="Investor tidak ditemukan")
            cursor.execute("SELECT harga FROM histori_harga ORDER BY id DESC LIMIT 1")
            current_harga = cursor.fetchone()["harga"]
            nilai_unit = user["saldo_unit"] * current_harga
            total_kekayaan = user["saldo_tunai"] + nilai_unit
            return {
                "username": username,
                "saldo_tunai": user["saldo_tunai"],
                "saldo_unit": user["saldo_unit"],
                "nilai_unit": nilai_unit,
                "total_kekayaan": total_kekayaan
            }
    finally:
        conn.close()

@app.post("/beli")
def eksekusi_beli(data: TradeModel):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT saldo_tunai, saldo_unit FROM investor WHERE username = %s FOR UPDATE", (data.username,))
            user = cursor.fetchone()
            if not user: raise HTTPException(status_code=404, detail="User tidak ditemukan")
            cursor.execute("SELECT harga FROM histori_harga ORDER BY id DESC LIMIT 1 FOR UPDATE")
            harga_sekarang = cursor.fetchone()["harga"]
            total_biaya = data.jumlah_unit * harga_sekarang
            if user["saldo_tunai"] < total_biaya:
                raise HTTPException(status_code=400, detail=f"Saldo tidak cukup! Butuh Rp{total_biaya:,.0f}")
            cursor.execute(
                "UPDATE investor SET saldo_tunai = saldo_tunai - %s, saldo_unit = saldo_unit + %s WHERE username = %s",
                (total_biaya, data.jumlah_unit, data.username)
            )
            harga_baru = harga_sekarang + (data.jumlah_unit * 0.5)
            cursor.execute("INSERT INTO histori_harga (harga) VALUES (%s)", (harga_baru,))
            return {"message": "Order buy sukses", "harga_baru": harga_baru}
    finally:
        conn.close()

@app.post("/jual")
def eksekusi_jual(data: TradeModel):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT saldo_tunai, saldo_unit FROM investor WHERE username = %s FOR UPDATE", (data.username,))
            user = cursor.fetchone()
            if not user: raise HTTPException(status_code=404, detail="User tidak ditemukan")
            if user["saldo_unit"] < data.jumlah_unit:
                raise HTTPException(status_code=400, detail="Unit tidak mencukupi untuk dijual!")
            cursor.execute("SELECT harga FROM histori_harga ORDER BY id DESC LIMIT 1 FOR UPDATE")
            harga_sekarang = cursor.fetchone()["harga"]
            total_hasil = data.jumlah_unit * harga_sekarang
            cursor.execute(
                "UPDATE investor SET saldo_tunai = saldo_tunai + %s, saldo_unit = saldo_unit - %s WHERE username = %s",
                (total_hasil, data.jumlah_unit, data.username)
            )
            harga_baru = max(100.0, harga_sekarang - (data.jumlah_unit * 0.5))
            cursor.execute("INSERT INTO histori_harga (harga) VALUES (%s)", (harga_baru,))
            return {"message": "Order sell sukses", "harga_baru": harga_baru}
    finally:
        conn.close()

@app.post("/admin/kelola-saldo")
def admin_kelola_saldo(data: AdminControlModel):
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
    if not ADMIN_PASSWORD or data.admin_secret_key != ADMIN_PASSWORD:
        raise HTTPException(status_code=403, detail="Admin secret key tidak valid!")

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT saldo_tunai FROM investor WHERE username = %s FOR UPDATE", (data.username,))
            user = cursor.fetchone()
            if not user:
                raise HTTPException(status_code=404, detail=f"User '{data.username}' tidak ditemukan!")

            if data.aksi == "deposit":
                cursor.execute(
                    "UPDATE investor SET saldo_tunai = saldo_tunai + %s WHERE username = %s",
                    (data.nominal, data.username)
                )
                return {"message": f"Deposit Rp{data.nominal:,.0f} ke '{data.username}' berhasil!"}

            elif data.aksi == "withdrawal":
                if user["saldo_tunai"] < data.nominal:
                    raise HTTPException(status_code=400, detail="Saldo investor tidak mencukupi untuk withdrawal!")
                cursor.execute(
                    "UPDATE investor SET saldo_tunai = saldo_tunai - %s WHERE username = %s",
                    (data.nominal, data.username)
                )
                return {"message": f"Withdrawal Rp{data.nominal:,.0f} dari '{data.username}' berhasil!"}
            else:
                raise HTTPException(status_code=400, detail="Aksi tidak valid! Gunakan 'deposit' atau 'withdrawal'.")
    finally:
        conn.close()


# ==========================================
# 4. ADMIN PANEL & PERMINTAAN DANA
# ==========================================

@app.get("/admin/users")
def admin_get_all_users(admin_secret_key: str):
    verify_admin(admin_secret_key)
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT harga FROM histori_harga ORDER BY id DESC LIMIT 1")
            row = cursor.fetchone()
            harga = row["harga"] if row else 100.0

            cursor.execute("""
                SELECT username, saldo_tunai, saldo_unit
                FROM investor
                WHERE username != 'admin'
                ORDER BY saldo_tunai DESC
            """)
            users = cursor.fetchall()
            result = []
            for u in users:
                nilai_unit = u["saldo_unit"] * harga
                result.append({
                    "username": u["username"],
                    "saldo_tunai": u["saldo_tunai"],
                    "saldo_unit": u["saldo_unit"],
                    "nilai_unit": nilai_unit,
                    "total_kekayaan": u["saldo_tunai"] + nilai_unit
                })
            return {"users": result, "harga_aset": harga}
    finally:
        conn.close()


@app.get("/admin/requests")
def admin_get_requests(admin_secret_key: str):
    verify_admin(admin_secret_key)
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT * FROM permintaan_dana
                ORDER BY
                    CASE WHEN status = 'pending' THEN 0 ELSE 1 END,
                    waktu DESC
                LIMIT 100
            """)
            rows = cursor.fetchall()
            for r in rows:
                if r.get("waktu"):
                    r["waktu"] = r["waktu"].strftime("%d/%m/%Y %H:%M")
                if r.get("waktu_diproses"):
                    r["waktu_diproses"] = r["waktu_diproses"].strftime("%d/%m/%Y %H:%M")
            return {"requests": rows}
    finally:
        conn.close()


@app.post("/request/dana")
def submit_request_dana(data: RequestModel):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT username FROM investor WHERE username = %s", (data.username,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="User tidak ditemukan")
            cursor.execute("""
                INSERT INTO permintaan_dana
                (username, tipe, nominal, metode, catatan, nama_pengirim, nomor_referensi, nomor_ewallet, nama_pemilik, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending')
            """, (
                data.username, data.tipe, data.nominal, data.metode,
                data.catatan, data.nama_pengirim, data.nomor_referensi,
                data.nomor_ewallet, data.nama_pemilik
            ))
            return {"message": "Permintaan berhasil dikirim dan menunggu verifikasi admin."}
    finally:
        conn.close()


@app.post("/admin/proses-request")
def admin_proses_request(data: UpdateRequestModel):
    verify_admin(data.admin_secret_key)
    if data.status not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="Status harus 'approved' atau 'rejected'")

    conn = get_db_connection()
    # Menonaktifkan autocommit sementara untuk membuat database transaction yang aman
    conn.autocommit(False)
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM permintaan_dana WHERE id = %s FOR UPDATE", (data.request_id,))
            req = cursor.fetchone()
            if not req:
                raise HTTPException(status_code=404, detail="Request tidak ditemukan")
            if req["status"] != "pending":
                raise HTTPException(status_code=400, detail=f"Request sudah diproses sebelumnya ({req['status']})")

            if data.status == "approved":
                if req["tipe"] == "topup":
                    cursor.execute(
                        "UPDATE investor SET saldo_tunai = saldo_tunai + %s WHERE username = %s",
                        (req["nominal"], req["username"])
                    )
                elif req["tipe"] == "withdraw":
                    cursor.execute("SELECT saldo_tunai FROM investor WHERE username = %s FOR UPDATE", (req["username"],))
                    user = cursor.fetchone()
                    if not user or user["saldo_tunai"] < req["nominal"]:
                        raise HTTPException(status_code=400, detail="Saldo user tidak mencukupi untuk withdraw ini!")
                    cursor.execute(
                        "UPDATE investor SET saldo_tunai = saldo_tunai - %s WHERE username = %s",
                        (req["nominal"], req["username"])
                    )

            cursor.execute(
                "UPDATE permintaan_dana SET status = %s, waktu_diproses = NOW() WHERE id = %s",
                (data.status, data.request_id)
            )
            # Jika semua query sukses, commit perubahan sekaligus
            conn.commit()
            return {"message": f"Request #{data.request_id} berhasil di-{data.status}."}
    except Exception as e:
        conn.rollback()  # Batalkan semua perubahan jika di tengah jalan ada error
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Terjadi kesalahan server: {str(e)}")
    finally:
        conn.close()
