# main.py - Sistem Investasi Real-Time untuk Railway (Versi Aman)
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from datetime import datetime
import random
import os
import json
import asyncio
from contextlib import asynccontextmanager

app = FastAPI(title="Sistem Investasi Real-Time")

# File penyimpanan data agar tidak hilang saat Railway restart
DATA_FILE = "data_investasi.json"

# ============ DATA MODEL ============
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

# ============ SISTEM UTAMA ============
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
        self.load_data() # Load data lama saat aplikasi dinyalakan
    
    def save_data(self):
        """Menyimpan seluruh state sistem ke file JSON"""
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
        """Membaca data dari file JSON jika ada"""
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
                print(f"Gagal memuat data lama, membuat database baru. Error: {e}")

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
        self.save_data() # Simpan perubahan harga
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
                "status": "sukses",
                "jumlah_unit": jumlah_unit,
                "harga": self.harga_saat_ini,
                "total": round(total_biaya, 2),
                "fee": round(fee, 2),
                "total_bayar": round(total_dengan_fee, 2),
                "saldo_tunai": round(user.saldo_tunai, 2),
                "saldo_unit": user.saldo_unit
            }
        else:
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
            "status": "sukses",
            "jumlah_unit": jumlah_unit,
            "harga": self.harga_saat_ini,
            "total": round(total_hasil, 2),
            "fee": round(fee, 2),
            "total_diterima": round(total_diterima, 2),
            "saldo_tunai": round(user.saldo_tunai, 2),
            "saldo_unit": user.saldo_unit
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
            "username": username,
            "saldo_tunai": round(user.saldo_tunai, 2),
            "saldo_unit": user.saldo_unit,
            "harga_saat_ini": self.harga_saat_ini,
            "nilai_unit": round(nilai_unit, 2),
            "total_kekayaan": round(total_kekayaan, 2),
            "total_dividen": round(total_dividen, 2),
            "riwayat_dividen": user_dividen
        }

# ============ INISIALISASI ============
sistem = SistemInvestasi()

