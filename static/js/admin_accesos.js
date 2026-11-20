(() => {
    const table = document.getElementById('tblAccesos');
    if (!table) return;

    const rows = Array.from(table.querySelectorAll('tbody tr[data-user-id]'));
    const saveButton = document.getElementById('accessSave');
    const discardButton = document.getElementById('accessDiscard');
    const changeCount = document.getElementById('accessChangeCount');
    const loadStatus = document.getElementById('accessLoadStatus');
    const loadStatusText = loadStatus?.querySelector('.app-status__text');
    const summary = document.getElementById('accessSummary');
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
    const states = new Map(rows.map(row => [row, { original: new Map(), saved: false, error: null }]));
    let loaded = false;
    let saving = false;

    function selectsFor(row) {
        return Array.from(row.querySelectorAll('select.perm-select'));
    }

    function isDirty(row) {
        if (!loaded) return false;
        const state = states.get(row);
        return selectsFor(row).some(select => select.value !== state.original.get(select.name));
    }

    function setRowStatus(row, tone, message, canRetry = false) {
        const status = row.querySelector('[data-row-status]');
        const text = row.querySelector('[data-row-status-text]');
        const retry = row.querySelector('[data-row-retry]');
        if (!status || !text || !retry) return;
        status.className = `app-status app-status--${tone} app-access-row-status`;
        text.textContent = message;
        status.hidden = false;
        retry.hidden = !canRetry;
        retry.disabled = saving || !loaded;
    }

    function clearRowStatus(row) {
        const status = row.querySelector('[data-row-status]');
        const text = row.querySelector('[data-row-status-text]');
        const retry = row.querySelector('[data-row-retry]');
        if (status) status.hidden = true;
        if (text) text.textContent = '';
        if (retry) {
            retry.hidden = true;
            retry.disabled = true;
        }
    }

    function refreshRow(row) {
        const state = states.get(row);
        const dirty = isDirty(row);
        selectsFor(row).forEach(select => {
            select.classList.toggle('app-access-select--changed', select.value !== state.original.get(select.name));
        });

        if (!dirty) state.error = null;
        if (state.error) {
            setRowStatus(row, 'error', `Error al guardar: ${state.error}`, true);
        } else if (dirty) {
            setRowStatus(row, 'warn', 'Modificado');
        } else if (state.saved) {
            setRowStatus(row, 'ok', 'Guardado');
        } else {
            clearRowStatus(row);
        }
    }

    function changedRows() {
        return rows.filter(isDirty);
    }

    function updateControls() {
        const count = changedRows().length;
        changeCount.textContent = count === 1 ? '1 usuario con cambios' : `${count} usuarios con cambios`;
        saveButton.textContent = `Guardar cambios (${count})`;
        saveButton.disabled = !loaded || saving || count === 0;
        discardButton.disabled = !loaded || saving || count === 0;
        rows.forEach(row => {
            selectsFor(row).forEach(select => { select.disabled = !loaded || saving; });
            const retry = row.querySelector('[data-row-retry]');
            if (retry && !retry.hidden) retry.disabled = !loaded || saving;
        });
    }

    function refreshAllRows() {
        rows.forEach(refreshRow);
        updateControls();
    }

    function showSummary(message, tone = 'neutral') {
        summary.className = `app-access-summary app-access-summary--${tone}`;
        summary.textContent = message;
        summary.hidden = false;
    }

    function clearSummary() {
        summary.textContent = '';
        summary.hidden = true;
    }

    function currentPermissions(row) {
        const permissions = {};
        selectsFor(row).forEach(select => { permissions[select.name] = select.value; });
        return permissions;
    }

    async function putRow(row) {
        const state = states.get(row);
        setRowStatus(row, 'neutral', 'Guardando…');
        try {
            const response = await fetch(`/api/admin/accesos/${row.dataset.userId}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({ permissions: currentPermissions(row) })
            });
            let result = null;
            try { result = await response.json(); } catch (error) { result = null; }
            if (!response.ok || !result || result.success !== true) {
                const message = result?.error || `HTTP ${response.status}`;
                throw new Error(message);
            }
            state.original = new Map(selectsFor(row).map(select => [select.name, select.value]));
            state.saved = true;
            state.error = null;
            refreshRow(row);
            return true;
        } catch (error) {
            const message = String(error?.message || 'Error de conexión').slice(0, 180);
            state.error = message;
            refreshRow(row);
            return false;
        }
    }

    function setLoadError(error) {
        loadStatus.classList.remove('app-status--neutral');
        loadStatus.classList.add('app-status--error');
        loadStatus.setAttribute('role', 'alert');
        loadStatusText.textContent = `No se pudieron cargar los permisos. ${String(error?.message || 'Error de conexión')}`;
    }

    async function loadPermissions() {
        try {
            const response = await fetch('/api/admin/accesos', { headers: { Accept: 'application/json' } });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();
            if (!Array.isArray(data)) throw new Error('La respuesta no contiene una lista de usuarios.');

            const byId = new Map(data.map(user => [String(user.id), user]));
            const loadedRows = rows.map(row => {
                const user = byId.get(row.dataset.userId);
                if (!user || !user.permissions || typeof user.permissions !== 'object') {
                    throw new Error('La respuesta no incluye los permisos de todos los usuarios visibles.');
                }
                const permissions = new Map();
                for (const select of selectsFor(row)) {
                    const level = user.permissions[select.name];
                    const allowed = Array.from(select.options).some(option => option.value === level);
                    if (!allowed) throw new Error(`Nivel de acceso inválido para ${select.name}.`);
                    permissions.set(select.name, level);
                }
                return { row, permissions };
            });

            loadedRows.forEach(({ row, permissions }) => {
                const state = states.get(row);
                permissions.forEach((level, module) => {
                    const select = selectsFor(row).find(item => item.name === module);
                    select.value = level;
                });
                state.original = permissions;
            });
            loaded = true;
            loadStatus.hidden = true;
            refreshAllRows();
        } catch (error) {
            setLoadError(error);
            updateControls();
        }
    }

    async function saveRows(targetRows) {
        if (!loaded || saving || !targetRows.length) return;
        saving = true;
        clearSummary();
        updateControls();
        let updated = 0;
        for (const row of targetRows) {
            if (await putRow(row)) updated += 1;
        }
        saving = false;
        refreshAllRows();
        const failed = targetRows.length - updated;
        const detail = failed ? ` ${failed} con error; podés reintentar desde su fila.` : '';
        showSummary(`${updated} de ${targetRows.length} usuarios actualizados.${detail}`, failed ? 'error' : 'ok');
    }

    rows.forEach(row => {
        selectsFor(row).forEach(select => {
            select.addEventListener('change', () => {
                const state = states.get(row);
                state.error = null;
                clearSummary();
                refreshRow(row);
                updateControls();
            });
        });
        row.querySelector('[data-row-retry]')?.addEventListener('click', () => {
            if (!saving && isDirty(row)) saveRows([row]);
        });
    });

    saveButton.addEventListener('click', () => saveRows(changedRows()));
    discardButton.addEventListener('click', () => {
        if (!loaded || saving) return;
        rows.forEach(row => {
            const state = states.get(row);
            selectsFor(row).forEach(select => { select.value = state.original.get(select.name); });
            state.error = null;
            refreshRow(row);
        });
        clearSummary();
        updateControls();
    });

    window.addEventListener('beforeunload', event => {
        if (!loaded || !changedRows().length) return;
        event.preventDefault();
        event.returnValue = '';
    });

    updateControls();
    loadPermissions();
})();
