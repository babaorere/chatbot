const API_BASE = 'http://localhost:8001';

class TenantApp {
    constructor() {
        this.tenantId = localStorage.getItem('tenant_id');
        this.init();
    }

    async init() {
        if (!this.tenantId) {
            this.tenantId = prompt('Ingresa tu Tenant ID:');
            if (this.tenantId) localStorage.setItem('tenant_id', this.tenantId);
        }

        this.categories = [];
        await this.loadCategories();
        this.setupNavigation();
        this.setupForms();
        this.setupModals();
        await this.loadDashboard();
        await this.loadProfile();
        await this.loadProducts();
        await this.loadKB();
        await this.loadChannels();
    }

    get headers() {
        return {
            'Content-Type': 'application/json',
            'X-Tenant-ID': this.tenantId,
        };
    }

    async fetch(endpoint, options = {}) {
        const url = `${API_BASE}${endpoint}`;
        const res = await fetch(url, {
            ...options,
            headers: { ...this.headers, ...options.headers },
        });
        if (!res.ok) {
            const error = await res.json().catch(() => ({ error: 'Error desconocido' }));
            throw new Error(error.error || `HTTP ${res.status}`);
        }
        return res.json();
    }

    setupNavigation() {
        document.querySelectorAll('.nav-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
                link.classList.add('active');

                document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
                const section = document.getElementById(link.dataset.section);
                if (section) section.classList.add('active');

                document.getElementById('pageTitle').textContent = link.textContent.trim();
            });
        });
    }

    setupForms() {
        document.getElementById('profileForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            try {
                const data = {
                    name: document.getElementById('profileName').value,
                    email: document.getElementById('profileEmail').value || null,
                    phone: document.getElementById('profilePhone').value || null,
                    address: document.getElementById('profileAddress').value || null,
                    city: document.getElementById('profileCity').value || null,
                    website: document.getElementById('profileWebsite').value || null,
                    logo_url: document.getElementById('profileLogo').value || null,
                    business_hours: this.parseJSON(document.getElementById('profileHours').value),
                };
                await this.fetch('/tenants/me/profile', { method: 'PUT', body: JSON.stringify(data) });
                this.showToast('Perfil actualizado', 'success');
                await this.loadProfile();
            } catch (err) {
                this.showToast(err.message, 'error');
            }
        });
    }

    setupModals() {
        document.getElementById('modalClose').addEventListener('click', () => {
            document.getElementById('modal').classList.remove('active');
        });

        document.getElementById('addProductBtn').addEventListener('click', () => {
            this.showProductModal();
        });

        document.getElementById('addKbBtn').addEventListener('click', () => {
            this.showKBModal();
        });

        const addCategoryBtn = document.getElementById('addCategoryBtn');
        if (addCategoryBtn) {
            addCategoryBtn.addEventListener('click', () => {
                this.showCategoryModal();
            });
        }

        document.getElementById('kbSearchBtn').addEventListener('click', () => {
            this.searchKB();
        });
    }

    async loadDashboard() {
        try {
            const [users, convs] = await Promise.all([
                this.fetch('/tenants/me/users/count'),
                this.fetch('/tenants/me/conversations/count'),
            ]);
            document.getElementById('userCount').textContent = users.count;
            document.getElementById('convCount').textContent = convs.count;
        } catch (err) {
            console.error('Dashboard load failed:', err);
        }
    }

    async loadProfile() {
        try {
            const profile = await this.fetch('/tenants/me/profile');
            document.getElementById('tenantName').textContent = profile.name;
            document.getElementById('profileName').value = profile.name || '';
            document.getElementById('profileEmail').value = profile.email || '';
            document.getElementById('profilePhone').value = profile.phone || '';
            document.getElementById('profileAddress').value = profile.address || '';
            document.getElementById('profileCity').value = profile.city || '';
            document.getElementById('profileWebsite').value = profile.website || '';
            document.getElementById('profileLogo').value = profile.logo_url || '';
            document.getElementById('profileHours').value = profile.business_hours ? JSON.stringify(profile.business_hours, null, 2) : '';
            document.getElementById('statusBadge').textContent = profile.status === 'active' ? 'Activo' : 'Inactivo';
        } catch (err) {
            console.error('Profile load failed:', err);
        }
    }

    async loadProducts() {
        try {
            const products = await this.fetch('/tenants/me/products?limit=100');
            const tbody = document.getElementById('productsBody');
            tbody.innerHTML = '';
            products.forEach(p => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${p.name}</td>
                    <td>${p.category || '-'}</td>
                    <td>${p.price ? '$' + p.price.toLocaleString() : '-'}</td>
                    <td>${p.stock}</td>
                    <td>${p.is_available ? '✅' : '❌'}</td>
                    <td>
                        <button class="btn btn-sm btn-secondary" onclick="app.editProduct('${p.id}')">Editar</button>
                        <button class="btn btn-sm btn-danger" onclick="app.deleteProduct('${p.id}')">Eliminar</button>
                    </td>
                `;
                tbody.appendChild(tr);
            });
            document.getElementById('productCount').textContent = products.length;
        } catch (err) {
            console.error('Products load failed:', err);
        }
    }

    async loadKB() {
        try {
            const entries = await this.fetch('/tenants/me/kb?limit=100');
            const tbody = document.getElementById('kbBody');
            tbody.innerHTML = '';
            entries.forEach(e => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${e.category}</td>
                    <td>${e.title}</td>
                    <td>${e.content.substring(0, 50)}...</td>
                    <td>${e.is_active ? '✅' : '❌'}</td>
                    <td>
                        <button class="btn btn-sm btn-secondary" onclick="app.editKB('${e.id}')">Editar</button>
                        <button class="btn btn-sm btn-danger" onclick="app.deleteKB('${e.id}')">Eliminar</button>
                    </td>
                `;
                tbody.appendChild(tr);
            });
            document.getElementById('kbCount').textContent = entries.length;
        } catch (err) {
            console.error('KB load failed:', err);
        }
    }

    async loadChannels() {
        try {
            const channels = await this.fetch('/tenants/me/channels');
            const container = document.getElementById('channelsList');
            container.innerHTML = '';
            if (channels.length === 0) {
                container.innerHTML = '<p class="text-muted">No hay canales configurados.</p>';
                return;
            }
            channels.forEach(c => {
                const card = document.createElement('div');
                card.className = 'channel-card';
                card.innerHTML = `
                    <h4>${c.platform}</h4>
                    <p>${c.channel_identifier}</p>
                `;
                container.appendChild(card);
            });
        } catch (err) {
            console.error('Channels load failed:', err);
        }
    }

    async searchKB() {
        const query = document.getElementById('kbSearchInput').value;
        if (!query) return;
        try {
            const result = await this.fetch('/tenants/me/kb/search', {
                method: 'POST',
                body: JSON.stringify({ query, top_k: 10 }),
            });
            this.showToast(`${result.count} resultados encontrados`, 'success');
        } catch (err) {
            this.showToast(err.message, 'error');
        }
    }

    showProductModal(product = null) {
        const modal = document.getElementById('modal');
        const title = document.getElementById('modalTitle');
        const body = document.getElementById('modalBody');

        const categoryOptions = this.categories.map(c => `
            <option value="${c.name}" ${product?.category === c.name ? 'selected' : ''}>${c.name}</option>
        `).join('');

        title.textContent = product ? 'Editar Producto' : 'Nuevo Producto';
        body.innerHTML = `
            <form id="productForm">
                <div class="form-group">
                    <label>Nombre</label>
                    <input type="text" id="prodName" value="${product?.name || ''}" required>
                </div>
                <div class="form-group">
                    <label>Descripción</label>
                    <textarea id="prodDesc">${product?.description || ''}</textarea>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label>Precio</label>
                        <input type="number" id="prodPrice" value="${product?.price || ''}" step="0.01">
                    </div>
                    <div class="form-group">
                        <label>Stock</label>
                        <input type="number" id="prodStock" value="${product?.stock || 0}">
                    </div>
                </div>
                <div class="form-group">
                    <label>Categoría</label>
                    <select id="prodCategory" class="form-control">${categoryOptions}</select>
                </div>
                <button type="submit" class="btn btn-primary">Guardar</button>
            </form>
        `;

        document.getElementById('productForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const data = {
                name: document.getElementById('prodName').value,
                description: document.getElementById('prodDesc').value || null,
                price: parseFloat(document.getElementById('prodPrice').value) || null,
                stock: parseInt(document.getElementById('prodStock').value) || 0,
                category: document.getElementById('prodCategory').value || null,
                is_available: true,
            };
            try {
                if (product) {
                    await this.fetch(`/tenants/me/products/${product.id}`, { method: 'PUT', body: JSON.stringify(data) });
                } else {
                    await this.fetch('/tenants/me/products', { method: 'POST', body: JSON.stringify(data) });
                }
                this.showToast('Producto guardado', 'success');
                modal.classList.remove('active');
                await this.loadProducts();
            } catch (err) {
                this.showToast(err.message, 'error');
            }
        });

        modal.classList.add('active');
    }

    async editProduct(id) {
        const products = await this.fetch('/tenants/me/products?limit=100');
        const product = products.find(p => p.id === id);
        if (product) this.showProductModal(product);
    }

    async deleteProduct(id) {
        if (!confirm('¿Eliminar este producto?')) return;
        try {
            await this.fetch(`/tenants/me/products/${id}`, { method: 'DELETE' });
            this.showToast('Producto eliminado', 'success');
            await this.loadProducts();
        } catch (err) {
            this.showToast(err.message, 'error');
        }
    }

    showKBModal(entry = null) {
        const modal = document.getElementById('modal');
        const title = document.getElementById('modalTitle');
        const body = document.getElementById('modalBody');

        title.textContent = entry ? 'Editar Entrada KB' : 'Nueva Entrada KB';
        body.innerHTML = `
            <form id="kbForm">
                <div class="form-group">
                    <label>Categoría</label>
                    <input type="text" id="kbCategory" value="${entry?.category || ''}" required>
                </div>
                <div class="form-group">
                    <label>Título</label>
                    <input type="text" id="kbTitle" value="${entry?.title || ''}" required>
                </div>
                <div class="form-group">
                    <label>Contenido</label>
                    <textarea id="kbContent" rows="5" required>${entry?.content || ''}</textarea>
                </div>
                <button type="submit" class="btn btn-primary">Guardar</button>
            </form>
        `;

        document.getElementById('kbForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const data = {
                category: document.getElementById('kbCategory').value,
                title: document.getElementById('kbTitle').value,
                content: document.getElementById('kbContent').value,
            };
            try {
                if (entry) {
                    await this.fetch(`/tenants/me/kb/${entry.id}`, { method: 'PUT', body: JSON.stringify(data) });
                } else {
                    await this.fetch('/tenants/me/kb', { method: 'POST', body: JSON.stringify(data) });
                }
                this.showToast('Entrada guardada', 'success');
                modal.classList.remove('active');
                await this.loadKB();
            } catch (err) {
                this.showToast(err.message, 'error');
            }
        });

        modal.classList.add('active');
    }

    async editKB(id) {
        const entries = await this.fetch('/tenants/me/kb?limit=100');
        const entry = entries.find(e => e.id === id);
        if (entry) this.showKBModal(entry);
    }

    async deleteKB(id) {
        if (!confirm('¿Eliminar esta entrada?')) return;
        try {
            await this.fetch(`/tenants/me/kb/${id}`, { method: 'DELETE' });
            this.showToast('Entrada eliminada', 'success');
            await this.loadKB();
        } catch (err) {
            this.showToast(err.message, 'error');
        }
    }

    showToast(message, type = 'success') {
        const container = document.getElementById('toastContainer');
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.textContent = message;
        container.appendChild(toast);
        setTimeout(() => toast.remove(), 3000);
    }

    parseJSON(str) {
        try {
            return str ? JSON.parse(str) : null;
        } catch {
            return null;
        }
    }

    async loadCategories() {
        try {
            const categories = await this.fetch('/categories');
            this.categories = categories;
            const tbody = document.getElementById('categoriesBody');
            if (!tbody) return;
            tbody.innerHTML = '';
            categories.forEach(c => {
                const tr = document.createElement('tr');
                const actions = c.is_system 
                    ? `<span class="badge status-badge" style="background: var(--bg-hover); color: var(--text-muted); cursor: not-allowed; border: 1px dashed var(--border-color);">🔒 Fijo</span>` 
                    : `
                        <button class="btn btn-sm btn-secondary" onclick="app.editCategory('${c.name}')">Editar</button>
                        <button class="btn btn-sm btn-danger" onclick="app.deleteCategory('${c.name}')">Eliminar</button>
                    `;
                tr.innerHTML = `
                    <td><strong>${c.name}</strong></td>
                    <td><code>${c.slug}</code></td>
                    <td style="display: flex; gap: 8px; align-items: center;">${actions}</td>
                `;
                tbody.appendChild(tr);
            });
        } catch (err) {
            console.error('Categories load failed:', err);
        }
    }

    showCategoryModal(category = null) {
        const modal = document.getElementById('modal');
        const title = document.getElementById('modalTitle');
        const body = document.getElementById('modalBody');

        title.textContent = category ? 'Editar Categoría' : 'Nueva Categoría';
        body.innerHTML = `
            <form id="categoryForm">
                <div class="form-group">
                    <label>Nombre de Categoría</label>
                    <input type="text" id="catName" value="${category || ''}" required placeholder="Ej: Licores Premium">
                </div>
                <button type="submit" class="btn btn-primary">Guardar</button>
            </form>
        `;

        document.getElementById('categoryForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const newName = document.getElementById('catName').value;
            try {
                if (category) {
                    await this.fetch(`/categories/${encodeURIComponent(category)}`, {
                        method: 'PUT',
                        body: JSON.stringify({ new_name: newName }),
                    });
                } else {
                    await this.fetch('/categories', {
                        method: 'POST',
                        body: JSON.stringify({ name: newName }),
                    });
                }
                this.showToast('Categoría guardada', 'success');
                modal.classList.remove('active');
                await this.loadCategories();
                await this.loadProducts();
            } catch (err) {
                this.showToast(err.message, 'error');
            }
        });

        modal.classList.add('active');
    }

    async deleteCategory(name) {
        if (!confirm(`¿Estás seguro de que deseas eliminar la categoría '${name}'? Todos los productos asociados pasarán automáticamente a la categoría 'General'.`)) return;
        try {
            await this.fetch(`/categories/${encodeURIComponent(name)}`, { method: 'DELETE' });
            this.showToast('Categoría eliminada con éxito', 'success');
            await this.loadCategories();
            await this.loadProducts();
        } catch (err) {
            this.showToast(err.message, 'error');
        }
    }

    editCategory(name) {
        this.showCategoryModal(name);
    }
}

const app = new TenantApp();
