function jsonResponse(route, payload, status = 200) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(payload),
  });
}

function emptyExcel(route, filename) {
  return route.fulfill({
    status: 200,
    headers: {
      "content-type":
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "content-disposition": `attachment; filename="${filename}"`,
    },
    body: Buffer.from("PK\x03\x04", "binary"),
  });
}

async function mockAdminApi(page) {
  const state = {
    tenants: [
      { id: "tenant-1", slug: "botilleria", name: "Botilleria Centro", status: "active" },
      { id: "tenant-2", slug: "bodega-norte", name: "Bodega Norte", status: "inactive" },
    ],
    agentConfig: {
      "tenant-1": {
        model: "openrouter/nvidia/nemotron-3-super-120b-a12b:free",
        instruction: "Asiste con ventas y soporte.",
        has_api_key: true,
      },
      "tenant-2": {
        model: "groq/llama3-8b-8192",
        instruction: "Asiste con soporte liviano.",
        has_api_key: false,
      },
    },
    settings: {
      maintenance_mode: false,
      default_model: "openrouter/nvidia/nemotron-3-super-120b-a12b:free",
    },
  };

  await page.route("http://localhost:8001/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();

    if (path === "/admin/tenants" && method === "GET") {
      return jsonResponse(route, state.tenants);
    }

    if (path === "/admin/tenants" && method === "POST") {
      const data = JSON.parse(request.postData() || "{}");
      const tenant = {
        id: `tenant-${state.tenants.length + 1}`,
        slug: data.slug,
        name: data.name,
        status: "active",
      };
      state.tenants.push(tenant);
      state.agentConfig[tenant.id] = {
        model: data.model,
        instruction: data.instruction,
        has_api_key: Boolean(data.api_key),
      };
      return jsonResponse(route, tenant, 201);
    }

    const agentMatch = path.match(/^\/admin\/tenants\/([^/]+)\/agent$/);
    if (agentMatch && method === "GET") {
      return jsonResponse(route, state.agentConfig[agentMatch[1]] || {});
    }
    if (agentMatch && method === "PUT") {
      const tenantId = agentMatch[1];
      const data = JSON.parse(request.postData() || "{}");
      state.agentConfig[tenantId] = {
        model: data.model,
        instruction: data.instruction,
        has_api_key: Boolean(data.api_key) || state.agentConfig[tenantId]?.has_api_key || false,
      };
      return jsonResponse(route, { status: "ok" });
    }

    const statusMatch = path.match(/^\/admin\/tenants\/([^/]+)\/status$/);
    if (statusMatch && method === "PATCH") {
      const tenant = state.tenants.find((item) => item.id === statusMatch[1]);
      if (tenant) {
        tenant.status = url.searchParams.get("status") || tenant.status;
      }
      return jsonResponse(route, { status: "ok" });
    }

    const deleteMatch = path.match(/^\/admin\/tenants\/([^/]+)$/);
    if (deleteMatch && method === "DELETE") {
      state.tenants = state.tenants.filter((item) => item.id !== deleteMatch[1]);
      return jsonResponse(route, { status: "deleted" });
    }

    if (path === "/admin/settings" && method === "GET") {
      return jsonResponse(route, state.settings);
    }

    const settingsMatch = path.match(/^\/admin\/settings\/(.+)$/);
    if (settingsMatch && method === "PUT") {
      const key = decodeURIComponent(settingsMatch[1]);
      const data = JSON.parse(request.postData() || "{}");
      state.settings[key] = data.value;
      return jsonResponse(route, {
        key,
        value: state.settings[key],
        description: data.description || key,
      });
    }

    return jsonResponse(route, { error: `Unhandled admin mock for ${method} ${path}` }, 500);
  });

  return state;
}

