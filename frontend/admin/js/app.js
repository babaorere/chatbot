const API_BASE = 'http://localhost:8001';

class AdminApp {
    constructor() {
        this.init();
    }

    async init() {
        this.setupNavigation();
        this.setupModals();
        this.setupAgentConfig();
        await this.loadDashboard();
        await this.loadTenants();
        await this.loadSettings();
    }

    async fetch(endpoint, options = {}) {
        const url = `${API_BASE}${endpoint}`;
        const res = await fetch(url, {
            ...options,
            headers: { 'Content-Type': 'application/json', ...options.headers },
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

    setupModals() {
        document.getElementById('modalClose').addEventListener('click', () => {
            document.getElementById('modal').classList.remove('active');
        });

        document.getElementById('addTenantBtn').addEventListener('click', () => {
            this.showTenantModal();
        });
    }

    setupAgentConfig() {
        document.getElementById('agentTenant').addEventListener('change', async (e) => {
            await this.loadAgentConfig(e.target.value);
        });

        document.getElementById('saveAgentBtn').addEventListener('click', async () => {
            const tenantId = document.getElementById('agentTenant').value;
            if (!tenantId) return;
            try {
                const data = {
                    model: document.getElementById('agentModel').value,
                    instruction: document.getElementById('agentInstruction').value,
                };
                const apiKey = document.getElementById('agentApiKey').value;
                if (apiKey) data.api_key = apiKey;

                await this.fetch(`/admin/tenants/${tenantId}/agent`, {
                    method: 'PUT',
                    body: JSON.stringify(data),
                });
                this.showToast('Configuración del agente actualizada', 'success');
            } catch (err) {
                this.showToast(err.message, 'error');
            }
        });
    }

    async loadDashboard() {
        try {
            const tenants = await this.fetch('/admin/tenants?limit=100');
            document.getElementById('tenantCount').textContent = tenants.length;
            document.getElementById('activeTenantCount').textContent = tenants.filter(t => t.status === 'active').length;
        } catch (err) {
            console.error('Dashboard load failed:', err);
        }
    }

    async loadTenants() {
        try {
            const tenants = await this.fetch('/admin/tenants?limit=100');
            const tbody = document.getElementById('tenantsBody');
            const select = document.getElementById('agentTenant');
            tbody.innerHTML = '';
            select.innerHTML = '<option value="">Seleccionar tenant...</option>';

            tenants.forEach(t => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${t.slug}</td>
                    <td>${t.name}</td>
                    <td>${t.status === 'active' ? '✅ Activo' : '❌ Inactivo'}</td>
                    <td>${new Date().toLocaleDateString()}</td>
                    <td>
                        <button class="btn btn-sm btn-secondary" onclick="app.toggleStatus('${t.id}', '${t.status}')">
                            ${t.status === 'active' ? 'Desactivar' : 'Activar'}
                        </button>
                        <button class="btn btn-sm btn-danger" onclick="app.deleteTenant('${t.id}')">Eliminar</button>
                    </td>
                `;
                tbody.appendChild(tr);

                const option = document.createElement('option');
                option.value = t.id;
                option.textContent = `${t.name} (${t.slug})`;
                select.appendChild(option);
            });
        } catch (err) {
            console.error('Tenants load failed:', err);
        }
    }

    async loadAgentConfig(tenantId) {
        if (!tenantId) return;
        try {
            const config = await this.fetch(`/admin/tenants/${tenantId}/agent`);
            document.getElementById('agentModel').value = config.model || '';
            document.getElementById('agentInstruction').value = config.instruction || '';
            document.getElementById('agentApiKey').value = config.has_api_key ? '••••••••' : '';
        } catch (err) {
            this.showToast(err.message, 'error');
        }
    }

    async loadSettings() {
        try {
            const settings = await this.fetch('/admin/settings');
            const tbody = document.getElementById('settingsBody');
            tbody.innerHTML = '';

            Object.entries(settings).forEach(([key, value]) => {
                const tr = document.createElement('tr');
                const displayValue = typeof value === 'object' ? JSON.stringify(value) : String(value);
                tr.innerHTML = `
                    <td><code>${key}</code></td>
                    <td>${displayValue.substring(0, 50)}${displayValue.length > 50 ? '...' : ''}</td>
                    <td>${key}</td>
                    <td>
                        <button class="btn btn-sm btn-secondary" onclick="app.editSetting('${key}')">Editar</button>
                    </td>
                `;
                tbody.appendChild(tr);
            });
        } catch (err) {
            console.error('Settings load failed:', err);
        }
    }

    showTenantModal() {
        const modal = document.getElementById('modal');
        const title = document.getElementById('modalTitle');
        const body = document.getElementById('modalBody');

        title.textContent = 'Nuevo Tenant';
        body.innerHTML = `
            <form id="tenantForm">
                <div class="form-group">
                    <label>Slug</label>
                    <input type="text" id="tenantSlug" required placeholder="mi_chatbot">
                </div>
                <div class="form-group">
                    <label>Nombre</label>
                    <input type="text" id="tenantName" required placeholder="Negocio Mi Negocio">
                </div>
                <div class="form-group">
                    <label>Instrucción del Agente</label>
                    <textarea id="tenantInstruction" rows="5" required placeholder="Eres el asistente virtual de..."></textarea>
                </div>
                <div class="form-group">
                    <label>Modelo</label>
                    <input type="text" id="tenantModel" value="openrouter/nvidia/nemotron-3-super-120b-a12b:free">
                </div>
                <div class="form-group">
                    <label>API Key (OpenRouter)</label>
                    <input type="password" id="tenantApiKey" placeholder="<OPENROUTER_API_KEY>">
                </div>
                <button type="submit" class="btn btn-primary">Crear Tenant</button>
            </form>
        `;

        document.getElementById('tenantForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            try {
                const data = {
                    slug: document.getElementById('tenantSlug').value,
                    name: document.getElementById('tenantName').value,
                    instruction: document.getElementById('tenantInstruction').value,
                    model: document.getElementById('tenantModel').value,
                    api_key: document.getElementById('tenantApiKey').value,
                };
                await this.fetch('/admin/tenants', { method: 'POST', body: JSON.stringify(data) });
                this.showToast('Tenant creado', 'success');
                modal.classList.remove('active');
                await this.loadTenants();
                await this.loadDashboard();
            } catch (err) {
                this.showToast(err.message, 'error');
            }
        });

        modal.classList.add('active');
    }

    async toggleStatus(id, currentStatus) {
        const newStatus = currentStatus === 'active' ? 'inactive' : 'active';
        try {
            await this.fetch(`/admin/tenants/${id}/status?status=${newStatus}`, { method: 'PATCH' });
            this.showToast(`Tenant ${newStatus === 'active' ? 'activado' : 'desactivado'}`, 'success');
            await this.loadTenants();
            await this.loadDashboard();
        } catch (err) {
            this.showToast(err.message, 'error');
        }
    }

    async deleteTenant(id) {
        if (!confirm('¿Eliminar este tenant? Esta acción no se puede deshacer.')) return;
        try {
            await this.fetch(`/admin/tenants/${id}`, { method: 'DELETE' });
            this.showToast('Tenant eliminado', 'success');
            await this.loadTenants();
            await this.loadDashboard();
        } catch (err) {
            this.showToast(err.message, 'error');
        }
    }

    editSetting(key) {
        const modal = document.getElementById('modal');
        const title = document.getElementById('modalTitle');
        const body = document.getElementById('modalBody');

        title.textContent = `Editar Setting: ${key}`;
        body.innerHTML = `
            <form id="settingForm">
                <div class="form-group">
                    <label>Valor (JSON)</label>
                    <textarea id="settingValue" rows="5"></textarea>
                </div>
                <button type="submit" class="btn btn-primary">Guardar</button>
            </form>
        `;

        this.fetch('/admin/settings').then(settings => {
            const value = settings[key];
            document.getElementById('settingValue').value = typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value);
        });

        document.getElementById('settingForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            try {
                const rawValue = document.getElementById('settingValue').value;
                let value;
                try {
                    value = JSON.parse(rawValue);
                } catch {
                    value = rawValue;
                }
                await this.fetch(`/admin/settings/${key}`, {
                    method: 'PUT',
                    body: JSON.stringify({ value }),
                });
                this.showToast('Setting actualizado', 'success');
                modal.classList.remove('active');
                await this.loadSettings();
            } catch (err) {
                this.showToast(err.message, 'error');
            }
        });

        modal.classList.add('active');
    }

    showToast(message, type = 'success') {
        const container = document.getElementById('toastContainer');
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.textContent = message;
        container.appendChild(toast);
        setTimeout(() => toast.remove(), 3000);
    }
}

const app = new AdminApp();