async def background_updater():
    while True:
        await asyncio.sleep(4 * 3600)  # Loop otomatis per 4 jam
        harga_baru = sistem.update_harga()
        print(f"Harga otomatis terupdate: Rp{harga_baru}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(background_updater())
    print("✅ Sistem investasi berjalan dengan auto-save JSON")
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
        "message": "Sistem Investasi Real-Time",
        "status": "running",
        "harga_saat_ini": sistem.harga_saat_ini,
        "last_update": sistem.last_update.isoformat() if isinstance(sistem.last_update, datetime) else sistem.last_update,
        "endpoints": {
            "register": "POST /register",
            "harga": "GET /harga",
            "beli": "POST /beli",
            "jual": "POST /jual",
            "portofolio": "GET /portofolio/{username}",
            "dashboard": "GET /dashboard"
        }
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
        "next_update_in_hours": 4,
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
    # Menggunakan dashboard HTML bawaan kamu yang sudah keren
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Sistem Investasi Real-Time</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; padding: 20px; }
            .container { max-width: 1200px; margin: auto; background: white; border-radius: 20px; padding: 30px; box-shadow: 0 20px 60px rgba(0,0,0,0.3); }
            h1 { color: #333; margin-bottom: 10px; }
            .subtitle { color: #666; margin-bottom: 30px; border-bottom: 2px solid #667eea; padding-bottom: 10px; }
            .info-bar { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 15px; margin-bottom: 30px; display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; }
            .info-item { text-align: center; }
            .info-item .label { font-size: 14px; opacity: 0.9; }
            .info-item .value { font-size: 28px; font-weight: bold; margin-top: 5px; }
            .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 20px; margin-bottom: 30px; }
            .card { background: #f8f9fa; border-radius: 15px; padding: 20px; border: 1px solid #e0e0e0; }
            .card h3 { margin-bottom: 15px; color: #333; }
            input, button { width: 100%; padding: 12px; margin: 8px 0; border-radius: 8px; border: 1px solid #ddd; font-size: 14px; }
            button { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; cursor: pointer; font-weight: bold; transition: transform 0.2s; }
            button:hover { transform: translateY(-2px); }
            .result { background: white; border-radius: 8px; padding: 10px; margin-top: 10px; font-size: 12px; overflow-x: auto; }
            canvas { max-height: 300px; margin-top: 20px; }
            .profit { color: #10b981; font-weight: bold; }
            @media (max-width: 768px) { .container { padding: 15px; } .grid { grid-template-columns: 1fr; } }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📈 Sistem Investasi Real-Time</h1>
            <div class="subtitle">Pergerakan harga setiap 4 jam | Fee 0.1% | Dividen 2% per bulan</div>
            
            <div class="info-bar" id="infoBar">
                <div class="info-item"><div class="label">💰 Harga Saat Ini</div><div class="value" id="hargaValue">Rp --</div></div>
                <div class="info-item"><div class="label">⏰ Last Update</div><div class="value" id="lastUpdate">--</div></div>
                <div class="info-item"><div class="label">🔄 Next Update</div><div class="value" id="nextUpdate">4 jam</div></div>
            </div>
            
            <div class="grid">
                <div class="card">
                    <h3>👤 Registrasi</h3>
                    <input type="text" id="regUser" placeholder="Username">
                    <button onclick="register()">Daftar Akun</button>
                    <div id="regResult" class="result"></div>
                </div>
                
                <div class="card">
                    <h3>🛒 Beli Unit</h3>
                    <input type="text" id="buyUser" placeholder="Username">
                    <input type="number" id="buyJumlah" placeholder="Jumlah unit" step="0.1">
                    <button onclick="beli()">Beli</button>
                    <div id="buyResult" class="result"></div>
                </div>
                
                <div class="card">
                    <h3>💰 Jual Unit</h3>
                    <input type="text" id="sellUser" placeholder="Username">
                    <input type="number" id="sellJumlah" placeholder="Jumlah unit" step="0.1">
                    <button onclick="jual()">Jual</button>
                    <div id="sellResult" class="result"></div>
                </div>
                
                <div class="card">
                    <h3>📊 Portofolio</h3>
                    <input type="text" id="portUser" placeholder="Username">
                    <button onclick="lihatPortofolio()">Lihat Portofolio</button>
                    <div id="portResult" class="result"></div>
                </div>
            </div>
            
            <div class="card">
                <h3>📈 Grafik Pergerakan Harga (30 terakhir)</h3>
                <canvas id="hargaChart"></canvas>
                <p style="margin-top: 10px; font-size: 12px; color: #666;">*Harga otomatis tersimpan dengan aman di persistent disk Railway.</p>
            </div>
        </div>
        
        <script>
            let chart;
            async function register() {
                const user = document.getElementById('regUser').value;
                if(!user) return alert('Masukkan username');
                const res = await fetch('/register', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({username: user})
                });
                const data = await res.json();
                document.getElementById('regResult').innerHTML = '<pre>' + JSON.stringify(data, null, 2) + '</pre>';
            }
            
            async function loadHarga() {
                const res = await fetch('/harga');
                const data = await res.json();
                document.getElementById('hargaValue').innerHTML = 'Rp ' + data.harga_saat_ini.toLocaleString();
                document.getElementById('lastUpdate').innerHTML = new Date(data.last_update).toLocaleTimeString();
                
                const labels = data.riwayat_harga.map(h => new Date(h.waktu).toLocaleTimeString());
                const prices = data.riwayat_harga.map(h => h.harga);
                
                if (chart) chart.destroy();
                const ctx = document.getElementById('hargaChart').getContext('2d');
                chart = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: labels,
                        datasets: [{
                            label: 'Harga per Unit (Rp)',
                            data: prices,
                            borderColor: '#667eea',
                            backgroundColor: 'rgba(102, 126, 234, 0.1)',
                            tension: 0.4,
                            fill: true
                        }]
                    }
                });
            }
            
            async function beli() {
                const user = document.getElementById('buyUser').value;
                const jumlah = parseFloat(document.getElementById('buyJumlah').value);
                const res = await fetch('/beli', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({username: user, jumlah_unit: jumlah})
                });
                const data = await res.json();
                document.getElementById('buyResult').innerHTML = '<pre>' + JSON.stringify(data, null, 2) + '</pre>';
                loadHarga();
            }
            
            async function jual() {
                const user = document.getElementById('sellUser').value;
                const jumlah = parseFloat(document.getElementById('sellJumlah').value);
                const res = await fetch('/jual', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({username: user, jumlah_unit: jumlah})
                });
                const data = await res.json();
                document.getElementById('sellResult').innerHTML = '<pre>' + JSON.stringify(data, null, 2) + '</pre>';
                loadHarga();
            }
            
            async function lihatPortofolio() {
                const user = document.getElementById('portUser').value;
                const res = await fetch('/portofolio/' + user);
                const data = await res.json();
                document.getElementById('portResult').innerHTML = '<pre>' + JSON.stringify(data, null, 2) + '</pre>';
            }
            loadHarga();
            setInterval(loadHarga, 10000);
        </script>
    </body>
    </html>
    """
