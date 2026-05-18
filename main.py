from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Dict, List, Optional
from datetime import datetime
from contextlib import asynccontextmanager
import random
import asyncio
import os

# ============ DATA MODEL ============
class User(BaseModel):
    username: str
    saldo_tunai: float = 1000000
    saldo_unit: float = 0

class SistemInvestasi:
    def __init__(self):
        self.harga_saat_ini = 400.0
        self.riwayat_harga = [{"waktu": datetime.now(), "harga": 400.0}]
        self.users: Dict[str, User] = {}
        self.fee_persen = 0.001
        
    def update_harga(self):
        perubahan = random.uniform(-0.015, 0.015)
        self.harga_saat_ini *= (1 + perubahan)
        self.harga_saat_ini = max(100, min(2000, self.harga_saat_ini))
        self.harga_saat_ini = round(self.harga_saat_ini, 2)
        self.riwayat_harga.append({"waktu": datetime.now(), "harga": self.harga_saat_ini})
        if len(self.riwayat_harga) > 100:
            self.riwayat_harga = self.riwayat_harga[-100:]
        return self.harga_saat_ini
    
    def register_user(self, username: str):
        if username not in self.users:
            self.users[username] = User(username=username)
            return True
        return False

# ============ INISIALISASI ============
sistem = SistemInvestasi()

# Background task untuk update harga
async def background_updater():
    """Update harga setiap 4 jam"""
    while True:
        await asyncio.sleep(4 * 3600)
        harga_baru = sistem.update_harga()
        print(f"[{datetime.now()}] Harga update: Rp{harga_baru}")

# ============ LIFESPAN ============
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    task = asyncio.create_task(background_updater())
    print("✅ Sistem investasi berjalan")
    yield
    # Shutdown
    task.cancel()
    print("🛑 Sistem dimatikan")

# ============ APP ============
app = FastAPI(
    title="Sistem Investasi Real-Time",
    lifespan=lifespan
)

# ============ API ENDPOINTS ============
@app.get("/")
def root():
    return {"message": "Sistem Investasi Berjalan", "harga": sistem.harga_saat_ini}

@app.get("/harga")
def get_harga():
    return {"harga_saat_ini": sistem.harga_saat_ini}

@app.post("/register")
def register_user(username: str):
    if sistem.register_user(username):
        return {"message": f"User {username} berhasil didaftarkan"}
    return {"error": "Username sudah ada"}

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Sistem Investasi</title>
        <style>
            body { font-family: Arial; margin: 20px; background: #f0f2f5; }
            .container { max-width: 800px; margin: auto; background: white; padding: 20px; border-radius: 10px; }
            .harga { font-size: 48px; color: #667eea; text-align: center; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📈 Sistem Investasi Real-Time</h1>
            <div class="harga" id="harga">Loading...</div>
            <button onclick="refresh()">Refresh Harga</button>
        </div>
        <script>
            async function refresh() {
                const res = await fetch('/harga');
                const data = await res.json();
                document.getElementById('harga').innerHTML = `Rp ${data.harga_saat_ini.toLocaleString()}`;
            }
            refresh();
            setInterval(refresh, 30000);
        </script>
    </body>
    </html>
    """

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
