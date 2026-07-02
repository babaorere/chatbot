const API_BASE = 'http://localhost:8001';

class AdminApp {
    constructor() {
        this.init();
    }

    async init() {
        this.setupNavigation();
        this.setupModals();
        this.setupQuickActions();
        await this.loadDashboard();
        await this.loadSettings();
        await this.loadAdmins();
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

        document.getElementById('addAdminBtn').addEventListener('click', () => {
            this.showAdminModal();
        });
    }

    setupQuickActions() {
        return;
    }

    async loadDashboard() {
        try {
            const settings = await this.fetch('/admin/settings');
            document.getElementById('tenantCount').textContent = '1';
            document.getElementById('activeTenantCount').textContent = '1';
            document.getElementById('tenantCountLabel').textContent = 'Negocio';
            document.getElementById('activeTenantCountLabel').textContent = 'Activo';
            document.getElementById('dashboardOverview').textContent = `Negocio configurado con ${Object.keys(settings).length} parámetros globales.`;
        } catch (err) {
            console.error('Dashboard load failed:', err);
        }
    }

    async loadTenants() {
        const tbody = document.getElementById('tenantsBody');
        if (tbody) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="5" class="empty-state">El modo multi-negocio está deshabilitado. La administración ahora es de un solo negocio.</td>
                </tr>
            `;
        }
    }

    async loadAgentConfig() {
        const notice = document.getElementById('agentNotice');
        if (notice) {
            notice.textContent = 'La configuración del agente se administra desde los parámetros globales del negocio.';
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

    async loadAdmins() {
        try {
            const admins = await this.fetch('/admin/system-admins');
            const tbody = document.getElementById('adminsBody');
            tbody.innerHTML = '';

            admins.forEach(admin => {
                const tr = document.createElement('tr');
                
                // Formatear medios de contacto
                const contacts = [];
                if (admin.telegram_chat_id) contacts.push(`Telegram: <code>${admin.telegram_chat_id}</code>`);
                if (admin.email) contacts.push(`Email: ${admin.email}`);
                if (admin.whatsapp_phone) contacts.push(`WA: ${admin.whatsapp_phone}`);
                const contactHtml = contacts.join('<br>') || '<em>Sin contacto</em>';

                // Canales activos
                const channels = [];
                if (admin.notify_telegram) channels.push('📱 Telegram');
                if (admin.notify_email) channels.push('📧 Email');
                if (admin.notify_whatsapp) channels.push('💬 WhatsApp');
                const channelsHtml = channels.join(', ') || 'Ninguno';

                // Tipos de alerta
                const alertsHtml = admin.alert_types.map(t => `<span class="badge badge-sm">${t}</span>`).join(' ') || '<span class="badge badge-sm">Todas</span>';

                tr.innerHTML = `
                    <td><strong>${admin.name}</strong></td>
                    <td>${contactHtml}</td>
                    <td>${channelsHtml}</td>
                    <td>${alertsHtml}</td>
                    <td>
                        <button class="btn btn-sm btn-secondary" onclick="app.showAdminModal(${JSON.stringify(admin).replace(/"/g, '&quot;')})">Editar</button>
                        <button class="btn btn-sm btn-danger" onclick="app.deleteAdmin(${admin.id})">Eliminar</button>
                    </td>
                `;
                tbody.appendChild(tr);
            });
        } catch (err) {
            console.error('Admins load failed:', err);
        }
    }

    showAdminModal(admin = null) {
        const modal = document.getElementById('modal');
        const title = document.getElementById('modalTitle');
        const body = document.getElementById('modalBody');

        title.textContent = admin ? `Editar Administrador: ${admin.name}` : 'Nuevo Administrador';
        
        const nameVal = admin ? admin.name : '';
        const emailVal = admin ? admin.email || '' : '';
        const telegramVal = admin ? admin.telegram_chat_id || '' : '';
        const whatsappVal = admin ? admin.whatsapp_phone || '' : '';
        const notifyEmail = admin ? admin.notify_email : false;
        const notifyTelegram = admin ? admin.notify_telegram : true;
        const notifyWhatsapp = admin ? admin.notify_whatsapp : false;
        const alerts = admin ? admin.alert_types : ['latency', 'error'];

        body.innerHTML = `
            <form id="adminForm">
                <div class="form-group">
                    <label class="label-with-help">Nombre
                        <button type="button" class="help-tip" data-tooltip="Nombre completo o alias identificador del administrador." aria-label="Ayuda sobre nombre">?</button>
                    </label>
                    <input type="text" id="adminName" required value="${nameVal}">
                </div>
                <div class="form-group">
                    <label class="label-with-help">Email (Opcional)
                        <button type="button" class="help-tip" data-tooltip="Dirección de correo donde se enviarán reportes o alertas si el canal email está activo." aria-label="Ayuda sobre email">?</button>
                    </label>
                    <input type="email" id="adminEmail" value="${emailVal}">
                </div>
                <div class="form-group">
                    <label class="label-with-help">Telegram Chat ID (Opcional)
                        <button type="button" class="help-tip" data-tooltip="ID numérico único del chat del administrador. Se puede obtener mediante bots como @userinfobot en Telegram." aria-label="Ayuda sobre telegram chat id">?</button>
                    </label>
                    <input type="text" id="adminTelegramChatId" value="${telegramVal}">
                </div>
                <div class="form-group">
                    <label class="label-with-help">WhatsApp Teléfono (Opcional)
                        <button type="button" class="help-tip" data-tooltip="Número de teléfono móvil en formato internacional, incluyendo código de país (ej: +56912345678)." aria-label="Ayuda sobre whatsapp">?</button>
                    </label>
                    <input type="text" id="adminWhatsappPhone" value="${whatsappVal}">
                </div>
                
                <div class="form-group">
                    <label class="label-with-help">Canales de Notificación Activos
                        <button type="button" class="help-tip" data-tooltip="Medios seleccionados a través de los cuales se enviarán las alertas. El soporte de WhatsApp se integrará en la próxima versión." aria-label="Ayuda sobre canales">?</button>
                    </label>
                    <div style="display: flex; gap: 15px; margin-top: 5px;">
                        <label style="font-weight: normal; cursor: pointer;">
                            <input type="checkbox" id="adminNotifyTelegram" ${notifyTelegram ? 'checked' : ''}> Telegram
                        </label>
                        <label style="font-weight: normal; cursor: pointer;">
                            <input type="checkbox" id="adminNotifyEmail" ${notifyEmail ? 'checked' : ''}> Email
                        </label>
                        <label style="font-weight: normal; cursor: pointer;">
                            <input type="checkbox" id="adminNotifyWhatsapp" ${notifyWhatsapp ? 'checked' : ''}> WhatsApp
                        </label>
                    </div>
                </div>

                <div class="form-group">
                    <label class="label-with-help">Tipos de Alerta a Recibir
                        <button type="button" class="help-tip" data-tooltip="Eventos del sistema que dispararán notificaciones (latencia mayor a 10 segundos o errores en llamadas de API)." aria-label="Ayuda sobre tipos de alerta">?</button>
                    </label>
                    <div style="display: flex; gap: 15px; margin-top: 5px;">
                        <label style="font-weight: normal; cursor: pointer;">
                            <input type="checkbox" id="adminAlertLatency" ${alerts.includes('latency') ? 'checked' : ''}> Latencias Críticas (LLM)
                        </label>
                        <label style="font-weight: normal; cursor: pointer;">
                            <input type="checkbox" id="adminAlertError" ${alerts.includes('error') ? 'checked' : ''}> Errores de Inferencia / API
                        </label>
                    </div>
                </div>

                <button type="submit" class="btn btn-primary" style="margin-top: 10px;">${admin ? 'Guardar Cambios' : 'Crear Administrador'}</button>
            </form>
        `;

        document.getElementById('adminForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            try {
                const alertTypes = [];
                if (document.getElementById('adminAlertLatency').checked) alertTypes.push('latency');
                if (document.getElementById('adminAlertError').checked) alertTypes.push('error');

                const data = {
                    name: document.getElementById('adminName').value,
                    email: document.getElementById('adminEmail').value || null,
                    telegram_chat_id: document.getElementById('adminTelegramChatId').value || null,
                    whatsapp_phone: document.getElementById('adminWhatsappPhone').value || null,
                    notify_email: document.getElementById('adminNotifyEmail').checked,
                    notify_telegram: document.getElementById('adminNotifyTelegram').checked,
                    notify_whatsapp: document.getElementById('adminNotifyWhatsapp').checked,
                    alert_types: alertTypes
                };

                const method = admin ? 'PUT' : 'POST';
                const endpoint = admin ? `/admin/system-admins/${admin.id}` : '/admin/system-admins';

                await this.fetch(endpoint, {
                    method,
                    body: JSON.stringify(data)
                });

                this.showToast(admin ? 'Administrador actualizado' : 'Administrador creado', 'success');
                modal.classList.remove('active');
                await this.loadAdmins();
            } catch (err) {
                this.showToast(err.message, 'error');
            }
        });

        modal.classList.add('active');
    }

    async deleteAdmin(id) {
        if (!confirm('¿Eliminar este administrador de la lista de alertas?')) return;
        try {
            await this.fetch(`/admin/system-admins/${id}`, { method: 'DELETE' });
            this.showToast('Administrador eliminado', 'success');
            await this.loadAdmins();
        } catch (err) {
            this.showToast(err.message, 'error');
        }
    }
}

const app = new AdminApp();
