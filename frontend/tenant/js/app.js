const API_BASE = 'http://localhost:8001';

class TenantApp {
    constructor() {
        this.sectionMeta = {
            dashboard: {
                kicker: 'Inicio',
                title: 'Resumen del día',
                description: 'Revise el estado general del negocio y entre rápido a sus tareas principales.',
            },
            profile: {
                kicker: 'Datos',
                title: 'Datos del negocio',
                description: 'Actualice la información que sus clientes ven y la forma en que usted atiende.',
            },
            products: {
                kicker: 'Venta',
                title: 'Productos',
                description: 'Mantenga su catálogo al día para evitar errores al vender o responder consultas.',
            },
            categories: {
                kicker: 'Orden',
                title: 'Grupos de productos',
                description: 'Ordene el catálogo con grupos simples para encontrar y cargar productos más rápido.',
            },
            knowledge: {
                kicker: 'Ayuda',
                title: 'Información útil',
                description: 'Guarde respuestas generales del negocio, como horarios, zonas de entrega y medios de pago.',
            },
            channels: {
                kicker: 'Contacto',
                title: 'Canales de atención',
                description: 'Revise los medios conectados por donde llegan los mensajes de sus clientes.',
            },
            preview: {
                kicker: 'Simulación',
                title: 'Simulador IA',
                description: 'Pruebe en vivo cómo responderá el asistente a sus clientes con la información y productos actuales de su catálogo.',
            },
        };
        this.weekDays = [
            { id: 'lunes', label: 'Lunes', storageKey: 'Lunes' },
            { id: 'martes', label: 'Martes', storageKey: 'Martes' },
            { id: 'miercoles', label: 'Miércoles', storageKey: 'Miércoles' },
            { id: 'jueves', label: 'Jueves', storageKey: 'Jueves' },
            { id: 'viernes', label: 'Viernes', storageKey: 'Viernes' },
            { id: 'sabado', label: 'Sábado', storageKey: 'Sábado' },
            { id: 'domingo', label: 'Domingo', storageKey: 'Domingo' },
        ];
        this.products = [];
        this.profileData = {};
        this.currentUser = null;
        this.hasLoadedInitialData = false;
    }

    async init() {
        this.setupNavigation();
        this.setupQuickActions();
        this.setupForms();
        this.setupModals();
        this.setupPreview();
        this.setupLogout();
        this.setupTableFilter('productsFilterInput', 'productsBody');
        this.setupTableFilter('categoriesFilterInput', 'categoriesBody');
        this.setupTableFilter('kbFilterInput', 'kbBody');
        this.setupBulkActions('productsTable', 'product-select-checkbox', 'selectAllProducts', 'productsBulkBar', 'productsBulkCount', {
            onDelete: async (ids) => {
                await Promise.all(ids.map(id => this.fetch(`/business/me/products/${id}`, { method: 'DELETE' })));
                this.showToast(`${ids.length} productos eliminados`, 'success');
                await this.loadProducts();
            },
            onStatus: async (ids, status) => {
                await Promise.all(ids.map(id => {
                    const p = (this.products || []).find(x => x.id === id);
                    if (!p) return Promise.resolve();
                    return this.fetch(`/business/me/products/${id}`, {
                        method: 'PUT',
                        body: JSON.stringify({ ...p, is_available: status })
                    });
                }));
                this.showToast(`${ids.length} productos actualizados`, 'success');
                await this.loadProducts();
            }
        });
        this.setupBulkActions('kbTable', 'kb-select-checkbox', 'selectAllKb', 'kbBulkBar', 'kbBulkCount', {
            onDelete: async (ids) => {
                await Promise.all(ids.map(id => this.fetch(`/business/me/kb/${id}`, { method: 'DELETE' })));
                this.showToast(`${ids.length} respuestas eliminadas`, 'success');
                await this.loadKB();
            },
            onStatus: async (ids, status) => {
                await Promise.all(ids.map(id => {
                    const e = (this.kbEntries || []).find(x => x.id === id);
                    if (!e) return Promise.resolve();
                    return this.fetch(`/business/me/kb/${id}`, {
                        method: 'PUT',
                        body: JSON.stringify({ ...e, is_active: status })
                    });
                }));
                this.showToast(`${ids.length} respuestas actualizadas`, 'success');
                await this.loadKB();
            }
        });
        window.addEventListener('offline', () => this.showOfflineBanner());
        window.addEventListener('online', () => this.showOnlineBanner());
        if (!navigator.onLine) {
            this.showOfflineBanner();
        }
        this.showAuthOverlay();
        const authenticated = await this.restoreSession();
        if (!authenticated) {
            this.focusAuthField();
            return;
        }
        await this.finishAuthenticatedBootstrap();
    }

    get headers() {
        return {
            'Content-Type': 'application/json',
        };
    }

    async fetch(endpoint, options = {}, retryOnAuthFailure = true) {
        const url = `${API_BASE}${endpoint}`;
        const res = await fetch(url, {
            ...options,
            credentials: 'include',
            headers: { ...this.headers, ...options.headers },
        });
        if (res.status === 429) {
            const msg = 'Has superado el límite de solicitudes. Por favor, espera unos segundos antes de reintentar.';
            this.showToast(msg, 'error');
            throw new Error(msg);
        }
        if (res.status === 401 && retryOnAuthFailure) {
            const refreshed = await this.tryRefreshSession();
            if (refreshed) {
                return this.fetch(endpoint, options, false);
            }
        }
        if (!res.ok) {
            const error = await res.json().catch(() => ({ error: 'Error desconocido' }));
            throw new Error(this.getFriendlyErrorMessage(res.status, error));
        }
        if (res.status === 204) return null;
        return res.json();
    }

    getFriendlyErrorMessage(status, payload = {}) {
        const rawMessage = payload?.error || payload?.detail || payload?.message || '';
        if (rawMessage) return rawMessage;
        if (status === 400) return 'Revise los datos ingresados antes de continuar.';
        if (status === 401 || status === 403) return 'No fue posible validar el acceso a este negocio.';
        if (status === 429) return 'Has superado el límite de solicitudes. Por favor, espera unos segundos antes de reintentar.';
        if (status === 404) return 'No encontramos la información solicitada.';
        if (status >= 500) return 'Hubo un problema del sistema. Intente nuevamente en unos minutos.';
        return 'No fue posible completar la acción solicitada.';
    }

    escapeHtml(value) {
        return String(value ?? '')
            .replaceAll('&', '&amp;')
            .replaceAll('<', '&lt;')
            .replaceAll('>', '&gt;')
            .replaceAll('"', '&quot;')
            .replaceAll("'", '&#39;');
    }

    async restoreSession() {
        try {
            const session = await this.fetch('/tenant-auth/me', {}, false);
            this.currentUser = session.user;
            this.hideAuthOverlay();
            this.renderTenantUserBadge();
            return true;
        } catch (_err) {
            this.currentUser = null;
            this.renderTenantUserBadge();
            return false;
        }
    }

    async tryRefreshSession() {
        try {
            const session = await this.fetch('/tenant-auth/refresh', { method: 'POST' }, false);
            this.currentUser = session.user;
            this.renderTenantUserBadge();
            return true;
        } catch (_err) {
            this.currentUser = null;
            this.renderTenantUserBadge();
            this.showAuthOverlay('Su sesión expiró. Ingrese nuevamente.');
            return false;
        }
    }

    async finishAuthenticatedBootstrap() {
        if (this.hasLoadedInitialData) return;
        this.categories = [];
        await this.loadCategories();
        await this.loadDashboard();
        await this.loadProducts();
        await this.loadProfile();
        await this.loadKB();
        await this.loadChannels();
        this.hasLoadedInitialData = true;
    }

    renderTenantUserBadge() {
        const badge = document.getElementById('tenantUserBadge');
        if (!badge) return;
        if (!this.currentUser) {
            badge.textContent = 'Sin sesión';
            return;
        }
        badge.textContent = `${this.currentUser.full_name} · ${this.currentUser.role}`;
    }