async function mockTenantApi(page) {
  const state = {
    profile: {
      name: "Botilleria Centro",
      email: "contacto@centro.cl",
      phone: "+56911111111",
      address: "Providencia 1234",
      city: "Santiago",
      website: "https://centro.cl",
      logo_url: "",
      business_hours: {
        Lunes: { open: "10:00", close: "22:00" },
        Martes: { open: "10:00", close: "22:00" },
        Miércoles: { open: "10:00", close: "22:00" },
        Jueves: { open: "10:00", close: "22:00" },
        Viernes: { open: "10:00", close: "22:00" },
        Sábado: { open: "10:00", close: "20:00" },
        Domingo: { closed: true, open: null, close: null },
      },
      human_agent_available: true,
      status: "active",
    },
    counts: { users: 42, conversations: 128 },
    products: [
      {
        id: "prod-1",
        name: "Alto del Carmen 35°",
        category: "Piscos",
        format: "750ml",
        price: 6500,
        stock: 12,
        is_available: true,
        description: "Pisco",
        unit_of_measure: "un",
      },
    ],
    kbEntries: [
      {
        id: "kb-1",
        category: "Horarios",
        title: "Horario de atención",
        content: "Atendemos de lunes a sábado.",
        is_active: true,
      },
    ],
    categories: [
      { name: "General", slug: "general", is_system: true },
      { name: "Piscos", slug: "piscos", is_system: false },
    ],
    channels: [{ platform: "telegram", channel_identifier: "@botilleria_centro_bot" }],
  };

  const handleTenantRoute = async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();

    if (path === "/tenants/me/users/count" && method === "GET") {
      return jsonResponse(route, { count: state.counts.users });
    }
    if (path === "/tenants/me/conversations/count" && method === "GET") {
      return jsonResponse(route, { count: state.counts.conversations });
    }
    if (path === "/tenants/me/profile" && method === "GET") {
      return jsonResponse(route, state.profile);
    }
    if (path === "/tenants/me/profile" && method === "PUT") {
      const data = JSON.parse(request.postData() || "{}");
      state.profile = { ...state.profile, ...data };
      return jsonResponse(route, state.profile);
    }
    if (path === "/tenants/me/products" && method === "GET") {
      return jsonResponse(route, state.products);
    }
    if (path === "/tenants/me/products" && method === "POST") {
      const data = JSON.parse(request.postData() || "{}");
      const product = {
        id: `prod-${state.products.length + 1}`,
        is_available: true,
        unit_of_measure: "un",
        ...data,
      };
      state.products.push(product);
      return jsonResponse(route, product, 201);
    }
    const productMatch = path.match(/^\/tenants\/me\/products\/([^/]+)$/);
    if (productMatch && method === "PUT") {
      const data = JSON.parse(request.postData() || "{}");
      state.products = state.products.map((item) =>
        item.id === productMatch[1] ? { ...item, ...data } : item
      );
      return jsonResponse(route, { status: "ok" });
    }
    if (productMatch && method === "DELETE") {
      state.products = state.products.filter((item) => item.id !== productMatch[1]);
      return jsonResponse(route, { status: "deleted" });
    }
    if (path === "/tenants/me/products/export" && method === "GET") {
      return emptyExcel(route, "productos.xlsx");
    }
    if (path === "/tenants/me/products/export/template" && method === "GET") {
      return emptyExcel(route, "plantilla_productos.xlsx");
    }
    if (path === "/tenants/me/products/import" && method === "POST") {
      return jsonResponse(route, {
        status: "ok",
        rows_processed: 1,
        created: 1,
        updated: 0,
        errors: 0,
      });
    }

    if (path === "/tenants/me/kb" && method === "GET") {
      return jsonResponse(route, state.kbEntries);
    }
    if (path === "/tenants/me/kb" && method === "POST") {
      const data = JSON.parse(request.postData() || "{}");
      const entry = { id: `kb-${state.kbEntries.length + 1}`, is_active: true, ...data };
      state.kbEntries.push(entry);
      return jsonResponse(route, entry, 201);
    }
    const kbMatch = path.match(/^\/tenants\/me\/kb\/([^/]+)$/);
    if (kbMatch && method === "PUT") {
      const data = JSON.parse(request.postData() || "{}");
      state.kbEntries = state.kbEntries.map((item) =>
        item.id === kbMatch[1] ? { ...item, ...data } : item
      );
      return jsonResponse(route, { status: "ok" });
    }
    if (kbMatch && method === "DELETE") {
      state.kbEntries = state.kbEntries.filter((item) => item.id !== kbMatch[1]);
      return jsonResponse(route, { status: "deleted" });
    }
    if (path === "/tenants/me/kb/search" && method === "POST") {
      return jsonResponse(route, { query: "horario", results: state.kbEntries, count: state.kbEntries.length });
    }

    if (path === "/categories" && method === "GET") {
      return jsonResponse(route, state.categories);
    }
    if (path === "/categories" && method === "POST") {
      const data = JSON.parse(request.postData() || "{}");
      const category = {
        name: data.name,
        slug: data.name.toLowerCase().replace(/\s+/g, "-"),
        is_system: false,
      };
      state.categories.push(category);
      return jsonResponse(route, { status: "success", category }, 201);
    }
    const categoryMatch = path.match(/^\/categories\/(.+)$/);
    if (categoryMatch && method === "PUT") {
      const currentName = decodeURIComponent(categoryMatch[1]);
      const data = JSON.parse(request.postData() || "{}");
      state.categories = state.categories.map((item) =>
        item.name === currentName
          ? { ...item, name: data.new_name, slug: data.new_name.toLowerCase().replace(/\s+/g, "-") }
          : item
      );
      return jsonResponse(route, { status: "success" });
    }
    if (categoryMatch && method === "DELETE") {
      const currentName = decodeURIComponent(categoryMatch[1]);
      state.categories = state.categories.filter((item) => item.name !== currentName);
      return jsonResponse(route, { status: "success" });
    }

    if (path === "/tenants/me/channels" && method === "GET") {
      return jsonResponse(route, state.channels);
    }

    return jsonResponse(route, { error: `Unhandled tenant mock for ${method} ${path}` }, 500);
  };

  await page.route("http://localhost:8001/**", handleTenantRoute);
  await page.route("http://127.0.0.1:4173/tenants/**", handleTenantRoute);
  await page.route("http://127.0.0.1:4173/categories/**", handleTenantRoute);

  return state;
}

module.exports = {
  mockAdminApi,
  mockTenantApi,
};
