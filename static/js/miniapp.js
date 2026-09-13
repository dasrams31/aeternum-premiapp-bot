// ==============================================================================
// Aeternum PremiApp Telegram Mini App (TMA) Client Logic
// ==============================================================================

const tg = window.Telegram?.WebApp;
const ADMIN_ID = 606533609;

let currentUser = {
    id: 606533609,
    first_name: "Admin",
    username: "dasrams",
    balance: 0,
    referral_balance: 0,
    is_admin: false,
};

let allProducts = [];
let allCategories = [];
let selectedProduct = null;
let currentDiscount = 0;
let currentPromoCode = null;

// 1. Inisialisasi Telegram WebApp
document.addEventListener("DOMContentLoaded", () => {
    if (tg) {
        tg.ready();
        tg.expand();
        tg.setHeaderColor?.('#0f172a');
        tg.setBackgroundColor?.('#0b0f19');

        const tgUser = tg.initDataUnsafe?.user;
        if (tgUser) {
            currentUser.id = tgUser.id;
            currentUser.first_name = tgUser.first_name || "Pengguna";
            currentUser.username = tgUser.username || "";
        }
    }

    currentUser.is_admin = currentUser.id === ADMIN_ID;

    // Render User Header
    document.getElementById("user-name").textContent = currentUser.first_name;
    document.getElementById("user-avatar-initial").textContent = currentUser.first_name.charAt(0).toUpperCase();

    if (currentUser.is_admin) {
        document.getElementById("admin-badge").classList.remove("hidden");
        document.getElementById("nav-admin").classList.remove("hidden");
    }

    // Load Data Awal
    loadUserProfile();
    loadCatalog();
    lucide.createIcons();
});

// 2. Tab Navigation
function switchTab(tabId) {
    if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred("light");

    document.querySelectorAll(".tab-content").forEach(el => el.classList.add("hidden"));
    document.querySelectorAll(".nav-btn").forEach(el => {
        el.classList.remove("text-indigo-400", "active");
        el.classList.add("text-slate-400");
    });

    const targetTab = document.getElementById(`tab-r${tabId}`) || document.getElementById(`tab-${tabId}`);
    if (targetTab) targetTab.classList.remove("hidden");

    const activeNav = document.getElementById(`nav-${tabId}`);
    if (activeNav) {
        activeNav.classList.remove("text-slate-400");
        activeNav.classList.add("text-indigo-400", "active");
    }

    if (tabId === "history") loadHistory();
    if (tabId === "admin" && currentUser.is_admin) loadAdminStats();
    lucide.createIcons();
}

// 3. Load User Profile & Balances
async function loadUserProfile() {
    try {
        const res = await fetch(`/api/user/profile?user_id=${currentUser.id}`);
        const data = await res.json();
        if (data.success && data.user) {
            currentUser.balance = parseFloat(data.user.balance) || 0;
            currentUser.referral_balance = parseFloat(data.user.referral_balance) || 0;

            const fmtBal = formatRupiah(currentUser.balance);
            const fmtRef = formatRupiah(currentUser.referral_balance);

            document.getElementById("user-balance-display").textContent = fmtBal;
            document.getElementById("wallet-balance-big").textContent = fmtBal;
            document.getElementById("wallet-referral-balance").textContent = fmtRef;

            const botUsername = data.bot_username || "aeternum_premibot";
            document.getElementById("ref-link-input").value = `https://t.me/${botUsername}?start=ref_${currentUser.id}`;
        }
    } catch (e) {
        console.error("Gagal memuat profil user:", e);
    }
}

// 4. Load Catalog & Categories
async function loadCatalog() {
    try {
        const res = await fetch('/api/catalog');
        const data = await res.json();
        if (data.success) {
            allProducts = data.products || [];
            allCategories = data.categories || [];
            renderCategories(allCategories);
            renderProducts(allProducts);
        }
    } catch (e) {
        console.error("Gagal memuat katalog:", e);
    }
}