    setupLogout() {
        const logoutBtn = document.getElementById('logoutBtn');
        if (!logoutBtn) return;
        logoutBtn.addEventListener('click', async () => {
            if (!confirm('¿Seguro que desea cerrar sesión en su panel de administración comercial?')) return;
            try {
                await this.fetch('/tenant-auth/logout', { method: 'POST' }, false);
            } catch (_err) {
                // Si el backend ya no reconoce la sesión, igual limpiamos la UI.
            } finally {
                this.currentUser = null;
                this.hasLoadedInitialData = false;
                this.renderTenantUserBadge();
                this.showAuthOverlay('La sesión se cerró correctamente.');
            }
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

    setupBulkActions(tableId, checkboxClass, selectAllId, bulkBarId, bulkCountId, callbacks) {
        const table = document.getElementById(tableId);
        const selectAll = document.getElementById(selectAllId);
        if (!table || !selectAll) return;

        selectAll.addEventListener('change', () => {
            const checked = selectAll.checked;
            table.querySelectorAll(`.${checkboxClass}`).forEach(cb => {
                if (cb.closest('tr').style.display !== 'none') {
                    cb.checked = checked;
                }
            });
            this.updateBulkState(checkboxClass, selectAllId, bulkBarId, bulkCountId);
        });

        table.addEventListener('change', (e) => {
            if (e.target && e.target.classList.contains(checkboxClass)) {
                this.updateBulkState(checkboxClass, selectAllId, bulkBarId, bulkCountId);
            }
        });

        const bar = document.getElementById(bulkBarId);
        if (!bar) return;

        const getSelectedIds = () => Array.from(table.querySelectorAll(`.${checkboxClass}:checked`)).map(cb => cb.dataset.id);

        const deleteBtn = bar.querySelector('[id^="bulkDelete"]');
        if (deleteBtn && callbacks.onDelete) {
            deleteBtn.addEventListener('click', async () => {
                const ids = getSelectedIds();
                if (!ids.length) return;
                if (!confirm(`¿Seguro que desea eliminar los ${ids.length} elementos seleccionados?`)) return;
                try {
                    await callbacks.onDelete(ids);
                } catch (err) {
                    this.showToast(err.message, 'error');
                }
            });
        }

        const activateBtn = bar.querySelector('[id^="bulkActivate"]');
        if (activateBtn && callbacks.onStatus) {
            activateBtn.addEventListener('click', async () => {
                const ids = getSelectedIds();
                if (!ids.length) return;
                try {
                    await callbacks.onStatus(ids, true);
                } catch (err) {
                    this.showToast(err.message, 'error');
                }
            });
        }

        const deactivateBtn = bar.querySelector('[id^="bulkDeactivate"]');
        if (deactivateBtn && callbacks.onStatus) {
            deactivateBtn.addEventListener('click', async () => {
                const ids = getSelectedIds();
                if (!ids.length) return;
                try {
                    await callbacks.onStatus(ids, false);
                } catch (err) {
                    this.showToast(err.message, 'error');
                }
            });
        }
    }

    updateBulkState(checkboxClass, selectAllId, bulkBarId, bulkCountId) {
        const checked = document.querySelectorAll(`.${checkboxClass}:checked`);
        const total = document.querySelectorAll(`.${checkboxClass}`);
        const selectAll = document.getElementById(selectAllId);
        const bar = document.getElementById(bulkBarId);
        const count = document.getElementById(bulkCountId);

        if (selectAll && total.length > 0) {
            selectAll.checked = checked.length > 0 && checked.length === total.length;
            selectAll.indeterminate = checked.length > 0 && checked.length < total.length;
        }

        if (bar && count) {
            if (checked.length > 0) {
                bar.style.display = 'flex';
                count.textContent = `${checked.length} sel.`;
            } else {
                bar.style.display = 'none';
                if (selectAll) selectAll.checked = false;
            }
        }
    }

    showAuthOverlay(message = 'Ingrese con su correo y contraseña o canjee una invitación de 6 horas.') {
        let overlay = document.getElementById('tenantAuthOverlay');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.id = 'tenantAuthOverlay';
            overlay.style.cssText = [
                'position:fixed', 'inset:0', 'background:rgba(10,10,20,0.92)',
                'display:flex', 'align-items:center', 'justify-content:center',
                'z-index:9999', 'backdrop-filter:blur(8px)', 'padding:1rem',
            ].join(';');
            overlay.innerHTML = `
                <div style="background:#101724;border:1px solid rgba(255,255,255,0.12);border-radius:20px;padding:2rem;width:min(560px,100%);box-shadow:0 30px 80px rgba(0,0,0,0.45);">
                    <p style="margin:0 0 0.35rem;color:#9fb3c8;font-size:0.8rem;text-transform:uppercase;letter-spacing:0.08em;">Acceso protegido</p>
                    <h2 style="margin:0 0 0.6rem;color:#f5f7fb;font-size:1.6rem;">Panel del negocio</h2>
                    <p id="tenantAuthMessage" style="margin:0 0 1.25rem;color:#c1cede;line-height:1.5;">${message}</p>
                    <div style="display:flex;gap:0.5rem;margin-bottom:1rem;">
                        <button type="button" class="btn btn-secondary" id="authTabLogin">Ingresar</button>
                        <button type="button" class="btn btn-secondary" id="authTabClaim">Usar invitación</button>
                    </div>
                    <div id="authLoginPanel">
                        <form id="tenantLoginForm">
                            <div class="form-group">
                                <label>Correo</label>
                                <input type="email" id="tenantLoginEmail" required autocomplete="username email">
                            </div>
                            <div class="form-group">
                                <label>Contraseña</label>
                                <input type="password" id="tenantLoginPassword" required autocomplete="current-password">
                            </div>
                            <button type="submit" class="btn btn-primary">Entrar al panel</button>
                        </form>
                    </div>
                    <div id="authClaimPanel" style="display:none;">
                        <form id="tenantClaimForm">
                            <div class="form-group">
                                <label>Token de invitación</label>
                                <input type="text" id="tenantClaimToken" required autocomplete="off">
                            </div>
                            <div class="form-group">
                                <label>Nombre completo</label>
                                <input type="text" id="tenantClaimName" required autocomplete="name">
                            </div>
                            <div class="form-group">
                                <label>Nueva contraseña</label>
                                <input type="password" id="tenantClaimPassword" required autocomplete="new-password">
                            </div>
                            <p class="overview-copy" style="margin-bottom:1rem;">Use una contraseña de 12 o más caracteres con mayúsculas, minúsculas, números y símbolos.</p>
                            <button type="submit" class="btn btn-primary">Activar acceso</button>
                        </form>
                    </div>
                </div>
            `;
            document.body.appendChild(overlay);
            this.bindAuthOverlayEvents();
        } else {
            overlay.style.display = 'flex';
            const msg = document.getElementById('tenantAuthMessage');
            if (msg) msg.textContent = message;
        }

        const inviteToken = new URLSearchParams(window.location.search).get('invite');
        if (inviteToken) {
            this.switchAuthTab('claim');
            const tokenInput = document.getElementById('tenantClaimToken');
            if (tokenInput) tokenInput.value = inviteToken;
        } else {
            this.switchAuthTab('login');
        }
    }

    hideAuthOverlay() {
        const overlay = document.getElementById('tenantAuthOverlay');
        if (overlay) overlay.style.display = 'none';
    }

    focusAuthField() {
        const activeClaim = document.getElementById('authClaimPanel')?.style.display !== 'none';
        const target = activeClaim
            ? document.getElementById('tenantClaimName') || document.getElementById('tenantClaimToken')
            : document.getElementById('tenantLoginEmail');
        target?.focus();
    }

    switchAuthTab(tab) {
        const loginPanel = document.getElementById('authLoginPanel');
        const claimPanel = document.getElementById('authClaimPanel');
        const showClaim = tab === 'claim';
        if (loginPanel) loginPanel.style.display = showClaim ? 'none' : 'block';
        if (claimPanel) claimPanel.style.display = showClaim ? 'block' : 'none';
    }

    bindAuthOverlayEvents() {
        document.getElementById('authTabLogin')?.addEventListener('click', () => {
            this.switchAuthTab('login');
            this.focusAuthField();
        });
        document.getElementById('authTabClaim')?.addEventListener('click', () => {
            this.switchAuthTab('claim');
            this.focusAuthField();
        });

        document.getElementById('tenantLoginForm')?.addEventListener('submit', async (event) => {
            event.preventDefault();
            try {
                const session = await this.fetch('/tenant-auth/login', {
                    method: 'POST',
                    body: JSON.stringify({
                        email: document.getElementById('tenantLoginEmail').value,
                        password: document.getElementById('tenantLoginPassword').value,
                    }),
                }, false);
                this.currentUser = session.user;
                this.hideAuthOverlay();
                this.renderTenantUserBadge();
                await this.finishAuthenticatedBootstrap();
                this.showToast('Sesión iniciada', 'success');
            } catch (err) {
                this.showToast(err.message, 'error');
            }
        });

        document.getElementById('tenantClaimForm')?.addEventListener('submit', async (event) => {
            event.preventDefault();
            try {
                const result = await this.fetch('/tenant-auth/invites/claim', {
                    method: 'POST',
                    body: JSON.stringify({
                        token: document.getElementById('tenantClaimToken').value,
                        full_name: document.getElementById('tenantClaimName').value,
                        password: document.getElementById('tenantClaimPassword').value,
                    }),
                }, false);
                this.currentUser = result.user;
                this.hideAuthOverlay();
                this.renderTenantUserBadge();
                await this.finishAuthenticatedBootstrap();
                window.history.replaceState({}, document.title, window.location.pathname);
                this.showToast('Acceso activado', 'success');
            } catch (err) {
                this.showToast(err.message, 'error');
            }
        });
    }

    setupNavigation() {
        document.querySelectorAll('.nav-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                this.goToSection(link.dataset.section);
            });
        });
        this.updatePageHeader('dashboard');
    }

    setupQuickActions() {
        document.querySelectorAll('[data-go-section]').forEach((button) => {
            button.addEventListener('click', () => {
                this.goToSection(button.dataset.goSection);
            });
        });
    }

    goToSection(sectionName) {
        document.querySelectorAll('.nav-link').forEach((link) => {
            link.classList.toggle('active', link.dataset.section === sectionName);
        });

        document.querySelectorAll('.section').forEach((section) => {
            section.classList.toggle('active', section.id === sectionName);
        });

        this.updatePageHeader(sectionName);
    }

    updatePageHeader(sectionName) {
        const meta = this.sectionMeta[sectionName] || this.sectionMeta.dashboard;
        document.getElementById('pageKicker').textContent = meta.kicker;
        document.getElementById('pageTitle').textContent = meta.title;
        document.getElementById('pageDescription').textContent = meta.description;
    }

    setupForms() {
        this.renderBusinessHoursEditor();
        this.setupProfileDraftState();
        document.querySelectorAll('[data-hours-preset]').forEach((button) => {
            button.addEventListener('click', () => {
                this.applyBusinessHoursPreset(button.dataset.hoursPreset);
                this.markProfileDirty();
            });
        });
        document.getElementById('profileForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const saveButton = document.getElementById('profileSaveBtn');
            try {
                this.setProfileSaveState('saving');
                this.setButtonBusy(saveButton, true, 'Guardando...');
                const data = {
                    name: document.getElementById('profileName').value,
                    email: document.getElementById('profileEmail').value || null,
                    phone: document.getElementById('profilePhone').value || null,
                    address: document.getElementById('profileAddress').value || null,
                    city: document.getElementById('profileCity').value || null,
                    website: document.getElementById('profileWebsite').value || null,
                    logo_url: document.getElementById('profileLogo').value || null,
                    business_hours: this.readBusinessHoursEditor(),
                    estimated_attention_minutes: document.getElementById('profileEstimatedAttentionMinutes').value.trim()
                        ? parseInt(document.getElementById('profileEstimatedAttentionMinutes').value, 10)
                        : null,
                    promotions_config: this.getFeaturedSectionState('promotions', this.profileData.promotions_config || {}),
                    best_sellers_config: this.getFeaturedSectionState('bestSellers', this.profileData.best_sellers_config || {}),
                    favorites_config: this.getFeaturedSectionState('favorites', this.profileData.favorites_config || {}),
                    human_agent_available: document.getElementById('profileHumanAvailable').checked,
                };
                await this.fetch('/business/me/profile', { method: 'PUT', body: JSON.stringify(data) });
                this.showToast('Datos del negocio actualizados', 'success');
                await this.loadProfile();
                this.setProfileSaveState('saved');
            } catch (err) {
                this.showToast(err.message, 'error');
                this.setProfileSaveState('pending', 'Revise los datos y vuelva a intentar.');
            } finally {
                this.setButtonBusy(saveButton, false, 'Guardar cambios');
            }
        });
    }

    setupProfileDraftState() {
        const form = document.getElementById('profileForm');
        if (!form) return;
        form.querySelectorAll('input, textarea, select').forEach((field) => {
            field.addEventListener('input', () => this.markProfileDirty());
            field.addEventListener('change', () => this.markProfileDirty());
        });
        this.setProfileSaveState('idle');
    }

    markProfileDirty() {
        this.setProfileSaveState('pending');
    }

    setProfileSaveState(state, customText = '') {
        const element = document.getElementById('profileSaveState');
        if (!element) return;
        element.classList.remove('pending', 'saving', 'saved');
        const copy = {
            idle: 'Sin cambios pendientes.',
            pending: 'Tiene cambios sin guardar.',
            saving: 'Guardando cambios...',
            saved: 'Cambios guardados correctamente.',
        };
        element.textContent = customText || copy[state] || copy.idle;
        if (state !== 'idle') {
            element.classList.add(state);
        }
    }

    setButtonBusy(button, isBusy, busyLabel) {
        if (!button) return;
        if (!button.dataset.defaultLabel) {
            button.dataset.defaultLabel = button.textContent;
        }
        button.disabled = isBusy;
        button.textContent = isBusy ? busyLabel : button.dataset.defaultLabel;
    }

    setupModals() {
        document.getElementById('modalClose').addEventListener('click', () => {
            document.getElementById('modal').classList.remove('active');
        });

        document.getElementById('addProductBtn').addEventListener('click', () => {
            this.showProductModal();
        });

        document.getElementById('exportProductsBtn').addEventListener('click', () => {
            this.exportProducts();
        });

        document.getElementById('exportTemplateBtn').addEventListener('click', () => {
            this.exportTemplate();
        });

        document.getElementById('importProductsInput').addEventListener('change', (e) => {
            const file = e.target.files[0];
            e.target.value = '';
            this.importProducts(file);
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
            const [users, convs, attentionTime] = await Promise.all([
                this.fetch('/business/me/users/count'),
                this.fetch('/business/me/conversations/count'),
                this.fetch('/business/me/attention-time'),
            ]);
            document.getElementById('userCount').textContent = users.count;
            document.getElementById('convCount').textContent = convs.count;
            document.getElementById('realDailyAverageMinutes').textContent = attentionTime.real_daily_average_minutes ?? '—';
            this.renderOperationalSummary();
        } catch (err) {
            console.error('Dashboard load failed:', err);
        }
    }

    async loadProfile() {
        try {
            const profile = await this.fetch('/business/me/profile');
            this.profileData = profile;
            document.getElementById('businessName').textContent = profile.name;
            document.getElementById('profileName').value = profile.name || '';
            document.getElementById('profileEmail').value = profile.email || '';
            document.getElementById('profilePhone').value = profile.phone || '';
            document.getElementById('profileAddress').value = profile.address || '';
            document.getElementById('profileCity').value = profile.city || '';
            document.getElementById('profileWebsite').value = profile.website || '';
            document.getElementById('profileLogo').value = profile.logo_url || '';
            document.getElementById('profileEstimatedAttentionMinutes').value = profile.estimated_attention_minutes ?? '';
            this.renderBusinessHoursEditor(profile.business_hours || {});
            document.getElementById('profileHumanAvailable').checked = !!profile.human_agent_available;
            document.getElementById('statusBadge').textContent = profile.status === 'active' ? 'Negocio activo' : 'Revisión pendiente';
            document.getElementById('dashboardGreeting').textContent = `Revise ${profile.name || 'su negocio'} sin complicaciones`;
            document.getElementById('businessName').textContent = profile.name || 'Negocio sin nombre';
            this.renderFeaturedContentEditor(profile);
            this.renderOperationalSummary();
        } catch (err) {
            console.error('Profile load failed:', err);
        }
    }

    async loadProducts() {
        try {
            const products = await this.fetch('/business/me/products?limit=100');
            this.products = products;
            const tbody = document.getElementById('productsBody');
            tbody.innerHTML = '';
            if (products.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="8" class="empty-state">Todavía no hay productos cargados. Agregue el primero para que su catálogo quede visible.</td>
                    </tr>
                `;
            }
            products.forEach(p => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td><input type="checkbox" class="product-select-checkbox" data-id="${p.id}"></td>
                    <td>${p.name}</td>
                    <td>${p.category || '-'}</td>
                    <td>${p.format || '-'}</td>
                    <td>${p.price ? '$' + p.price.toLocaleString() : '-'}</td>
                    <td>${p.stock}</td>
                    <td><span class="status-pill ${p.is_available ? 'available' : 'unavailable'}">${p.is_available ? 'Disponible' : 'No disponible'}</span></td>
                    <td class="table-actions">
                        <button class="btn btn-sm btn-secondary" onclick="app.editProduct('${p.id}')">Editar</button>
                        <button class="btn btn-sm btn-danger" onclick="app.deleteProduct('${p.id}')">Eliminar</button>
                    </td>
                `;
                tbody.appendChild(tr);
            });
            document.getElementById('productCount').textContent = products.length;
            this.renderFeaturedContentEditor(this.profileData || {});
            this.renderOperationalSummary();
            this.applyTableFilter('productsFilterInput', 'productsBody');
            this.updateBulkState('product-select-checkbox', 'selectAllProducts', 'productsBulkBar', 'productsBulkCount');
        } catch (err) {
            console.error('Products load failed:', err);
        }
    }

    async loadKB() {
        try {
            const entries = await this.fetch('/business/me/kb?limit=100');
            this.kbEntries = entries;
            const tbody = document.getElementById('kbBody');
            tbody.innerHTML = '';
            if (entries.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="6" class="empty-state">Todavía no hay respuestas guardadas. Agregue una para resolver preguntas frecuentes con más rapidez.</td>
                    </tr>
                `;
            }
            entries.forEach(e => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td><input type="checkbox" class="kb-select-checkbox" data-id="${e.id}"></td>
                    <td>${e.category}</td>
                    <td>${e.title}</td>
                    <td>${e.content.substring(0, 50)}...</td>
                    <td><span class="status-pill ${e.is_active ? 'available' : 'unavailable'}">${e.is_active ? 'Activa' : 'Inactiva'}</span></td>
                    <td class="table-actions">
                        <button class="btn btn-sm btn-secondary" onclick="app.editKB('${e.id}')">Editar</button>
                        <button class="btn btn-sm btn-danger" onclick="app.deleteKB('${e.id}')">Eliminar</button>
                    </td>
                `;
                tbody.appendChild(tr);
            });
            document.getElementById('kbCount').textContent = entries.length;
            this.renderOperationalSummary();
            this.applyTableFilter('kbFilterInput', 'kbBody');
            this.updateBulkState('kb-select-checkbox', 'selectAllKb', 'kbBulkBar', 'kbBulkCount');
        } catch (err) {
            console.error('KB load failed:', err);
        }
    }

    async loadChannels() {
        try {
            const channels = await this.fetch('/business/me/channels');
            const container = document.getElementById('channelsList');
            container.innerHTML = '';
            if (channels.length === 0) {
                container.innerHTML = '<p class="text-muted">Todavía no hay canales conectados. Cuando se active uno, aparecerá aquí.</p>';
                this.renderOperationalSummary();
                return;
            }
            channels.forEach(c => {
                const card = document.createElement('div');
                card.className = 'channel-card';
                card.innerHTML = `
                    <h4>${c.platform}</h4>
                    <p>Canal conectado: ${c.channel_identifier}</p>
                `;
                container.appendChild(card);
            });
            this.renderOperationalSummary();
        } catch (err) {
            console.error('Channels load failed:', err);
        }
    }

    async searchKB() {
        const query = document.getElementById('kbSearchInput').value;
        const feedback = document.getElementById('kbSearchFeedback');
        if (!query) {
            if (feedback) {
                feedback.textContent = 'Escriba una palabra o frase para buscar entre sus respuestas guardadas.';
                feedback.className = 'search-feedback warning';
            }
            return;
        }
        try {
            const result = await this.fetch('/business/me/kb/search', {
                method: 'POST',
                body: JSON.stringify({ query, top_k: 10 }),
            });
            this.showToast(`${result.count} resultados encontrados`, 'success');
            if (feedback) {
                feedback.textContent = result.count > 0
                    ? `Se encontraron ${result.count} resultados para "${query}".`
                    : `No encontramos resultados para "${query}". Puede probar con otra palabra.`;
                feedback.className = `search-feedback ${result.count > 0 ? 'success' : 'warning'}`;
            }
        } catch (err) {
            this.showToast(err.message, 'error');
            if (feedback) {
                feedback.textContent = err.message;
                feedback.className = 'search-feedback warning';
            }
        }
    }

    showProductModal(product = null) {
        const modal = document.getElementById('modal');
        const title = document.getElementById('modalTitle');
        const body = document.getElementById('modalBody');

        const categoryOptions = this.categories.map(c => `
            <option value="${c.name}" ${product?.category === c.name ? 'selected' : ''}>${c.name}</option>
        `).join('');

        title.textContent = product ? 'Editar producto' : 'Agregar producto';
        body.innerHTML = `
            <p class="modal-copy">Complete solo los datos que sus clientes necesitan para entender qué vende y en qué condiciones está disponible.</p>
            <form id="productForm">
                <div class="form-group">
                    <label>Nombre</label>
                    <input type="text" id="prodName" value="${product?.name || ''}" required>
                    <p class="field-note">Use un nombre claro y reconocible para evitar dudas al vender.</p>
                </div>
                <div class="form-group">
                    <label>Descripción</label>
                    <textarea id="prodDesc">${product?.description || ''}</textarea>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label>Precio</label>
                        <input type="number" id="prodPrice" value="${product?.price || ''}" step="0.01">
                        <p class="field-note">Si todavía no desea publicarlo, puede dejarlo vacío temporalmente.</p>
                    </div>
                    <div class="form-group">
                        <label>Stock</label>
                        <input type="number" id="prodStock" value="${product?.stock || 0}">
                        <p class="field-note">Use cero cuando no tenga unidades disponibles.</p>
                    </div>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label>Formato <small style="opacity:.6">(ej: 500cc, caja x12, unidad)</small></label>
                        <input type="text" id="prodFormat" value="${product?.format || ''}" placeholder="ej: 750ml, caja x6, unidad">
                    </div>
                    <div class="form-group">
                        <label>Unidad de medida</label>
                        <input type="text" id="prodUnit" value="${product?.unit_of_measure || 'un'}" placeholder="un, kg, lt">
                    </div>
                </div>
                <div class="form-group">
                    <label>Categoría</label>
                    <select id="prodCategory" class="form-control">${categoryOptions}</select>
                    <p class="field-note">Elija el grupo que mejor ayude a ordenar el catálogo.</p>
                </div>
                <button type="submit" class="btn btn-primary">Guardar producto</button>
            </form>
        `;

        document.getElementById('productForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const saveButton = e.currentTarget.querySelector('button[type="submit"]');
            const data = {
                name: document.getElementById('prodName').value,
                description: document.getElementById('prodDesc').value || null,
                price: parseFloat(document.getElementById('prodPrice').value) || null,
                stock: parseInt(document.getElementById('prodStock').value) || 0,
                format: document.getElementById('prodFormat').value || null,
                unit_of_measure: document.getElementById('prodUnit').value || 'un',
                category: document.getElementById('prodCategory').value || null,
                is_available: true,
            };
            try {
                this.setButtonBusy(saveButton, true, 'Guardando...');
                if (product) {
                    await this.fetch(`/business/me/products/${product.id}`, { method: 'PUT', body: JSON.stringify(data) });
                } else {
                    await this.fetch('/business/me/products', { method: 'POST', body: JSON.stringify(data) });
                }
                this.showToast('Producto guardado', 'success');
                modal.classList.remove('active');
                await this.loadProducts();
            } catch (err) {
                this.showToast(err.message, 'error');
            } finally {
                this.setButtonBusy(saveButton, false, 'Guardar producto');
            }
        });

        modal.classList.add('active');
    }

    async editProduct(id) {
        const modal = document.getElementById('modal');
        const title = document.getElementById('modalTitle');
        const body = document.getElementById('modalBody');
        title.textContent = 'Editar producto';
        body.innerHTML = `
            <div class="spinner-container">
                <div class="spinner"></div>
                <p>Cargando datos del producto...</p>
            </div>
        `;
        modal.classList.add('active');

        try {
            const products = await this.fetch('/business/me/products?limit=100');
            const product = products.find(p => p.id === id);
            if (product) {
                this.showProductModal(product);
            } else {
                this.showToast('Producto no encontrado', 'error');
                modal.classList.remove('active');
            }
        } catch (err) {
            this.showToast(err.message, 'error');
            modal.classList.remove('active');
        }
    }

    async deleteProduct(id) {
        const products = await this.fetch('/business/me/products?limit=100');
        const product = products.find((item) => item.id === id);
        if (!confirm(`¿Desea eliminar ${product?.name || 'este producto'}? Esta acción quitará el producto de su catálogo visible.`)) return;
        try {
            await this.fetch(`/business/me/products/${id}`, { method: 'DELETE' });
            this.showToast('Producto eliminado', 'success');
            await this.loadProducts();
        } catch (err) {
            this.showToast(err.message, 'error');
        }
    }

    async exportProducts() {
        try {
            const response = await fetch(`${API_BASE}/business/me/products/export`, {
                credentials: 'include',
                headers: this.headers,
            });
            if (!response.ok) throw new Error('No fue posible exportar el catálogo');
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'productos.xlsx';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            this.showToast('Catálogo descargado', 'success');
        } catch (err) {
            this.showToast('Error al exportar: ' + err.message, 'error');
        }
    }

    async exportTemplate() {
        try {
            const response = await fetch(`${API_BASE}/business/me/products/export/template`, {
                credentials: 'include',
                headers: this.headers,
            });
            if (!response.ok) throw new Error('No fue posible descargar la plantilla');
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'plantilla_productos.xlsx';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            this.showToast('Plantilla descargada', 'success');
        } catch (err) {
            this.showToast('Error al descargar plantilla: ' + err.message, 'error');
        }
    }

    async importProducts(file) {
        if (!file) return;
        if (!file.name.endsWith('.xlsx')) {
            this.showToast('Solo se aceptan archivos .xlsx', 'error');
            return;
        }
        try {
            const formData = new FormData();
            formData.append('file', file);
            const response = await fetch(`${API_BASE}/business/me/products/import`, {
                method: 'POST',
                credentials: 'include',
                headers: this.headers,
                body: formData,
            });
            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.detail || 'No fue posible cargar el archivo');
            }
            const result = await response.json();
            const message = result.errors > 0
                ? `Carga terminada con observaciones: ${result.created} nuevos, ${result.updated} actualizados y ${result.errors} por revisar.`
                : `Carga completada: ${result.created} productos nuevos y ${result.updated} actualizados.`;
            this.showToast(message, result.errors > 0 ? 'error' : 'success');
            await this.loadProducts();
        } catch (err) {
            this.showToast('Error al importar: ' + err.message, 'error');
        }
    }

    showKBModal(entry = null) {
        const modal = document.getElementById('modal');
        const title = document.getElementById('modalTitle');
        const body = document.getElementById('modalBody');

        title.textContent = entry ? 'Editar respuesta guardada' : 'Agregar respuesta';
        body.innerHTML = `
            <p class="modal-copy">Guarde aquí respuestas generales que conviene repetir con frecuencia, sin depender del stock o del precio del momento.</p>
            <form id="kbForm">
                <div class="form-group">
                    <label>Tema</label>
                    <input type="text" id="kbCategory" value="${entry?.category || ''}" required>
                    <p class="field-note">Ejemplos: horarios, pagos, entregas o cambios.</p>
                </div>
                <div class="form-group">
                    <label>Título</label>
                    <input type="text" id="kbTitle" value="${entry?.title || ''}" required>
                </div>
                <div class="form-group">
                    <label>Respuesta</label>
                    <textarea id="kbContent" rows="5" required>${entry?.content || ''}</textarea>
                </div>
                <button type="submit" class="btn btn-primary">Guardar respuesta</button>
            </form>
        `;

        document.getElementById('kbForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const saveButton = e.currentTarget.querySelector('button[type="submit"]');
            const data = {
                category: document.getElementById('kbCategory').value,
                title: document.getElementById('kbTitle').value,
                content: document.getElementById('kbContent').value,
            };
            try {
                this.setButtonBusy(saveButton, true, 'Guardando...');
                if (entry) {
                    await this.fetch(`/business/me/kb/${entry.id}`, { method: 'PUT', body: JSON.stringify(data) });
                } else {
                    await this.fetch('/business/me/kb', { method: 'POST', body: JSON.stringify(data) });
                }
                this.showToast('Respuesta guardada', 'success');
                modal.classList.remove('active');
                await this.loadKB();
            } catch (err) {
                this.showToast(err.message, 'error');
            } finally {
                this.setButtonBusy(saveButton, false, 'Guardar respuesta');
            }
        });

        modal.classList.add('active');
    }

    async editKB(id) {
        const modal = document.getElementById('modal');
        const title = document.getElementById('modalTitle');
        const body = document.getElementById('modalBody');
        title.textContent = 'Editar respuesta';
        body.innerHTML = `
            <div class="spinner-container">
                <div class="spinner"></div>
                <p>Cargando datos de la respuesta...</p>
            </div>
        `;
        modal.classList.add('active');

        try {
            const entries = await this.fetch('/business/me/kb?limit=100');
            const entry = entries.find(e => e.id === id);
            if (entry) {
                this.showKBModal(entry);
            } else {
                this.showToast('Respuesta no encontrada', 'error');
                modal.classList.remove('active');
            }
        } catch (err) {
            this.showToast(err.message, 'error');
            modal.classList.remove('active');
        }
    }

    async deleteKB(id) {
        const entries = await this.fetch('/business/me/kb?limit=100');
        const entry = entries.find((item) => item.id === id);
        if (!confirm(`¿Desea eliminar "${entry?.title || 'esta respuesta'}"? Ya no estará disponible como referencia para el negocio.`)) return;
        try {
            await this.fetch(`/business/me/kb/${id}`, { method: 'DELETE' });
            this.showToast('Respuesta eliminada', 'success');
            await this.loadKB();
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


    showToast(message, type = 'success') {
        const container = document.getElementById('toastContainer');
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.textContent = message;
        container.appendChild(toast);
        setTimeout(() => toast.remove(), 3000);
    }

    renderBusinessHoursEditor(hours = {}) {
        const editor = document.getElementById('profileHoursEditor');
        const summary = document.getElementById('profileHoursSummary');
        if (!editor || !summary) return;

        editor.innerHTML = this.weekDays.map(({ id, label, storageKey }) => {
            const value = this.normalizeBusinessHours(
                hours[storageKey] || hours[id] || hours[label] || hours[label.toLowerCase()] || {}
            );
            const isClosed = value.closed;
            const openValue = value.open || '10:00';
            const closeValue = value.close || '22:00';
            return `
                <div class="hours-row" data-day="${id}">
                    <div class="hours-day">${label}</div>
                    <div class="hours-time-group">
                        <input type="time" id="hours-${id}-open" aria-label="Abre ${label}" value="${openValue}" ${isClosed ? 'disabled' : ''}>
                    </div>
                    <div class="hours-time-group">
                        <input type="time" id="hours-${id}-close" aria-label="Cierra ${label}" value="${closeValue}" ${isClosed ? 'disabled' : ''}>
                    </div>
                    <label class="hours-closed">
                        <input type="checkbox" id="hours-${id}-closed" ${isClosed ? 'checked' : ''}>
                        Cerrado
                    </label>
                </div>
            `;
        }).join('');

        this.weekDays.forEach(({ id }) => {
            const closedInput = document.getElementById(`hours-${id}-closed`);
            const openInput = document.getElementById(`hours-${id}-open`);
            const closeInput = document.getElementById(`hours-${id}-close`);
            if (!closedInput || !openInput || !closeInput) return;
            closedInput.addEventListener('change', () => {
                const isClosed = closedInput.checked;
                openInput.disabled = isClosed;
                closeInput.disabled = isClosed;
                this.updateBusinessHoursSummary();
            });
            openInput.addEventListener('input', () => this.updateBusinessHoursSummary());
            closeInput.addEventListener('input', () => this.updateBusinessHoursSummary());
        });

        this.updateBusinessHoursSummary();
    }

    normalizeBusinessHours(dayConfig = {}) {
        if (!dayConfig || typeof dayConfig !== 'object') {
            return { open: '', close: '', closed: false };
        }
        return {
            open: typeof dayConfig.open === 'string' ? dayConfig.open : '',
            close: typeof dayConfig.close === 'string' ? dayConfig.close : '',
            closed: Boolean(dayConfig.closed) || dayConfig.open === null || dayConfig.close === null,
        };
    }

    applyBusinessHoursPreset(presetName) {
        const presets = {
            weekdays: {
                Lunes: { open: '10:00', close: '22:00' },
                Martes: { open: '10:00', close: '22:00' },
                Miércoles: { open: '10:00', close: '22:00' },
                Jueves: { open: '10:00', close: '22:00' },
                Viernes: { open: '10:00', close: '22:00' },
                Sábado: { closed: true, open: null, close: null },
                Domingo: { closed: true, open: null, close: null },
            },
            weekdays_plus_sat: {
                Lunes: { open: '10:00', close: '22:00' },
                Martes: { open: '10:00', close: '22:00' },
                Miércoles: { open: '10:00', close: '22:00' },
                Jueves: { open: '10:00', close: '22:00' },
                Viernes: { open: '10:00', close: '22:00' },
                Sábado: { open: '10:00', close: '20:00' },
                Domingo: { closed: true, open: null, close: null },
            },
            daily: {
                Lunes: { open: '10:00', close: '22:00' },
                Martes: { open: '10:00', close: '22:00' },
                Miércoles: { open: '10:00', close: '22:00' },
                Jueves: { open: '10:00', close: '22:00' },
                Viernes: { open: '10:00', close: '22:00' },
                Sábado: { open: '10:00', close: '22:00' },
                Domingo: { open: '10:00', close: '22:00' },
            },
            closed: {
                Lunes: { closed: true, open: null, close: null },
                Martes: { closed: true, open: null, close: null },
                Miércoles: { closed: true, open: null, close: null },
                Jueves: { closed: true, open: null, close: null },
                Viernes: { closed: true, open: null, close: null },
                Sábado: { closed: true, open: null, close: null },
                Domingo: { closed: true, open: null, close: null },
            },
        };

        this.renderBusinessHoursEditor(presets[presetName] || {});
    }

    readBusinessHoursEditor() {
        const hours = {};
        this.weekDays.forEach(({ id, storageKey }) => {
            const closed = document.getElementById(`hours-${id}-closed`)?.checked ?? false;
            const open = document.getElementById(`hours-${id}-open`)?.value || '';
            const close = document.getElementById(`hours-${id}-close`)?.value || '';
            hours[storageKey] = closed
                ? { closed: true, open: null, close: null }
                : { open, close };
        });
        return hours;
    }

    updateBusinessHoursSummary() {
        const summary = document.getElementById('profileHoursSummary');
        if (!summary) return;
        const parts = this.weekDays.map(({ id, label }) => {
            const closed = document.getElementById(`hours-${id}-closed`)?.checked ?? false;
            if (closed) return `${label}: cerrado`;
            const open = document.getElementById(`hours-${id}-open`)?.value || '--:--';
            const close = document.getElementById(`hours-${id}-close`)?.value || '--:--';
            return `${label}: ${open} a ${close}`;
        });
        summary.innerHTML = `<strong>Vista rápida:</strong> ${parts.join(' · ')}`;
    }

    async loadCategories() {
        try {
            const categories = await this.fetch('/categories');
            this.categories = categories;
            const tbody = document.getElementById('categoriesBody');
            if (!tbody) return;
            tbody.innerHTML = '';
            if (categories.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="3" class="empty-state">Todavía no hay grupos creados. Puede comenzar con uno simple para ordenar su catálogo.</td>
                    </tr>
                `;
            }
            categories.forEach(c => {
                const tr = document.createElement('tr');
                const actions = c.is_system 
                    ? `<span class="status-pill available">Fijo</span>` 
                    : `
                        <button class="btn btn-sm btn-secondary" onclick="app.editCategory('${c.name}')">Editar</button>
                        <button class="btn btn-sm btn-danger" onclick="app.deleteCategory('${c.name}')">Eliminar</button>
                    `;
                tr.innerHTML = `
                    <td><strong>${c.name}</strong></td>
                    <td><code>${c.slug}</code></td>
                    <td class="table-actions">${actions}</td>
                `;
                tbody.appendChild(tr);
            });
            this.applyTableFilter('categoriesFilterInput', 'categoriesBody');
        } catch (err) {
            console.error('Categories load failed:', err);
        }
    }

    showCategoryModal(category = null) {
        const modal = document.getElementById('modal');
        const title = document.getElementById('modalTitle');
        const body = document.getElementById('modalBody');

        title.textContent = category ? 'Editar grupo' : 'Agregar grupo';
        body.innerHTML = `
            <p class="modal-copy">Los grupos sirven para ordenar productos similares. No es necesario crear demasiados.</p>
            <form id="categoryForm">
                <div class="form-group">
                    <label>Nombre del grupo</label>
                    <input type="text" id="catName" value="${category || ''}" required placeholder="Ej: Licores premium">
                    <p class="field-note">Use nombres cortos y fáciles de reconocer.</p>
                </div>
                <button type="submit" class="btn btn-primary">Guardar grupo</button>
            </form>
        `;

        document.getElementById('categoryForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const saveButton = e.currentTarget.querySelector('button[type="submit"]');
            const newName = document.getElementById('catName').value;
            try {
                this.setButtonBusy(saveButton, true, 'Guardando...');
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
                this.showToast('Grupo guardado', 'success');
                modal.classList.remove('active');
                await this.loadCategories();
                await this.loadProducts();
            } catch (err) {
                this.showToast(err.message, 'error');
            } finally {
                this.setButtonBusy(saveButton, false, 'Guardar grupo');
            }
        });

        modal.classList.add('active');
    }

    async deleteCategory(name) {
        if (!confirm(`¿Desea eliminar el grupo '${name}'? Los productos asociados pasarán automáticamente al grupo 'General'.`)) return;
        try {
            await this.fetch(`/categories/${encodeURIComponent(name)}`, { method: 'DELETE' });
            this.showToast('Grupo eliminado', 'success');
            await this.loadCategories();
            await this.loadProducts();
        } catch (err) {
            this.showToast(err.message, 'error');
        }
    }

    editCategory(name) {
        this.showCategoryModal(name);
    }

    renderOperationalSummary() {
        const summary = document.getElementById('dashboardSummary');
        const recommendation = document.getElementById('dashboardRecommendation');
        const checklist = document.getElementById('dashboardChecklist');
        if (!summary || !recommendation) return;

        const profileName = document.getElementById('profileName')?.value?.trim() || document.getElementById('businessName')?.textContent?.trim() || 'su negocio';
        const productCount = Number(document.getElementById('productCount')?.textContent || '0');
        const kbCount = Number(document.getElementById('kbCount')?.textContent || '0');
        const userCount = Number(document.getElementById('userCount')?.textContent || '0');
        const convCount = Number(document.getElementById('convCount')?.textContent || '0');
        const activeChannels = document.querySelectorAll('#channelsList .channel-card').length;

        summary.textContent = `${profileName} registra ${productCount} productos, ${kbCount} respuestas guardadas, ${userCount} personas registradas y ${convCount} conversaciones atendidas.`;
        if (checklist) {
            const items = [];
            items.push(productCount > 0 ? 'El catálogo ya tiene productos cargados.' : 'Falta cargar al menos un producto.');
            items.push(kbCount > 0 ? 'Ya hay respuestas generales guardadas.' : 'Conviene guardar una respuesta sobre horarios, pagos o entregas.');
            items.push(activeChannels > 0 ? 'Hay al menos un canal de atención conectado.' : 'Todavía no hay canales de atención visibles.');
            checklist.innerHTML = items.map((item) => `<li>${item}</li>`).join('');
        }
        this.renderVisualCharts();

        if (productCount === 0) {
            recommendation.textContent = 'Agregue al menos un producto. Es la acción con mayor impacto para evitar respuestas incompletas sobre su catálogo.';
            return;
        }

        if (kbCount === 0) {
            recommendation.textContent = 'Agregue una respuesta útil con horarios, pagos o zonas de entrega. Eso reduce consultas repetidas y mejora la atención.';
            return;
        }

        if (activeChannels === 0) {
            recommendation.textContent = 'Revise los canales de atención. Si no hay ninguno conectado, sus clientes no podrán comunicarse por este medio.';
            return;
        }

        recommendation.textContent = 'La base operativa está lista. Revise solo lo que cambie en su catálogo, horarios o información de atención.';
    }

    renderVisualCharts() {
        const catChart = document.getElementById('chartCategoryDistribution');
        if (catChart) {
            const products = this.products || [];
            if (products.length === 0) {
                catChart.innerHTML = '<p class="text-muted" style="font-size:0.85rem;">No hay productos para graficar.</p>';
            } else {
                const counts = {};
                products.forEach(p => {
                    const cat = p.category || 'General';
                    counts[cat] = (counts[cat] || 0) + 1;
                });
                const total = products.length;
                const sortedCats = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 4);
                catChart.innerHTML = sortedCats.map(([cat, count]) => {
                    const pct = Math.round((count / total) * 100);
                    return `
                        <div style="display:flex; flex-direction:column; gap:0.2rem;">
                            <div style="display:flex; justify-content:space-between; font-size:0.85rem; color:#cbd5e1;">
                                <span style="font-weight:500; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; max-width:70%;">${cat}</span>
                                <span><strong>${count}</strong> (${pct}%)</span>
                            </div>
                            <div style="width:100%; background:#2a2a4a; border-radius:6px; height:8px; overflow:hidden;">
                                <div style="width:${pct}%; background:linear-gradient(90deg, #6366f1, #a855f7); height:100%; transition:width 0.5s ease;"></div>
                            </div>
                        </div>
                    `;
                }).join('');
            }
        }

        const availChart = document.getElementById('chartAvailability');
        if (availChart) {
            const products = this.products || [];
            if (products.length === 0) {
                availChart.innerHTML = '<p class="text-muted" style="font-size:0.85rem;">No hay productos para evaluar disponibilidad.</p>';
            } else {
                const availCount = products.filter(p => p.is_available).length;
                const unavailCount = products.length - availCount;
                const availPct = Math.round((availCount / products.length) * 100);
                const unavailPct = 100 - availPct;
                const totalStock = products.reduce((sum, p) => sum + (Number(p.stock) || 0), 0);
                availChart.innerHTML = `
                    <div style="display:flex; justify-content:space-between; align-items:center; font-size:0.85rem;">
                        <span style="color:#10b981; font-weight:600;">● Disponibles: ${availCount} (${availPct}%)</span>
                        <span style="color:#ef4444; font-weight:600;">● No disp.: ${unavailCount} (${unavailPct}%)</span>
                    </div>
                    <div style="width:100%; background:#2a2a4a; border-radius:8px; height:12px; display:flex; overflow:hidden;">
                        <div style="width:${availPct}%; background:#10b981; height:100%; transition:width 0.5s ease;" title="Disponibles: ${availPct}%"></div>
                        <div style="width:${unavailPct}%; background:#ef4444; height:100%; transition:width 0.5s ease;" title="No disponibles: ${unavailPct}%"></div>
                    </div>
                    <div style="margin-top:0.3rem; padding:0.6rem; background:#1e1e30; border-radius:8px; font-size:0.85rem; color:#94a3b8; display:flex; justify-content:space-between;">
                        <span>Inventario total en stock:</span>
                        <strong style="color:#f1f5f9;">${totalStock.toLocaleString()} unidades</strong>
                    </div>
                `;
            }
        }

        const kbChart = document.getElementById('chartKbCoverage');
        if (kbChart) {
            const entries = this.kbEntries || [];
            if (entries.length === 0) {
                kbChart.innerHTML = '<p class="text-muted" style="font-size:0.85rem;">Aún no hay respuestas guardadas en la base de conocimiento.</p>';
            } else {
                const activeCount = entries.filter(e => e.is_active).length;
                const activePct = Math.round((activeCount / entries.length) * 100);
                const categories = new Set(entries.map(e => e.category || 'General')).size;
                kbChart.innerHTML = `
                    <div style="display:flex; flex-direction:column; gap:0.6rem;">
                        <div style="display:flex; justify-content:space-between; font-size:0.85rem; color:#cbd5e1;">
                            <span>Respuestas Activas</span>
                            <strong>${activeCount} de ${entries.length} (${activePct}%)</strong>
                        </div>
                        <div style="width:100%; background:#2a2a4a; border-radius:6px; height:8px; overflow:hidden;">
                            <div style="width:${activePct}%; background:linear-gradient(90deg, #3b82f6, #06b6d4); height:100%; transition:width 0.5s ease;"></div>
                        </div>
                        <div style="display:flex; justify-content:space-between; align-items:center; margin-top:0.2rem; font-size:0.85rem; color:#94a3b8;">
                            <span>Temas / Categorías cubiertas:</span>
                            <span class="status-pill available" style="font-size:0.75rem;">${categories} temas</span>
                        </div>
                    </div>
                `;
            }
        }
    }

    setupPreview() {
        const form = document.getElementById('previewForm');
        const input = document.getElementById('previewInput');
        const messages = document.getElementById('previewMessages');
        const typing = document.getElementById('previewTyping');
        const clearBtn = document.getElementById('clearPreviewBtn');

        if (!form || !input || !messages) return;

        if (clearBtn) {
            clearBtn.addEventListener('click', () => {
                messages.innerHTML = `
                    <div class="chat-msg chat-msg--bot" style="align-self:flex-start; max-width:80%; background:#1e1e30; color:#e2e8f0; padding:0.8rem 1.2rem; border-radius:12px 12px 12px 0; border:1px solid #2a2a4a; font-size:0.9rem; line-height:1.4;">
                        ¡Hola! Soy el asistente de prueba de su negocio. ¿En qué le puedo ayudar hoy? Puede preguntarme por productos, precios, horarios o stock.
                    </div>
                `;
            });
        }

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const text = input.value.trim();
            if (!text || !this.currentUser) return;

            input.value = '';
            const userDiv = document.createElement('div');
            userDiv.className = 'chat-msg chat-msg--user';
            userDiv.style.cssText = 'align-self:flex-end; max-width:80%; background:#4f46e5; color:#fff; padding:0.8rem 1.2rem; border-radius:12px 12px 0 12px; font-size:0.9rem; line-height:1.4;';
            userDiv.textContent = text;
            messages.appendChild(userDiv);
            messages.scrollTop = messages.scrollHeight;

            if (typing) typing.style.display = 'block';

            try {
                const res = await this.fetch('/chat', {
                    method: 'POST',
                    body: JSON.stringify({
                        user_id: String(this.currentUser.id),
                        platform: 'web',
                        message: text,
                        session_id: `preview-${this.currentUser.id}`
                    })
                });
                
                const botDiv = document.createElement('div');
                botDiv.className = 'chat-msg chat-msg--bot';
                botDiv.style.cssText = 'align-self:flex-start; max-width:80%; background:#1e1e30; color:#e2e8f0; padding:0.8rem 1.2rem; border-radius:12px 12px 12px 0; border:1px solid #2a2a4a; font-size:0.9rem; line-height:1.4; white-space:pre-wrap;';
                botDiv.textContent = res.response || 'El agente no retornó respuesta.';
                messages.appendChild(botDiv);
            } catch (err) {
                const errDiv = document.createElement('div');
                errDiv.className = 'chat-msg chat-msg--error';
                errDiv.style.cssText = 'align-self:flex-start; max-width:80%; background:#7f1d1d; color:#fecaca; padding:0.8rem 1.2rem; border-radius:12px; font-size:0.85rem; line-height:1.4; border:1px solid #ef4444;';
                errDiv.textContent = `Error al consultar al agente: ${err.message}`;
                messages.appendChild(errDiv);
            } finally {
                if (typing) typing.style.display = 'none';
                messages.scrollTop = messages.scrollHeight;
            }
        });
    }

    getFeaturedSectionState(sectionKey, fallback = {}) {
        const enabled = document.getElementById(`${sectionKey}Enabled`)?.checked ?? Boolean(fallback.enabled);
        const title = document.getElementById(`${sectionKey}Title`)?.value?.trim() || fallback.title || '';
        const productIds = Array.from(
            document.querySelectorAll(`[data-featured-list="${sectionKey}"] [data-product-id]`)
        ).map((item) => item.dataset.productId);
        const mode = sectionKey === 'bestSellers'
            ? (productIds.length > 0 ? 'manual' : 'automatic')
            : 'manual';
        return { enabled, title, mode, product_ids: productIds };
    }

    renderFeaturedContentEditor(profile = {}) {
        const container = document.getElementById('featuredContentEditor');
        if (!container) return;
        const promotions = profile.promotions_config || {};
        const bestSellers = profile.best_sellers_config || {};
        const favorites = profile.favorites_config || {};
        const productOptions = this.products.length
            ? this.products
                .map((product) => `<option value="${this.escapeHtml(product.id)}">${this.escapeHtml(product.name)}</option>`)
                .join('')
            : '<option value="">Cargue productos para activar la selección</option>';

        container.innerHTML = `
            <article class="featured-block" data-featured-section="promotions">
                <div class="featured-block-header">
                    <div>
                        <p class="card-kicker">Bloque 1</p>
                        <h4>Promociones</h4>
                        <p class="field-note">Muestre primero las ofertas que quiera destacar.</p>
                    </div>
                    <label class="toggle-pill">
                        <input type="checkbox" id="promotionsEnabled" ${promotions.enabled ? 'checked' : ''}>
                        <span>Activo</span>
                    </label>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label class="label-with-help">Título visible
                            <button type="button" class="help-tip" data-tooltip="Texto breve que verá el cliente al abrir la sección." aria-label="Ayuda sobre título de promociones">?</button>
                        </label>
                        <input type="text" id="promotionsTitle" value="${this.escapeHtml(promotions.title || 'Promociones destacadas')}" maxlength="120">
                    </div>
                    <div class="form-group">
                        <label class="label-with-help">Agregar producto
                            <button type="button" class="help-tip" data-tooltip="Seleccione productos del catálogo para incluirlos en este bloque." aria-label="Ayuda sobre selección de promociones">?</button>
                        </label>
                        <div class="inline-actions">
                            <select id="promotionsPicker">${productOptions}</select>
                            <button type="button" class="btn btn-secondary" data-action="add-featured-product" data-section="promotions">Agregar</button>
                        </div>
                    </div>
                </div>
                <input type="hidden" id="promotionsMode" value="manual">
                <div class="featured-list" data-featured-list="promotions"></div>
            </article>
            <article class="featured-block" data-featured-section="bestSellers">
                <div class="featured-block-header">
                    <div>
                        <p class="card-kicker">Bloque 2</p>
                        <h4>Más vendidos</h4>
                        <p class="field-note">Si no agrega productos, se mostrará la selección calculada por ventas reales.</p>
                    </div>
                    <label class="toggle-pill">
                        <input type="checkbox" id="bestSellersEnabled" ${bestSellers.enabled ? 'checked' : ''}>
                        <span>Activo</span>
                    </label>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label class="label-with-help">Título visible
                            <button type="button" class="help-tip" data-tooltip="Texto breve que verá el cliente al abrir la sección." aria-label="Ayuda sobre título de más vendidos">?</button>
                        </label>
                        <input type="text" id="bestSellersTitle" value="${this.escapeHtml(bestSellers.title || 'Más vendidos')}" maxlength="120">
                    </div>
                    <div class="form-group">
                        <label class="label-with-help">Agregar producto
                            <button type="button" class="help-tip" data-tooltip="Seleccione productos para fijarlos manualmente cuando prefiera priorizar una selección editorial." aria-label="Ayuda sobre selección de más vendidos">?</button>
                        </label>
                        <div class="inline-actions">
                            <select id="bestSellersPicker">${productOptions}</select>
                            <button type="button" class="btn btn-secondary" data-action="add-featured-product" data-section="bestSellers">Agregar</button>
                        </div>
                    </div>
                </div>
                <input type="hidden" id="bestSellersMode" value="${bestSellers.product_ids && bestSellers.product_ids.length ? 'manual' : 'automatic'}">
                <div class="featured-list" data-featured-list="bestSellers"></div>
            </article>
            <article class="featured-block" data-featured-section="favorites">
                <div class="featured-block-header">
                    <div>
                        <p class="card-kicker">Bloque 3</p>
                        <h4>Favoritos</h4>
                        <p class="field-note">Productos que el negocio quiere mostrar con prioridad editorial.</p>
                    </div>
                    <label class="toggle-pill">
                        <input type="checkbox" id="favoritesEnabled" ${favorites.enabled ? 'checked' : ''}>
                        <span>Activo</span>
                    </label>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label class="label-with-help">Título visible
                            <button type="button" class="help-tip" data-tooltip="Texto breve que verá el cliente al abrir la sección." aria-label="Ayuda sobre título de favoritos">?</button>
                        </label>
                        <input type="text" id="favoritesTitle" value="${this.escapeHtml(favorites.title || 'Productos favoritos')}" maxlength="120">
                    </div>
                    <div class="form-group">
                        <label class="label-with-help">Agregar producto
                            <button type="button" class="help-tip" data-tooltip="Seleccione productos del catálogo que quiera priorizar en la vista del cliente." aria-label="Ayuda sobre selección de favoritos">?</button>
                        </label>
                        <div class="inline-actions">
                            <select id="favoritesPicker">${productOptions}</select>
                            <button type="button" class="btn btn-secondary" data-action="add-featured-product" data-section="favorites">Agregar</button>
                        </div>
                    </div>
                </div>
                <input type="hidden" id="favoritesMode" value="${favorites.product_ids && favorites.product_ids.length ? 'manual' : 'manual'}">
                <div class="featured-list" data-featured-list="favorites"></div>
            </article>
        `;

        const setList = (sectionKey, productIds) => {
            const list = container.querySelector(`[data-featured-list="${sectionKey}"]`);
            if (!list) return;
            const productsById = new Map(this.products.map((product) => [product.id, product]));
            if (!productIds.length) {
                list.innerHTML = '<p class="field-note">Todavía no hay productos seleccionados.</p>';
                return;
            }
            list.innerHTML = productIds.map((productId) => {
                const product = productsById.get(productId);
                const name = this.escapeHtml(product?.name || 'Producto');
                const meta = product?.price ? `$${Number(product.price).toLocaleString()}` : 'Sin precio';
                return `
                    <span class="chip" data-product-id="${this.escapeHtml(productId)}">
                        <span>${name} <em>${this.escapeHtml(meta)}</em></span>
                        <button type="button" class="chip-remove" data-action="remove-featured-product" data-section="${sectionKey}" data-product-id="${this.escapeHtml(productId)}" aria-label="Quitar producto">×</button>
                    </span>
                `;
            }).join('');
        };

        const promotionsIds = Array.isArray(promotions.product_ids) ? promotions.product_ids : [];
        const bestSellersIds = Array.isArray(bestSellers.product_ids) ? bestSellers.product_ids : [];
        const favoritesIds = Array.isArray(favorites.product_ids) ? favorites.product_ids : [];
        setList('promotions', promotionsIds);
        setList('bestSellers', bestSellersIds);
        setList('favorites', favoritesIds);

        if (!container.dataset.listenersAttached) {
            container.dataset.listenersAttached = 'true';
            container.addEventListener('input', () => this.markProfileDirty());
            container.addEventListener('change', () => this.markProfileDirty());
            container.addEventListener('click', (event) => {
                const button = event.target.closest('[data-action="add-featured-product"]');
                if (button) {
                    const sectionKey = button.dataset.section;
                    const picker = container.querySelector(`#${sectionKey}Picker`);
                    if (!picker || !picker.value) return;
                    const list = container.querySelector(`[data-featured-list="${sectionKey}"]`);
                    const selectedIds = new Set(
                        Array.from(list?.querySelectorAll('[data-product-id]') || []).map((item) => item.dataset.productId)
                    );
                    selectedIds.add(picker.value);
                    setList(sectionKey, Array.from(selectedIds));
                    this.markProfileDirty();
                    return;
                }

                const removeButton = event.target.closest('[data-action="remove-featured-product"]');
                if (removeButton) {
                    const sectionKey = removeButton.dataset.section;
                    const list = container.querySelector(`[data-featured-list="${sectionKey}"]`);
                    const selectedIds = Array.from(
                        list?.querySelectorAll('[data-product-id]') || []
                    )
                        .map((item) => item.dataset.productId)
                        .filter((productId) => productId !== removeButton.dataset.productId);
                    setList(sectionKey, selectedIds);
                    this.markProfileDirty();
                }
            });
        }

        container._setFeaturedList = setList;
    }
}

function bootstrapTenantApp() {
    window.app = new TenantApp();
    window.app.init();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bootstrapTenantApp, { once: true });
} else {
    bootstrapTenantApp();
}
