# main.py - Sistem Investasi Real-Time untuk Railway (Versi Aman + CORS)
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
import random
import os
import json
import asyncio
from contextlib import asynccontextmanager

# File penyimpanan data agar tidak hilang saat Railway restart
DATA_FILE = "data_investasi.json"

# ============ SISTEM UTAMA (Class ditaruh di atas agar inisialisasi lancar) ============
class User:
    def __init__(self, username: str, saldo_tunai=1000000.0, saldo_unit=0.0):
        self.username = username
        self.saldo_tunai = saldo_tunai
        self.saldo_unit = saldo_unit

    def to_dict(self):
        return {"username": self.username, "saldo_tunai": self.saldo_tunai, "saldo_unit": self.saldo_unit}

class Transaksi:
    def __init__(self, username, jenis, jumlah_unit, harga, fee, waktu=None):
        self.username = username
        self.jenis = jenis
        self.jumlah_unit = jumlah_unit
        self.harga = harga
        self.fee = fee
        self.waktu = waktu if waktu else datetime.now()

    def to_dict(self):
        return {
            "username": self.username, "jenis": self.jenis, 
            "jumlah_unit": self.jumlah_unit, "harga": self.harga, 
            "fee": self.fee, "waktu": self.waktu.isoformat() if isinstance(self.waktu, datetime) else self.waktu
        }