function renderCategories(categories) {
    const container = document.getElementById("category-pills");
    container.innerHTML = `
        <button onclick="filterCategory('ALL')" class="cat-pill active whitespace-nowrap px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-indigo-600 text-white shadow-sm transition-all">
            Semua Produk
        </button>
    `;

    categories.forEach(cat => {
        const btn = document.createElement("button");
        btn.onclick = () => filterCategory(cat.id);
        btn.className = "cat-pill whitespace-nowrap px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-slate-800 text-slate-300 hover:bg-slate-700 transition-all";
        btn.textContent = cat.name;
        container.appendChild(btn);
    });
}

function filterCategory(catId) {
    if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred("light");

    document.querySelectorAll(".cat-pill").forEach(el => {
        el.classList.remove("bg-indigo-600", "text-white", "active");
        el.classList.add("bg-slate-800", "text-slate-300");
    });

    event.target.classList.remove("bg-slate-800", "text-slate-300");
    event.target.classList.add("bg-indigo-600", "text-white", "active");

    if (catId === "ALL") {
        renderProducts(allProducts);
    } else {
        const filtered = allProducts.filter(p => p.category_id === parseInt(catId));
        renderProducts(filtered);
    }
}

function renderProducts(products) {
    const grid = document.getElementById("product-grid");
    if (!products.length) {
        grid.innerHTML = `<div class="col-span-2 text-center py-10 text-slate-500 text-xs">Belum ada produk aktif di kategori ini.</div>`;
        return;
    }

    grid.innerHTML = products.map(p => {
        let stockBadge = `<span class="text-[10px] text-cyan-400 font-semibold bg-cyan-500/10 px-1.5 py-0.5 rounded">⚡ Instan</span>`;
        if (p.product_type === 'TEXT_STOCK') {
            stockBadge = p.stock_count > 0 
                ? `<span class="text-[10px] text-emerald-400 font-semibold bg-emerald-500/10 px-1.5 py-0.5 rounded">🟢 Sisa ${p.stock_count}</span>`
                : `<span class="text-[10px] text-rose-400 font-semibold bg-rose-500/10 px-1.5 py-0.5 rounded">🔴 Habis</span>`;
        }

        return `
            <div onclick="openProductModal(${p.id})" class="glass rounded-2xl p-3 flex flex-col justify-between hover:border-indigo-500/40 transition-all active:scale-95 cursor-pointer">
                <div>
                    <div class="flex justify-between items-start mb-1.5">
                        <span class="text-[9px] font-bold uppercase tracking-wider text-slate-400">${p.category_name || 'DIGITAL'}</span>
                        ${stockBadge}
                    </div>
                    <h3 class="text-xs font-bold text-white line-clamp-2 leading-snug">${p.name}</h3>
                </div>
                <div class="mt-3 pt-2 border-t border-slate-800/80 flex items-center justify-between">
                    <div>
                        <span class="text-[9px] text-slate-400 block">Harga</span>
                        <span class="text-xs font-black text-indigo-300">${formatRupiah(p.price)}</span>
                    </div>
                    <div class="w-7 h-7 rounded-lg bg-indigo-600 text-white flex items-center justify-center shadow-md">
                        <i data-lucide="shopping-cart" class="w-3.5 h-3.5"></i>
                    </div>
                </div>
            </div>
        `;
    }).join("");

    lucide.createIcons();
}

// 5. Product Modal & Checkout
function openProductModal(productId) {
    if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred("medium");

    selectedProduct = allProducts.find(p => p.id === productId);
    if (!selectedProduct) return;

    currentDiscount = 0;
    currentPromoCode = null;
    document.getElementById("promo-code-input").value = "";
    document.getElementById("promo-applied-msg").classList.add("hidden");

    document.getElementById("modal-category").textContent = selectedProduct.category_name || "DIGITAL";
    document.getElementById("modal-title").textContent = selectedProduct.name;
    document.getElementById("modal-price").textContent = formatRupiah(selectedProduct.price);
    document.getElementById("modal-desc").textContent = selectedProduct.description || "Tidak ada deskripsi tambahan.";
    document.getElementById("modal-duration").textContent = selectedProduct.duration_days ? `${selectedProduct.duration_days} Hari` : "Lifetime";

    if (selectedProduct.product_type === 'TEXT_STOCK') {
        document.getElementById("modal-stock").textContent = selectedProduct.stock_count > 0 ? `${selectedProduct.stock_count} Akun` : "Stok Habis";
    } else {
        document.getElementById("modal-stock").textContent = "Pengiriman Instan 1 Detik";
    }

    document.getElementById("product-modal").classList.remove("hidden");
    lucide.createIcons();
}

