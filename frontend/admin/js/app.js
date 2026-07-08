const API_BASE = 'http://localhost:8001';
const API_KEY_STORAGE = 'admin_api_key';

class AdminApp {
    constructor() {
        this.apiKey = sessionStorage.getItem(API_KEY_STORAGE) || '';
        if (this.apiKey) {
            this.init();
        }
    }

    async init() {
        this.setupNavigation();
        this.setupModals();
        this.setupQuickActions();
        this.setupLogout();
        this.setupTableFilter('settingsFilterInput', 'settingsBody');
        this.setupTableFilter('tenantInvitesFilterInput', 'tenantInvitesBody');
        this.setupTableFilter('tenantUsersFilterInput', 'tenantUsersBody');
        this.setupTableFilter('adminsFilterInput', 'adminsBody');
        window.addEventListener('offline', () => this.showOfflineBanner());
        window.addEventListener('online', () => this.showOnlineBanner());
        if (!navigator.onLine) {
            this.showOfflineBanner();
        }
        await this.loadDashboard();
        await this.loadAgentConfig();
        await this.loadSettings();
        await this.loadTenantAccess();
        await this.loadAdmins();
    }

    async fetch(endpoint, options = {}) {
        const url = `${API_BASE}${endpoint}`;
        const res = await fetch(url, {
            ...options,
            headers: {
                'Content-Type': 'application/json',
                'X-Admin-API-Key': this.apiKey,
                ...options.headers,
            },
        });
        if (res.status === 429) {
            const msg = 'Has superado el límite de solicitudes. Por favor, espera unos segundos antes de reintentar.';
            this.showToast(msg, 'error');
            throw new Error(msg);
        }
        if (res.status === 403) {
            sessionStorage.removeItem(API_KEY_STORAGE);
            this.apiKey = '';
            this.showLoginScreen('Clave inválida o expirada. Ingrese la clave de administración.');
            throw new Error('HTTP 403');
        }
        if (!res.ok) {
            const error = await res.json().catch(() => ({ error: 'Error desconocido' }));
            throw new Error(error.error || `HTTP ${res.status}`);
        }
        return res.json();
    }

    showLoginScreen(message = 'Ingrese la clave de administración para acceder al panel.') {
        let overlay = document.getElementById('loginOverlay');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.id = 'loginOverlay';
            overlay.style.cssText = [
                'position:fixed', 'inset:0', 'background:rgba(10,10,20,0.92)',
                'display:flex', 'align-items:center', 'justify-content:center',
                'z-index:9999', 'backdrop-filter:blur(8px)',
            ].join(';');
            overlay.innerHTML = `
                <div style="background:#1a1a2e;border:1px solid #3a3a5c;border-radius:16px;padding:2.5rem;width:min(400px,90vw);box-shadow:0 25px 60px rgba(0,0,0,0.6);">
                    <h2 style="margin:0 0 0.5rem;color:#e2e8f0;font-size:1.4rem;">&#128272; Panel de Administración</h2>
                    <p id="loginMsg" style="margin:0 0 1.5rem;color:#94a3b8;font-size:0.9rem;">${message}</p>
                    <form id="loginForm">
                        <input type="text" name="username" autocomplete="username"
                            style="display:none;" aria-hidden="true" tabindex="-1"
                            value="admin">
                        <div style="position:relative;margin-bottom:1rem;">
                            <input id="loginKeyInput" type="password" name="password"
                                autocomplete="current-password"
                                placeholder="Clave de administración"
                                style="width:100%;box-sizing:border-box;padding:0.75rem 3rem 0.75rem 1rem;
                                       border-radius:8px;border:1px solid #3a3a5c;background:#0f0f1a;
                                       color:#e2e8f0;font-size:1rem;outline:none;"
                            >
                            <button type="button" id="toggleKeyVisibility"
                                title="Mostrar / ocultar clave"
                                style="position:absolute;right:0.75rem;top:50%;transform:translateY(-50%);
                                       background:none;border:none;cursor:pointer;color:#94a3b8;
                                       font-size:1.1rem;line-height:1;padding:0;">&#128065;</button>
                        </div>
                            <button type="submit" id="loginSubmitBtn"
                                style="width:100%;padding:0.8rem;border:none;border-radius:8px;
                                       background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff;
                                       font-size:1rem;font-weight:600;cursor:pointer;">
                            Acceder
                        </button>
                    </form>
                </div>`;
            document.body.appendChild(overlay);

            const doLogin = (e) => {
                if (e) e.preventDefault();
                const key = document.getElementById('loginKeyInput').value.trim();
                if (!key) return;
                this.apiKey = key;
                sessionStorage.setItem(API_KEY_STORAGE, key);
                overlay.remove();
                this.init();
            };
            document.getElementById('loginForm').addEventListener('submit', doLogin);
            document.getElementById('loginKeyInput').addEventListener('keydown', (e) => {
                if (e.key === 'Enter') { e.preventDefault(); doLogin(e); }
            });
            document.getElementById('toggleKeyVisibility').addEventListener('click', () => {
                const inp = document.getElementById('loginKeyInput');
                const btn = document.getElementById('toggleKeyVisibility');
                if (inp.type === 'password') {
                    inp.type = 'text';
                    btn.innerHTML = '&#128683;';
                } else {
                    inp.type = 'password';
                    btn.innerHTML = '&#128065;';
                }
            });
        } else {
            document.getElementById('loginMsg').textContent = message;
        }
        document.getElementById('loginKeyInput')?.focus();
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
        const modalClose = document.getElementById('modalClose');
        if (modalClose) {
            modalClose.addEventListener('click', () => {
                document.getElementById('modal')?.classList.remove('active');
            });
        }