class SistemInvestasi:
    def __init__(self):
        self.harga_saat_ini = 400.0
        self.riwayat_harga = [{"waktu": datetime.now().isoformat(), "harga": 400.0}]
        self.users = {}
        self.transaksi_history = []
        self.dividen_history = []
        self.fee_persen = 0.001
        self.dividen_persen = 0.02
        self.last_dividen_date = datetime.now()
        self.last_update = datetime.now()
        self.load_data()
    
    def save_data(self):
        data = {
            "harga_saat_ini": self.harga_saat_ini,
            "riwayat_harga": self.riwayat_harga,
            "users": {k: v.to_dict() for k, v in self.users.items()},
            "transaksi_history": [t.to_dict() for t in self.transaksi_history],
            "dividen_history": self.dividen_history,
            "last_dividen_date": self.last_dividen_date.isoformat() if isinstance(self.last_dividen_date, datetime) else self.last_dividen_date,
            "last_update": self.last_update.isoformat() if isinstance(self.last_update, datetime) else self.last_update
        }
        with open(DATA_FILE, "w") as f:
            json.dump(data, f, indent=4)

    def load_data(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r") as f:
                    data = json.load(f)
                self.harga_saat_ini = data.get("harga_saat_ini", 400.0)
                self.riwayat_harga = data.get("riwayat_harga", [])
                self.dividen_history = data.get("dividen_history", [])
                self.transaksi_history = [Transaksi(**t) for t in data.get("transaksi_history", [])]
                
                for k, v in data.get("users", {}).items():
                    self.users[k] = User(v["username"], v["saldo_tunai"], v["saldo_unit"])
                    
                try:
                    self.last_dividen_date = datetime.fromisoformat(data["last_dividen_date"])
                    self.last_update = datetime.fromisoformat(data["last_update"])
                except:
                    self.last_dividen_date = datetime.now()
                    self.last_update = datetime.now()
            except Exception as e:
                print(f"Gagal memuat data, membuat database baru: {e}")

    def update_harga(self):
        perubahan = random.uniform(-0.015, 0.015)
        self.harga_saat_ini *= (1 + perubahan)
        self.harga_saat_ini = max(100, min(2000, self.harga_saat_ini))
        self.harga_saat_ini = round(self.harga_saat_ini, 2)
        
        self.riwayat_harga.append({
            "waktu": datetime.now().isoformat(), 
            "harga": self.harga_saat_ini
        })
        if len(self.riwayat_harga) > 100:
            self.riwayat_harga = self.riwayat_harga[-100:]
        
        self.last_update = datetime.now()
        self.cek_dividen()
        self.save_data()
        return self.harga_saat_ini
    
    def cek_dividen(self):
        hari_berlalu = (datetime.now() - self.last_dividen_date).days
        if hari_berlalu >= 30:
            for user in self.users.values():
                nilai_portofolio = user.saldo_unit * self.harga_saat_ini
                dividen = nilai_portofolio * self.dividen_persen
                user.saldo_tunai += dividen
                self.dividen_history.append({
                    "username": user.username,
                    "dividen": round(dividen, 2),
                    "periode": self.last_dividen_date.strftime('%Y-%m'),
                    "waktu": datetime.now().isoformat()
                })
            self.last_dividen_date = datetime.now()
            self.save_data()
    
    def register_user(self, username: str):
        if username not in self.users:
            self.users[username] = User(username)
            self.save_data()
            return True
        return False
    
    def beli(self, username: str, jumlah_unit: float):
        user = self.users.get(username)
        if not user:
            raise HTTPException(404, "User tidak ditemukan")
        
        total_biaya = jumlah_unit * self.harga_saat_ini
        fee = total_biaya * self.fee_persen
        total_dengan_fee = total_biaya + fee
        
        if user.saldo_tunai >= total_dengan_fee:
            user.saldo_tunai -= total_dengan_fee
            user.saldo_unit += jumlah_unit
            
            self.transaksi_history.append(Transaksi(
                username, "beli", jumlah_unit, self.harga_saat_ini, fee
            ))
            self.save_data()
            
            return {
                "status": "sukses", "jumlah_unit": jumlah_unit, "harga": self.harga_saat_ini,
                "total": round(total_biaya, 2), "fee": round(fee, 2), "total_bayar": round(total_dengan_fee, 2),
                "saldo_tunai": round(user.saldo_tunai, 2), "saldo_unit": user.saldo_unit
            }
        raise HTTPException(400, "Saldo tidak cukup")
    
    def jual(self, username: str, jumlah_unit: float):
        user = self.users.get(username)
        if not user:
            raise HTTPException(404, "User tidak ditemukan")
        if user.saldo_unit < jumlah_unit:
            raise HTTPException(400, "Unit tidak cukup")
        
        total_hasil = jumlah_unit * self.harga_saat_ini
        fee = total_hasil * self.fee_persen
        total_diterima = total_hasil - fee
        
        user.saldo_unit -= jumlah_unit
        user.saldo_tunai += total_diterima
        
        self.transaksi_history.append(Transaksi(
            username, "jual", jumlah_unit, self.harga_saat_ini, fee
        ))
        self.save_data()
        
        return {
            "status": "sukses", "jumlah_unit": jumlah_unit, "harga": self.harga_saat_ini,
            "total": round(total_hasil, 2), "fee": round(fee, 2), "total_diterima": round(total_diterima, 2),
            "saldo_tunai": round(user.saldo_tunai, 2), "saldo_unit": user.saldo_unit
        }
    
    def get_portofolio(self, username: str):
        user = self.users.get(username)
        if not user:
            raise HTTPException(404, "User tidak ditemukan")
        
        nilai_unit = user.saldo_unit * self.harga_saat_ini
        total_kekayaan = user.saldo_tunai + nilai_unit
        user_dividen = [d for d in self.dividen_history if d["username"] == username]
        total_dividen = sum(d["dividen"] for d in user_dividen)
        
        return {
            "username": username, "saldo_tunai": round(user.saldo_tunai, 2), "saldo_unit": user.saldo_unit,
            "harga_saat_ini": self.harga_saat_ini, "nilai_unit": round(nilai_unit, 2),
            "total_kekayaan": round(total_kekayaan, 2), "total_dividen": round(total_dividen, 2),
            "riwayat_dividen": user_dividen
        }

# ============ INISIALISASI & CORS SETUP ============
sistem = SistemInvestasi()
app = FastAPI(title="Sistem Investasi Real-Time")

# Konfigurasi CORS agar index.html dari luar bisa nembak ke Railway kamu
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def background_updater():
    while True:
        await asyncio.sleep(4 * 3600)
        harga_baru = sistem.update_harga()
        print(f"Harga otomatis terupdate: Rp{harga_baru}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(background_updater())
    print("✅ Sistem investasi berjalan dengan auto-save JSON & CORS Aktif")
    yield

app.router.lifespan_context = lifespan

# ============ API ENDPOINTS ============
class TransaksiRequest(BaseModel):
    username: str
    jumlah_unit: float

class RegisterRequest(BaseModel):
    username: str

@app.get("/")
def root():
    return {
        "message": "Sistem Investasi Real-Time", "status": "running", "harga_saat_ini": sistem.harga_saat_ini,
        "last_update": sistem.last_update.isoformat() if isinstance(sistem.last_update, datetime) else sistem.last_update,
        "endpoints": ["/register", "/harga", "/beli", "/jual", "/portofolio/{username}", "/dashboard"]
    }

@app.post("/register")
def register_user(req: RegisterRequest):
    if sistem.register_user(req.username):
        return {"message": f"User {req.username} berhasil didaftarkan", "saldo_awal": 1000000}
    raise HTTPException(400, "Username sudah ada")

@app.get("/harga")
def get_harga():
    return {
        "harga_saat_ini": sistem.harga_saat_ini,
        "last_update": sistem.last_update.isoformat() if isinstance(sistem.last_update, datetime) else sistem.last_update,
        "riwayat_harga": sistem.riwayat_harga[-30:]
    }

@app.post("/beli")
def beli_unit(req: TransaksiRequest):
    return sistem.beli(req.username, req.jumlah_unit)

@app.post("/jual")
def jual_unit(req: TransaksiRequest):
    return sistem.jual(req.username, req.jumlah_unit)

@app.get("/portofolio/{username}")
def get_portofolio(username: str):
    return sistem.get_portofolio(username)

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    return "<h1>API Server Aktif</h1><p>Gunakan file index.html eksternal kamu untuk mengakses UI grafis.</p>"