function closeProductModal() {
    document.getElementById("product-modal").classList.add("hidden");
}

// 6. Apply Promo Code in Modal
async function applyPromoCode() {
    const code = document.getElementById("promo-code-input").value.trim().toUpperCase();
    if (!code || !selectedProduct) return;

    try {
        const res = await fetch('/api/promo/validate', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                code: code,
                user_id: currentUser.id,
                price: selectedProduct.price
            })
        });
        const data = await res.json();
        const msgEl = document.getElementById("promo-applied-msg");

        if (data.success) {
            currentDiscount = data.discount_amount;
            currentPromoCode = code;
            const finalPrice = selectedProduct.price - currentDiscount;

            msgEl.textContent = `✅ Kupon ${code} aktif! Diskon -${formatRupiah(currentDiscount)} (Total: ${formatRupiah(finalPrice)})`;
            msgEl.classList.remove("hidden");
            document.getElementById("modal-price").innerHTML = `<s>${formatRupiah(selectedProduct.price)}</s> <span class="text-emerald-400 font-black">${formatRupiah(finalPrice)}</span>`;
        } else {
            msgEl.textContent = data.message || "Kode promo tidak valid!";
            msgEl.classList.remove("hidden");
            msgEl.classList.replace("text-emerald-400", "text-rose-400");
        }
    } catch (e) {
        console.error("Promo error:", e);
    }
}

// 7. Execute Orders
async function executeBuyWithBalance() {
    if (!selectedProduct) return;
    const finalPrice = selectedProduct.price - currentDiscount;

    if (currentUser.balance < finalPrice) {
        alert(`⚠️ Saldo Anda (${formatRupiah(currentUser.balance)}) tidak cukup untuk membeli ${selectedProduct.name} (${formatRupiah(finalPrice)}). Silakan Top Up Saldo terlebih dahulu!`);
        return;
    }

    if (!confirm(`Konfirmasi pembelian ${selectedProduct.name} menggunakan saldo ${formatRupiah(finalPrice)}?`)) return;

    try {
        const res = await fetch('/api/order/create', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                user_id: currentUser.id,
                product_id: selectedProduct.id,
                payment_method: 'BALANCE',
                promo_code: currentPromoCode,
                discount_amount: currentDiscount
            })
        });
        const data = await res.json();
        if (data.success) {
            alert(`🎉 Pembayaran Sukses! Kredensial produk Anda telah dikirimkan ke chat Telegram bot.`);
            closeProductModal();
            loadUserProfile();
            loadCatalog();
            if (tg) tg.close();
        } else {
            alert(data.message || "Gagal memproses pesanan.");
        }
    } catch (e) {
        alert("Terjadi kesalahan jaringan.");
    }
}

async function executeBuyWithQRIS() {
    if (!selectedProduct) return;
    const finalPrice = selectedProduct.price - currentDiscount;

    try {
        const res = await fetch('/api/order/create', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                user_id: currentUser.id,
                product_id: selectedProduct.id,
                payment_method: 'QRIS',
                promo_code: currentPromoCode,
                discount_amount: currentDiscount
            })
        });
        const data = await res.json();
        if (data.success) {
            alert(`🧾 Invoice QRIS #${data.invoice_id} berhasil dibuat! Silakan buka chat Telegram bot untuk scan dan menyelesaikan pembayaran.`);
            closeProductModal();
            if (tg) tg.close();
        }
    } catch (e) {
        alert("Gagal membuat QRIS.");
    }
}