        const addAdminBtn = document.getElementById('addAdminBtn');
        if (addAdminBtn) {
            addAdminBtn.addEventListener('click', () => {
                this.showAdminModal();
            });
        }
    }

    setupQuickActions() {
        const goToSettingsBtnTop = document.getElementById('goToSettingsBtnTop');
        if (goToSettingsBtnTop) {
            goToSettingsBtnTop.addEventListener('click', () => {
                document.querySelector('.nav-link[data-section="settings"]')?.click();
            });
        }

        const goToAgentBtn = document.getElementById('goToAgentBtn');
        if (goToAgentBtn) {
            goToAgentBtn.addEventListener('click', () => {
                document.querySelector('.nav-link[data-section="agent"]')?.click();
            });
        }

        const goToTenantAccessBtn = document.getElementById('goToTenantAccessBtn');
        if (goToTenantAccessBtn) {
            goToTenantAccessBtn.addEventListener('click', () => {
                document.querySelector('.nav-link[data-section="tenantAccess"]')?.click();
            });
        }
    }

    setupLogout() {
        const logoutBtn = document.getElementById('adminLogoutBtn');
        if (!logoutBtn) return;
        logoutBtn.addEventListener('click', () => {
            if (!confirm('¿Seguro que desea salir del panel de administración general?')) return;
            sessionStorage.removeItem(API_KEY_STORAGE);
            this.apiKey = '';
            this.showLoginScreen('La sesión administrativa se cerró correctamente.');
        });
    }

    setupTableFilter(inputId, tbodyId) {
        const input = document.getElementById(inputId);
        const tbody = document.getElementById(tbodyId);
        if (!input || !tbody) return;
        input.addEventListener('input', () => {
            this.applyTableFilter(inputId, tbodyId);
        });
    }

    applyTableFilter(inputId, tbodyId) {
        const input = document.getElementById(inputId);
        const tbody = document.getElementById(tbodyId);
        if (!input || !tbody) return;
        const query = (input.value || '').toLowerCase().trim();
        Array.from(tbody.querySelectorAll('tr')).forEach(row => {
            if (row.querySelector('.empty-state') || row.querySelector('.text-muted')) return;
            const text = row.textContent.toLowerCase();
            row.style.display = (!query || text.includes(query)) ? '' : 'none';
        });
    }

    async loadDashboard() {
        try {
            const settings = await this.fetch('/admin/settings');
            
            // Mostrar nombre abreviado del modelo en el badge
            const mainModel = settings.model_name || 'Desconocido';
            const modelShort = mainModel.split('/').pop() || mainModel;
            document.getElementById('activeAgentStatus').textContent = modelShort;
            
            const settingsCount = Object.keys(settings).length;
            document.getElementById('systemSettingsCount').textContent = String(settingsCount);
            
            document.getElementById('dashboardOverview').innerHTML = `
                El sistema opera actualmente en modo <strong>instancia única</strong> y <strong>multiusuario</strong>.<br>
                El motor de IA principal está configurado como <code>${mainModel}</code>.
            `;
        } catch (err) {
            console.error('Dashboard load failed:', err);
        }
    }

    async loadAgentConfig() {
        try {
            const settings = await this.fetch('/admin/settings');
            
            const mainModel = settings.model_name || '';
            const fb1 = settings.fallback_model_1 || 'none';
            const fb2 = settings.fallback_model_2 || 'none';
            const inst = settings.agent_instruction || '';
            
            const modelSelect = document.getElementById('agentModel');
            const fb1Select = document.getElementById('agentFallback1');
            const fb2Select = document.getElementById('agentFallback2');
            const instTextarea = document.getElementById('agentInstruction');
            const apiKeyInput = document.getElementById('agentApiKey');

            // Asegurar que las opciones actuales existan en los dropdowns
            const ensureOptionExists = (selectEl, val) => {
                if (!val || val === 'none') return;
                let exists = false;
                for (let i = 0; i < selectEl.options.length; i++) {
                    if (selectEl.options[i].value === val) {
                        exists = true;
                        break;
                    }
                }
                if (!exists) {
                    const opt = document.createElement('option');
                    opt.value = val;
                    opt.textContent = `Personalizado - ${val}`;
                    selectEl.appendChild(opt);
                }
            };

            if (modelSelect) ensureOptionExists(modelSelect, mainModel);
            if (fb1Select) ensureOptionExists(fb1Select, fb1);
            if (fb2Select) ensureOptionExists(fb2Select, fb2);

            if (modelSelect) modelSelect.value = mainModel;
            if (fb1Select) fb1Select.value = fb1;
            if (fb2Select) fb2Select.value = fb2;
            if (instTextarea) instTextarea.value = inst;
            if (apiKeyInput) apiKeyInput.value = ''; // Se deja en blanco en UI por seguridad

            // Enlazar botón de guardar una sola vez
            if (!this.agentConfigSetupDone) {
                const saveBtn = document.getElementById('saveAgentBtn');
                if (saveBtn) {
                    saveBtn.onclick = async () => {
                        try {
                            const newModel = modelSelect.value;
                            const newFb1 = fb1Select.value;
                            const newFb2 = fb2Select.value;
                            const newInst = instTextarea.value;
                            const newApiKey = apiKeyInput.value.trim();

                            saveBtn.disabled = true;
                            saveBtn.textContent = 'Guardando...';

                            await this.fetch('/admin/settings/model_name', {
                                method: 'PUT',
                                body: JSON.stringify({ value: newModel })
                            });
                            await this.fetch('/admin/settings/fallback_model_1', {
                                method: 'PUT',
                                body: JSON.stringify({ value: newFb1 })
                            });
                            await this.fetch('/admin/settings/fallback_model_2', {
                                method: 'PUT',
                                body: JSON.stringify({ value: newFb2 })
                            });
                            await this.fetch('/admin/settings/agent_instruction', {
                                method: 'PUT',
                                body: JSON.stringify({ value: newInst })
                            });

                            if (newApiKey) {
                                await this.fetch('/admin/settings/openrouter_api_key', {
                                    method: 'PUT',
                                    body: JSON.stringify({ value: newApiKey })
                                });
                            }

                            this.showToast('Configuración del Agente guardada con éxito', 'success');
                            await this.loadDashboard();
                            await this.loadSettings();
                        } catch (err) {
                            this.showToast(err.message, 'error');
                        } finally {
                            saveBtn.disabled = false;
                            saveBtn.textContent = 'Guardar Configuración';
                        }
                    };
                }
                this.agentConfigSetupDone = true;
            }
        } catch (err) {
            console.error('Agent config load failed:', err);
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
        this.applyTableFilter('settingsFilterInput', 'settingsBody');
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
        this.applyTableFilter('adminsFilterInput', 'adminsBody');
    }

    async loadTenantAccess() {
        try {
            const [invites, users] = await Promise.all([
                this.fetch('/admin/tenant-access/invites'),
                this.fetch('/admin/tenant-access/users'),
            ]);

            const invitesBody = document.getElementById('tenantInvitesBody');
            if (invitesBody) {
                invitesBody.innerHTML = '';
                if (invites.length === 0) {
                    invitesBody.innerHTML = '<tr><td colspan="5" class="empty-state">Todavía no hay invitaciones emitidas.</td></tr>';
                }
                invites.forEach((invite) => {
                    const tr = document.createElement('tr');
                    const status = invite.revoked_at
                        ? 'Revocada'
                        : invite.used_at
                            ? 'Usada'
                            : 'Pendiente';
                    const action = !invite.revoked_at && !invite.used_at
                        ? `<button class="btn btn-sm btn-danger" onclick="app.revokeTenantInvite('${invite.id}')">Revocar</button>`
                        : '<span class="status-pill unavailable">Cerrada</span>';
                    tr.innerHTML = `
                        <td>${invite.email}</td>
                        <td><code>${invite.role}</code></td>
                        <td>${this.formatDateTime(invite.expires_at)}</td>
                        <td>${status}</td>
                        <td class="table-actions">
                            ${invite.invite_url ? `<button class="btn btn-sm btn-secondary" onclick="app.copyInviteLink('${invite.invite_url}')">Copiar link</button>` : ''}
                            ${action}
                        </td>
                    `;
                    invitesBody.appendChild(tr);
                });
            }

            const usersBody = document.getElementById('tenantUsersBody');
            if (usersBody) {
                usersBody.innerHTML = '';
                if (users.length === 0) {
                    usersBody.innerHTML = '<tr><td colspan="6" class="empty-state">Aún no hay usuarios activos.</td></tr>';
                }
                users.forEach((user) => {
                    const tr = document.createElement('tr');
                    const canDisable = user.status === 'active';
                    tr.innerHTML = `
                        <td><strong>${user.full_name}</strong></td>
                        <td>${user.email}</td>
                        <td><code>${user.role}</code></td>
                        <td>${user.status}</td>
                        <td>${user.last_login_at ? this.formatDateTime(user.last_login_at) : 'Nunca'}</td>
                        <td class="table-actions">
                            ${canDisable
                                ? `<button class="btn btn-sm btn-danger" onclick="app.disableTenantUser(${user.id})">Desactivar</button>`
                                : `<button class="btn btn-sm btn-secondary" onclick="app.enableTenantUser(${user.id})">Reactivar</button>`}
                        </td>
                    `;
                    usersBody.appendChild(tr);
                });
            }

            const addTenantInviteBtn = document.getElementById('addTenantInviteBtn');
            if (addTenantInviteBtn && !this.tenantInviteSetupDone) {
                addTenantInviteBtn.addEventListener('click', () => this.showTenantInviteModal());
                this.tenantInviteSetupDone = true;
            }
        } catch (err) {
            console.error('Tenant access load failed:', err);
        }
        this.applyTableFilter('tenantInvitesFilterInput', 'tenantInvitesBody');
        this.applyTableFilter('tenantUsersFilterInput', 'tenantUsersBody');
    }

    formatDateTime(value) {
        if (!value) return '—';
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return value;
        return date.toLocaleString('es-CL');
    }

    copyInviteLink(relativeUrl) {
        const absoluteUrl = new URL(relativeUrl, window.location.origin).toString();
        navigator.clipboard.writeText(absoluteUrl)
            .then(() => this.showToast('Link de invitación copiado', 'success'))
            .catch(() => this.showToast(absoluteUrl, 'success'));
    }

    showTenantInviteModal() {
        const modal = document.getElementById('modal');
        const title = document.getElementById('modalTitle');
        const body = document.getElementById('modalBody');

        title.textContent = 'Nueva invitación de acceso';
        body.innerHTML = `
            <form id="tenantInviteForm">
                <div class="form-group">
                    <label>Email</label>
                    <input type="email" id="tenantInviteEmail" required placeholder="equipo@negocio.cl">
                </div>
                <div class="form-group">
                    <label>Nombre sugerido</label>
                    <input type="text" id="tenantInviteName" placeholder="Nombre del usuario">
                </div>
                <div class="form-group">
                    <label>Rol</label>
                    <select id="tenantInviteRole">
                        <option value="owner">owner</option>
                        <option value="manager" selected>manager</option>
                        <option value="staff">staff</option>
                    </select>
                </div>
                <p class="overview-copy" style="margin-bottom:1rem;">La invitación dura 6 horas y solo puede usarse una vez. Al canjearla, el usuario define su contraseña permanente.</p>
                <button type="submit" class="btn btn-primary">Emitir invitación</button>
            </form>
        `;

        document.getElementById('tenantInviteForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            try {
                const invite = await this.fetch('/admin/tenant-access/invites', {
                    method: 'POST',
                    body: JSON.stringify({
                        email: document.getElementById('tenantInviteEmail').value,
                        full_name: document.getElementById('tenantInviteName').value || null,
                        role: document.getElementById('tenantInviteRole').value,
                    }),
                });
                this.showToast('Invitación emitida', 'success');
                modal.classList.remove('active');
                if (invite.invite_url) {
                    this.copyInviteLink(invite.invite_url);
                }
                await this.loadTenantAccess();
            } catch (err) {
                this.showToast(err.message, 'error');
            }
        });

        modal.classList.add('active');
    }

    async revokeTenantInvite(inviteId) {
        if (!confirm('¿Revocar esta invitación? El link dejará de servir de inmediato.')) return;
        try {
            await this.fetch(`/admin/tenant-access/invites/${inviteId}/revoke`, {
                method: 'POST',
            });
            this.showToast('Invitación revocada', 'success');
            await this.loadTenantAccess();
        } catch (err) {
            this.showToast(err.message, 'error');
        }
    }

    async disableTenantUser(userId) {
        if (!confirm('¿Desactivar este usuario del negocio y cerrar sus sesiones?')) return;
        try {
            await this.fetch(`/admin/tenant-access/users/${userId}/disable`, {
                method: 'POST',
                body: JSON.stringify({ disabled: true }),
            });
            this.showToast('Usuario desactivado', 'success');
            await this.loadTenantAccess();
        } catch (err) {
            this.showToast(err.message, 'error');
        }
    }

    async enableTenantUser(userId) {
        try {
            await this.fetch(`/admin/tenant-access/users/${userId}/disable`, {
                method: 'POST',
                body: JSON.stringify({ disabled: false }),
            });
            this.showToast('Usuario reactivado', 'success');
            await this.loadTenantAccess();
        } catch (err) {
            this.showToast(err.message, 'error');
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

    showOfflineBanner() {
        let banner = document.getElementById('offlineBanner');
        if (!banner) {
            banner = document.createElement('div');
            banner.id = 'offlineBanner';
            banner.style.cssText = 'position:fixed; top:0; left:0; width:100%; background:#e53e3e; color:#fff; text-align:center; padding:0.5rem; font-weight:bold; z-index:10000; box-shadow:0 2px 10px rgba(0,0,0,0.3); font-size:0.9rem;';
            banner.textContent = '⚠️ Sin conexión a internet. Algunas funciones pueden no estar disponibles.';
            document.body.appendChild(banner);
        }
    }

    showOnlineBanner() {
        const banner = document.getElementById('offlineBanner');
        if (banner) {
            banner.remove();
        }
        this.showToast('Conexión restablecida.', 'success');
    }
}

function bootstrapAdminApp() {
    const storedKey = sessionStorage.getItem(API_KEY_STORAGE);
    window.app = new AdminApp();
    if (!storedKey) {
        window.app.showLoginScreen();
    }
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bootstrapAdminApp, { once: true });
} else {
    bootstrapAdminApp();
}
