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
    """Membuat tabel jika belum ada dan memastikan harga awal diset ke Rp100"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Tabel Akun & Saldo Investor
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS investor (
                    username VARCHAR(50) PRIMARY KEY,
                    password_hash VARCHAR(255) NOT NULL,
                    saldo_tunai DOUBLE NOT NULL DEFAULT 0.0,
                    saldo_unit DOUBLE NOT NULL DEFAULT 0.0
                )
            """)
            
            # Tabel Histori Pergerakan Harga
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS histori_harga (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    harga DOUBLE NOT NULL,
                    waktu TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Cek apakah sudah ada data harga. Jika kosong, inject harga awal Rp100
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
    await loop.run_in_executor(None, init_db)
    yield

app = FastAPI(lifespan=lifespan)

# Bypass keamanan CORS agar komunikasi internal API lancar
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

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

# ==========================================
# 3. INTERFACE FRONTEND ENDPOINT (ROOT GUI)
# ==========================================
@app.get("/", response_class=HTMLResponse)
def read_root_frontend():
    # Menyisipkan antarmuka aplikasi mobile langsung dari memori backend
    html_content = """
    <!DOCTYPE html>
    <html lang="id">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <title>MarketsHub Mobile Pro</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
            body { 
                background-color: #f8fafc; color: #0f172a; min-height: 100vh; padding-bottom: 80px; 
                -webkit-tap-highlight-color: transparent; overflow-x: hidden;
            }
            .container { width: 100%; padding: 16px; }
            header {
                display: flex; justify-content: space-between; align-items: center;
                padding: 16px; background: #ffffff; border-bottom: 1px solid #e2e8f0;
                position: sticky; top: 0; width: 100%; z-index: 90;
            }
            .brand { font-size: 1.2rem; font-weight: 800; color: #10b981; }
            .logout-link { color: #ef4444; font-size: 13px; font-weight: 600; cursor: pointer; }
            .bottom-nav {
                position: fixed; bottom: 0; left: 0; right: 0; height: 64px;
                background: #ffffff; border-top: 1px solid #e2e8f0;
                display: flex; justify-content: space-around; align-items: center;
                z-index: 100; box-shadow: 0 -4px 10px rgba(0,0,0,0.03);
            }
            .nav-item {
                display: flex; flex-direction: column; align-items: center; justify-content: center;
                background: none; border: none; color: #94a3b8; font-size: 11px; font-weight: 600;
                cursor: pointer; width: 100%; height: 100%; padding: 0; margin: 0;
            }
            .nav-item.active { color: #10b981; }
            .nav-item-icon { font-size: 20px; margin-bottom: 2px; }
            .page { display: none; animation: fadeIn 0.3s ease; }
            .page.active { display: block; }
            @keyframes fadeIn { from { opacity: 0; transform: translateY(5px); } to { opacity: 1; transform: translateY(0); } }
            .auth-card {
                background: #ffffff; border-radius: 20px; padding: 24px;
                border: 1px solid #e2e8f0; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.02);
                margin-top: 40px; text-align: center;
            }
            .auth-card h2 { font-size: 1.5rem; font-weight: 800; margin-bottom: 6px; }
            .auth-card p { color: #64748b; font-size: 13px; margin-bottom: 24px; }
            .balance-card {
                background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
                border-radius: 16px; padding: 20px; color: #ffffff; margin-bottom: 16px;
            }
            .balance-label { font-size: 11px; text-transform: uppercase; color: #94a3b8; letter-spacing: 0.5px; font-weight: 700; }
            .balance-main { font-size: 26px; font-weight: 800; margin: 4px 0 12px 0; letter-spacing: -0.5px; }
            .balance-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; border-top: 1px solid #334155; padding-top: 12px; }
            .sub-balance-val { font-size: 14px; font-weight: 700; color: #f8fafc; margin-top: 2px; }
            .market-badge-card {
                background: #ffffff; border-radius: 14px; padding: 14px 16px;
                border: 1px solid #e2e8f0; display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;
            }
            .price-up { color: #10b981; font-weight: 800; font-size: 18px; }
            input, select, button { width: 100%; height: 48px; border-radius: 12px; font-size: 14px; font-weight: 600; transition: all 0.2s; -webkit-appearance: none; }
            input, select { background: #f1f5f9; border: 1px solid #e2e8f0; color: #0f172a; padding: 0 16px; margin-bottom: 12px; }
            input:focus, select:focus { outline: none; border-color: #10b981; background: #ffffff; }
            button { background: #10b981; color: white; border: none; cursor: pointer; display: flex; align-items: center; justify-content: center; }
            button:active { transform: scale(0.98); background: #059669; }
            button.secondary { background: #f1f5f9; color: #334155; border: 1px solid #e2e8f0; }
            button.secondary:active { background: #e2e8f0; }
            button.danger { background: #ef4444; }
            button.danger:active { background: #dc2626; }
            .status-banner { padding: 12px; border-radius: 10px; font-size: 12px; font-weight: 600; margin-top: 8px; display: none; }
            .status-banner.success { background: #f0fdf4; border: 1px solid #bbf7d0; color: #16a34a; }
            .status-banner.error { background: #fef2f2; border: 1px solid #fca5a5; color: #dc2626; }
            .chart-card { background: #ffffff; border-radius: 16px; border: 1px solid #e2e8f0; padding: 16px; margin-bottom: 16px; }
            .chart-card h3 { font-size: 14px; font-weight: 700; color: #64748b; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.5px;}
            .chart-wrapper { position: relative; width: 100%; height: 220px; }
            .action-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 4px; }
            .mobile-modal {
                position: fixed; top: 0; bottom: 0; left: 0; right: 0;
                background: rgba(15, 23, 42, 0.4); backdrop-filter: blur(4px);
                z-index: 200; display: none; align-items: flex-end;
            }
            .modal-content {
                background: #ffffff; border-top-left-radius: 24px; border-top-right-radius: 24px;
                width: 100%; padding: 24px 20px; animation: slideUp 0.25s ease-out;
            }
            @keyframes slideUp { from { transform: translateY(100%); } to { transform: translateY(0); } }
            .modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
            .modal-header h3 { font-size: 16px; font-weight: 800; }
            .close-btn { font-size: 20px; color: #94a3b8; cursor: pointer; font-weight: bold; }
            .list-item { display: flex; justify-content: space-between; padding: 14px 0; border-bottom: 1px solid #f1f5f9; font-size: 14px; }
            .list-item:last-child { border-bottom: none; }
            .list-label { color: #64748b; }
            .list-val { font-weight: 700; }
            .auth-link { color: #10b981; font-weight: bold; cursor: pointer; text-decoration: underline; }
        </style>
    </head>
    <body>
        <header id="mainHeader" style="display: none;">
            <div class="brand" id="headerTitle">MarketsHub</div>
            <div class="logout-link" onclick="handleLogout()">Keluar</div>
        </header>

        <div class="container">
            <div id="pageLogin" class="page active">
                <div class="auth-card">
                    <h2>Masuk Akun</h2>
                    <p>Akses portal investor & pengelolaan admin mandiri</p>
                    <input type="text" id="loginUser" placeholder="Username (Ketik 'admin' untuk Master)">
                    <input type="password" id="loginPass" placeholder="Password Akun">
                    <button onclick="handleLogin()">Masuk Aman</button>
                    <div style="margin-top: 20px; font-size: 13px; color: #64748b;">
                        Belum punya rekening? <span class="auth-link" onclick="navigateTo('pageRegister')">Daftar Akun</span>
                    </div>
                    <div id="loginStatus" class="status-banner error"></div>
                </div>
            </div>

            <div id="pageRegister" class="page">
                <div class="auth-card">
                    <h2>Buka Rekening</h2>
                    <p>Buat identitas investasimu secara instan</p>
                    <input type="text" id="regUser" placeholder="Buat Username Baru">
                    <input type="password" id="regPass" placeholder="Password (Min 6 Karakter)">
                    <button onclick="handleRegister()">Konfirmasi Registrasi</button>
                    <div style="margin-top: 20px; font-size: 13px; color: #64748b;">
                        Sudah memiliki akun? <span class="auth-link" onclick="navigateTo('pageLogin')">Login Ke Sistem</span>
                    </div>
                    <div id="regStatus" class="status-banner"></div>
                </div>
            </div>

            <div id="tabPasar" class="tab-content page">
                <div class="balance-card">
                    <div class="balance-label">Total Nilai Portofolio (Net Worth)</div>
                    <div class="balance-main" id="topKekayaan">Rp 0</div>
                    <div class="balance-grid">
                        <div>
                            <div class="balance-label">Kas Tunai (Cash)</div>
                            <div class="sub-balance-val" id="topTunai">Rp 0</div>
                        </div>
                        <div>
                            <div class="balance-label">Valuasi Unit</div>
                            <div class="sub-balance-val" id="topInvestasi">Rp 0</div>
                        </div>
                    </div>
                </div>

                <div class="market-badge-card">
                    <div>
                        <div class="balance-label" style="color:#64748b">Harga Efek Saat Ini</div>
                        <div style="font-size:11px; color:#94a3b8" id="topLastUpdate">--:--:--</div>
                    </div>
                    <div class="price-up" id="topHarga">Rp 100</div>
                </div>

                <div class="chart-card">
                    <h3>Tren Volumetrik Aset</h3>
                    <div class="chart-wrapper">
                        <canvas id="hargaChart"></canvas>
                    </div>
                </div>

                <div class="action-grid">
                    <button onclick="openModal('modalBeli')">▲ ORDER BUY</button>
                    <button class="secondary" onclick="openModal('modalJual')">▼ ORDER SELL</button>
                </div>
            </div>

            <div id="tabPorto" class="tab-content page">
                <div class="chart-card">
                    <h3 style="margin-bottom:8px;">Statistik Rekening</h3>
                    <div class="list-item"><span class="list-label">ID Investor</span><span class="list-val" id="lblUser">--</span></div>
                    <div class="list-item"><span class="list-label">Saldo Kas Tunai</span><span class="list-val" id="lblTunai">Rp 0</span></div>
                    <div class="list-item"><span class="list-label">Kepemilikan Efek</span><span class="list-val" style="color:#10b981" id="lblUnit">0 Unit</span></div>
                    <div class="list-item"><span class="list-label">Valuasi Konversi</span><span class="list-val" id="lblInvestasi">Rp 0</span></div>
                    <div class="list-item" style="border-top:1px dashed #e2e8f0; margin-top:8px; padding-top:14px;">
                        <span class="list-label" style="font-weight:bold; color:#0f172a">Total Akumulasi Bersih</span>
                        <span class="list-val" style="color:#10b981; font-size:16px" id="lblTotal">Rp 0</span>
                    </div>
                </div>
            </div>

            <div id="tabAdmin" class="tab-content page">
                <div class="chart-card">
                    <h3 style="color:#ef4444; margin-bottom:14px;">Otoritas Kas Investor (Deposit / WD)</h3>
                    <input type="text" id="admTargetUser" placeholder="Username Investor Target">
                    <select id="admAksiTipe">
                        <option value="deposit">DEPOSIT (Tambah Saldo Kas)</option>
                        <option value="withdrawal">WITHDRAWAL (Tarik/Potong Saldo Kas)</option>
                    </select>
                    <input type="number" id="admNominal" placeholder="Nominal Dana (IDR)">
                    <button class="danger" onclick="handleAdminAction()">Eksekusi Perubahan Kas</button>
                    <div id="adminStatus" class="status-banner"></div>
                </div>
            </div>
        </div>

        <div class="bottom-nav" id="mainNavbar" style="display: none;">
            <button class="nav-item active" id="btnNavPasar" onclick="switchTab('pasar')">
                <div class="nav-item-icon">📈</div><div>Pasar</div>
            </button>
            <button class="nav-item" id="btnNavPorto" onclick="switchTab('porto')">
                <div class="nav-item-icon">💼</div><div>Portofolio</div>
            </button>
        </div>

        <div id="modalBeli" class="mobile-modal" onclick="closeModalOnOutsideClick(event, 'modalBeli')">
            <div class="modal-content">
                <div class="modal-header">
                    <h3>Eksekusi Order Pembelian</h3>
                    <span class="close-btn" onclick="closeModal('modalBeli')">✕</span>
                </div>
                <input type="number" id="buyJumlah" placeholder="Masukkan jumlah unit (Ex: 10)">
                <button onclick="handleBeli()">Konfirmasi Pembelian</button>
                <div id="buyStatus" class="status-banner"></div>
            </div>
        </div>

        <div id="modalJual" class="mobile-modal" onclick="closeClick(event, 'modalJual')">
            <div class="modal-content">
                <div class="modal-header">
                    <h3>Eksekusi Order Penjualan</h3>
                    <span class="close-btn" onclick="closeModal('modalJual')">✕</span>
                </div>
                <input type="number" id="sellJumlah" placeholder="Masukkan jumlah unit (Ex: 5)">
                <button class="secondary" style="background:#0f172a; color:#fff" onclick="handleJual()">Konfirmasi Penjualan</button>
                <div id="sellStatus" class="status-banner"></div>
            </div>
        </div>

        <script>
            // Kosongkan string karena Frontend & Backend sekarang bersatu di URL domain yang sama!
            const API_BASE_URL = window.location.origin;
            let currentUser = localStorage.getItem("investor_username") || "";
            let adminTokenUsed = ""; let chart;

            function toRp(val) { return 'Rp ' + Number(val).toLocaleString('id-ID', {maximumFractionDigits: 2}); }
            window.onload = function() { if(currentUser) { setupSessionVisibility(); } else { navigateTo('pageLogin'); } };
            
            function navigateTo(pageId) {
                document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
                document.getElementById('mainHeader').style.display = 'none';
                document.getElementById('mainNavbar').style.display = 'none';
                if(document.getElementById(pageId)) document.getElementById(pageId).classList.add('active');
            }

            function setupSessionVisibility() {
                document.getElementById('mainHeader').style.display = 'flex';
                if (currentUser === "admin") {
                    document.getElementById('headerTitle').innerText = "Hub Master";
                    navigateTo('tabAdmin');
                } else {
                    document.getElementById('headerTitle').innerText = "MarketsHub";
                    document.getElementById('mainNavbar').style.display = 'flex';
                    switchTab('pasar');
                }
            }

            function switchTab(tabName) {
                document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
                document.getElementById('btnNavPasar').classList.remove('active');
                document.getElementById('btnNavPorto').classList.remove('active');
                if(tabName === 'pasar') {
                    document.getElementById('tabPasar').classList.add('active');
                    document.getElementById('btnNavPasar').classList.add('active');
                } else {
                    document.getElementById('tabPorto').classList.add('active');
                    document.getElementById('btnNavPorto').classList.add('active');
                }
                loadFinancialData();
            }

            function openModal(id) { document.getElementById(id).style.display = 'flex'; }
            function closeModal(id) { document.getElementById(id).style.display = 'none'; }
            function closeModalOnOutsideClick(e, id) { if(e.target.id === id) closeModal(id); }

            async function loadFinancialData() {
                if (!currentUser || currentUser === "admin") return;
                try {
                    const portoRes = await fetch(`${API_BASE_URL}/portofolio/${currentUser}`);
                    const uData = await portoRes.json();
                    const hargaRes = await fetch(`${API_BASE_URL}/harga`);
                    const hData = await hargaRes.json();

                    document.getElementById('topHarga').innerText = toRp(hData.harga_saat_ini);
                    document.getElementById('topLastUpdate').innerText = "Update: " + hData.last_update;
                    document.getElementById('topInvestasi').innerText = toRp(uData.nilai_unit);
                    document.getElementById('topKekayaan').innerText = toRp(uData.total_kekayaan);
                    document.getElementById('topTunai').innerText = toRp(uData.saldo_tunai);

                    document.getElementById('lblUser').innerText = uData.username;
                    document.getElementById('lblTunai').innerText = toRp(uData.saldo_tunai);
                    document.getElementById('lblUnit').innerText = uData.saldo_unit + " Unit";
                    document.getElementById('lblInvestasi').innerText = toRp(uData.nilai_unit);
                    document.getElementById('lblTotal').innerText = toRp(uData.total_kekayaan);

                    const labels = hData.riwayat_harga.map(h => h.waktu);
                    const prices = hData.riwayat_harga.map(h => h.harga);
                    if (chart) chart.destroy();
                    chart = new Chart(document.getElementById('hargaChart').getContext('2d'), {
                        type: 'line',
                        data: {
                            labels: labels,
                            datasets: [{ data: prices, borderColor: '#10b981', backgroundColor: 'rgba(16, 185, 129, 0.01)', borderWidth: 2, tension: 0.1, fill: true, pointRadius: 0 }]
                        },
                        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } } }
                    });
                } catch (err) { console.log("Sync error"); }
            }

            async function handleLogin() {
                const user = document.getElementById('loginUser').value.trim();
                const pass = document.getElementById('loginPass').value;
                const banner = document.getElementById('loginStatus');
                if (user.toLowerCase() === "admin") {
                    adminTokenUsed = pass; localStorage.setItem("investor_username", "admin");
                    currentUser = "admin"; setupSessionVisibility(); return;
                }
                try {
                    const res = await fetch(`${API_BASE_URL}/login`, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ username: user, password: pass }) });
                    const data = await res.json();
                    if(res.ok) {
                        localStorage.setItem("investor_username", user); currentUser = user; setupSessionVisibility();
                    } else { banner.innerText = data.detail; banner.style.display = 'block'; }
                } catch(e) { banner.innerText = "Server offline"; banner.style.display = 'block'; }
            }

            async function handleRegister() {
                const user = document.getElementById('regUser').value.trim();
                const pass = document.getElementById('regPass').value;
                const banner = document.getElementById('regStatus');
                try {
                    const res = await fetch(`${API_BASE_URL}/register`, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ username: user, password: pass }) });
                    const data = await res.json();
                    if(res.ok) { banner.className = "status-banner success"; banner.innerText = "Sukses! Silakan Login"; banner.style.display = 'block'; }
                    else { banner.className = "status-banner error"; banner.innerText = data.detail; banner.style.display = 'block'; }
                } catch(e) { banner.innerText = "Error Cloud Connection"; banner.style.display = 'block'; }
            }

            async function handleBeli() {
                const jumlah = parseFloat(document.getElementById('buyJumlah').value);
                const banner = document.getElementById('buyStatus');
                try {
                    const res = await fetch(`${API_BASE_URL}/beli`, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({username: currentUser, jumlah_unit: jumlah}) });
                    const data = await res.json();
                    if(res.ok) { loadFinancialData(); closeModal('modalBeli'); }
                    else { banner.innerText = data.detail; banner.style.display = 'block'; }
                } catch(e) { alert("Error"); }
            }

            async function handleJual() {
                const jumlah = parseFloat(document.getElementById('sellJumlah').value);
                const banner = document.getElementById('sellStatus');
                try {
                    const res = await fetch(`${API_BASE_URL}/jual`, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({username: currentUser, jumlah_unit: jumlah}) });
                    const data = await res.json();
                    if(res.ok) { loadFinancialData(); closeModal('modalJual'); }
                    else { banner.innerText = data.detail; banner.style.display = 'block'; }
                } catch(e) { alert("Error"); }
            }

            async function handleAdminAction() {
                const targetUser = document.getElementById('admTargetUser').value.trim();
                const tipeAksi = document.getElementById('admAksiTipe').value;
                const nominalVal = parseFloat(document.getElementById('admNominal').value);
                const banner = document.getElementById('adminStatus');
                try {
                    const res = await fetch(`${API_BASE_URL}/admin/kelola-saldo`, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ username: targetUser, nominal: nominalVal, aksi: tipeAksi, admin_secret_key: adminTokenUsed }) });
                    const data = await res.json();
                    if (res.ok) { banner.className = "status-banner success"; banner.innerText = data.message; banner.style.display = 'block'; }
                    else { banner.className = "status-banner error"; banner.innerText = data.detail; banner.style.display = 'block'; }
                } catch(e) { banner.innerText = "Perintah gagal"; }
            }

            function handleLogout() { localStorage.removeItem("investor_username"); currentUser = ""; navigateTo('pageLogin'); }
            setInterval(() => { if(currentUser && currentUser !== "admin" && document.getElementById('tabPasar').classList.contains('active')) { loadFinancialData(); } }, 10000);
        </script>
    </body>
    </html>
    """
    return html_content

# ==========================================
# 4. CORE ENDPOINTS ROUTER (BACKEND API)
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
                "INSERT INTO investor (username, password_hash, saldo_tunai, saldo_unit) VALUES (%s, %s, 0.0, 0.0)",
                (data.username, p_hash)
            )
            return {"message": "Registrasi sukses!"}
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
                raise HTTPException(status_code=400, detail="Unit efek tidak mencukupi")
            
            cursor.execute("SELECT harga FROM histori_harga ORDER BY id DESC LIMIT 1 FOR UPDATE")
            harga_sekarang = cursor.fetchone()["harga"]
            
            total_pendapatan = data.jumlah_unit * harga_sekarang
            cursor.execute(
                "UPDATE investor SET saldo_tunai = saldo_tunai + %s, saldo_unit = saldo_unit - %s WHERE username = %s",
                (total_pendapatan, data.jumlah_unit, data.username)
            )
            
            harga_baru = max(1.0, harga_sekarang - (data.jumlah_unit * 0.5))
            cursor.execute("INSERT INTO histori_harga (harga) VALUES (%s)", (harga_baru,))
            return {"message": "Order sell sukses", "harga_baru": harga_baru}
    finally:
        conn.close()

@app.post("/admin/kelola-saldo")
def admin_otoritas_saldo(data: AdminControlModel):
    if data.admin_secret_key != "LibertyAdminSuperSecret2026":
        raise HTTPException(status_code=403, detail="Token admin salah.")
        
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT saldo_tunai FROM investor WHERE username = %s FOR UPDATE", (data.username,))
            user = cursor.fetchone()
            if not user: raise HTTPException(status_code=404, detail="Target tidak ditemukan")
                
            if data.aksi.lower() == "deposit":
                saldo_baru = user["saldo_tunai"] + data.nominal
                msg = f"Sukses deposit Rp{data.nominal:,} ke {data.username}"
            elif data.aksi.lower() == "withdrawal":
                if user["saldo_tunai"] < data.nominal: raise HTTPException(status_code=400, detail="Saldo tidak cukup")
                saldo_baru = user["saldo_tunai"] - data.nominal
                msg = f"Sukses potong dana Rp{data.nominal:,} dari {data.username}"
            else:
                raise HTTPException(status_code=400, detail="Aksi salah")
                
            cursor.execute("UPDATE investor SET saldo_tunai = %s WHERE username = %s", (saldo_baru, data.username))
            return {"status": "success", "message": msg}
    finally:
        conn.close()