// 8. Top Up Modal
function openTopUpModal() {
    document.getElementById("topup-modal").classList.remove("hidden");
}

function closeTopUpModal() {
    document.getElementById("topup-modal").classList.add("hidden");
}

async function submitTopUp(amount) {
    try {
        const res = await fetch('/api/order/create', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                user_id: currentUser.id,
                amount: amount,
                trx_type: 'TOPUP',
                payment_method: 'QRIS'
            })
        });
        const data = await res.json();
        if (data.success) {
            alert(`🧾 Invoice Top Up QRIS #${data.invoice_id} dibuat! Silakan buka chat Telegram untuk scan kode QRIS.`);
            closeTopUpModal();
            if (tg) tg.close();
        }
    } catch (e) {
        alert("Gagal membuat invoice top up.");
    }
}

// 9. Load History
async function loadHistory() {
    const list = document.getElementById("history-list");
    try {
        const res = await fetch(`/api/user/history?user_id=${currentUser.id}`);
        const data = await res.json();
        if (data.success && data.transactions.length) {
            list.innerHTML = data.transactions.map(t => {
                const isPaid = t.status === 'PAID';
                const statusBadge = isPaid ? 'bg-emerald-500/20 text-emerald-400' : 'bg-amber-500/20 text-amber-400';
                return `
                    <div class="glass p-3.5 rounded-2xl space-y-2">
                        <div class="flex justify-between items-start">
                            <div>
                                <span class="text-[10px] text-slate-400 font-mono">#${t.id}</span>
                                <h4 class="text-xs font-bold text-white">${t.product_name || (t.trx_type === 'TOPUP' ? 'Top Up Saldo' : 'Produk Digital')}</h4>
                            </div>
                            <span class="text-[10px] font-bold px-2 py-0.5 rounded-full ${statusBadge}">${t.status}</span>
                        </div>
                        <div class="flex justify-between items-center text-xs pt-1 border-t border-slate-800 text-slate-300">
                            <span>Total: <b class="text-indigo-300">${formatRupiah(t.amount)}</b></span>
                            <span class="text-[10px] text-slate-400">${t.date}</span>
                        </div>
                        ${t.delivered_content ? `
                            <div class="bg-slate-900/80 p-2 rounded-xl text-[11px] font-mono text-cyan-300 break-all border border-slate-800">
                                🔑 ${t.delivered_content}
                            </div>
                        ` : ''}
                    </div>
                `;
            }).join("");
        } else {
            list.innerHTML = `<div class="text-center py-10 text-slate-500 text-xs">Belum ada riwayat transaksi.</div>`;
        }
    } catch (e) {
        list.innerHTML = `<div class="text-center py-10 text-rose-500 text-xs">Gagal memuat riwayat.</div>`;
    }
}

// 10. Admin Stats & Features
async function loadAdminStats() {
    try {
        const res = await fetch(`/api/admin/stats?user_id=${currentUser.id}`);
        const data = await res.json();
        if (data.success) {
            document.getElementById("admin-stat-omset").textContent = formatRupiah(data.total_omset);
            document.getElementById("admin-stat-trx").textContent = `${data.total_trx} Pesanan`;
        }
    } catch (e) {
        console.error("Gagal memuat admin stats:", e);
    }
}

function downloadCSVReport() {
    window.location.href = `/api/admin/export-csv?user_id=${currentUser.id}`;
}

// Helper Functions
function formatRupiah(val) {
    return "Rp " + parseFloat(val || 0).toLocaleString("id-ID");
}

function copyRefLink() {
    const input = document.getElementById("ref-link-input");
    input.select();
    document.execCommand("copy");
    if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred("success");
    alert("Tautan afiliasi berhasil disalin!");
}

function withdrawReferral() {
    alert("Untuk mencairkan komisi referral, silakan kirim pesan ke Admin Utama @dasrams.");
}
