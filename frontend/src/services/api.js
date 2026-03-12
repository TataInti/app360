// frontend/src/services/api.js
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5001/api';

const ACCESS_TOKEN_KEY = 'app360_access_token';

class ApiService {
  getAccessToken() {
    try {
      return localStorage.getItem(ACCESS_TOKEN_KEY);
    } catch {
      return null;
    }
  }

  setAccessToken(token) {
    try {
      if (!token) localStorage.removeItem(ACCESS_TOKEN_KEY);
      else localStorage.setItem(ACCESS_TOKEN_KEY, token);
    } catch {
      // no-op
    }
  }

  async request(endpoint, options = {}) {
    const url = `${API_BASE_URL}${endpoint}`;
    const token = this.getAccessToken();
    const config = {
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...options.headers,
      },
      credentials: 'include',
      ...options,
    };

    try {
      const response = await fetch(url, config);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const contentType = response.headers.get('content-type') || '';
      if (!contentType.includes('application/json')) {
        throw new Error(`Expected JSON response, got: ${contentType || 'unknown'}`);
      }
      return await response.json();
    } catch (error) {
      console.error('API request failed:', error);
      throw error;
    }
  }

  // Auth endpoints (JWT)
  async login(credentials) {
    const data = await this.request('/login', {
      method: 'POST',
      body: JSON.stringify(credentials),
    });
    if (data?.access_token) this.setAccessToken(data.access_token);
    return data;
  }

  async logout() {
    this.setAccessToken(null);
    return { success: true };
  }

  async getCurrentUser() {
    return this.request('/me');
  }

  // Dashboard endpoints
  async getDashboard() {
    return this.request('/dashboard');
  }

  async getDashboardFinanciero(period = '30') {
    const p = encodeURIComponent(period);
    return this.request(`/dashboard-financiero?period=${p}`);
  }

  async getDashboardComercial() {
    return this.request('/dashboard-comercial');
  }

  async getDashboardComercialV2(period = '30') {
    const p = encodeURIComponent(period);
    return this.request(`/dashboard-comercial-v2?period=${p}`);
  }

  async getVentasPreDetalle(params = '') {
    return this.request(`/comercial/ventas-pre-detalle${params ? `?${params}` : ''}`);
  }

  async getPanelEjecutivo() {
    return this.request('/panel-ejecutivo');
  }

  async getPanelEjecutivoV2(period = 'ytd') {
    const p = encodeURIComponent(period);
    return this.request(`/panel-ejecutivo-v2?period=${p}`);
  }

  // Inteligencia / BI endpoints
  async getInteligenciaOverview(params = '') {
    return this.request(`/bi/overview${params ? `?${params}` : ''}`);
  }

  async getInteligenciaRentabilidad(params = '') {
    return this.request(`/bi/rentabilidad${params ? `?${params}` : ''}`);
  }

  async getInteligenciaEficiencia(params = '') {
    return this.request(`/bi/eficiencia${params ? `?${params}` : ''}`);
  }

  async getInteligenciaLiquidez(params = '') {
    return this.request(`/bi/liquidez${params ? `?${params}` : ''}`);
  }

  async getInteligenciaProyecciones(params = '') {
    return this.request(`/bi/proyecciones${params ? `?${params}` : ''}`);
  }

  // Products endpoints
  async getProducts() {
    return this.request('/products');
  }

  async createProduct(product) {
    return this.request('/products', {
      method: 'POST',
      body: JSON.stringify(product),
    });
  }

  async updateProduct(id, product) {
    return this.request(`/products/${id}`, {
      method: 'PUT',
      body: JSON.stringify(product),
    });
  }

  async deleteProduct(id) {
    return this.request(`/products/${id}`, {
      method: 'DELETE',
    });
  }

  // Locations endpoints
  async getLocations() {
    return this.request('/locations');
  }

  async createLocation(location) {
    return this.request('/locations', {
      method: 'POST',
      body: JSON.stringify(location),
    });
  }

  async updateLocation(id, location) {
    return this.request(`/locations/${id}`, {
      method: 'PUT',
      body: JSON.stringify(location),
    });
  }

  async deleteLocation(id) {
    return this.request(`/locations/${id}`, {
      method: 'DELETE',
    });
  }

  // Leads endpoints
  async getLeads() {
    return this.request('/leads');
  }

  async createLead(lead) {
    return this.request('/leads', {
      method: 'POST',
      body: JSON.stringify(lead),
    });
  }

  async updateLead(id, lead) {
    return this.request(`/leads/${id}`, {
      method: 'PUT',
      body: JSON.stringify(lead),
    });
  }

  async deleteLead(id) {
    return this.request(`/leads/${id}`, {
      method: 'DELETE',
    });
  }

  // Stock endpoints
  async getStock() {
    return this.request('/stock');
  }

  async createStock(stock) {
    return this.request('/stock', {
      method: 'POST',
      body: JSON.stringify(stock),
    });
  }

  async updateStock(id, stock) {
    return this.request(`/stock/${id}`, {
      method: 'PUT',
      body: JSON.stringify(stock),
    });
  }

  async deleteStock(id) {
    return this.request(`/stock/${id}`, {
      method: 'DELETE',
    });
  }

  // Compras/Purchases endpoints
  async getPurchases() {
    return this.request('/compras');
  }

  async getComprasOverview(period = '30') {
    const p = encodeURIComponent(period);
    return this.request(`/compras/overview?period=${p}`);
  }

  async createPurchase(purchase) {
    return this.request('/compras', {
      method: 'POST',
      body: JSON.stringify(purchase),
    });
  }

  async updatePurchase(id, purchase) {
    return this.request(`/compras/${id}`, {
      method: 'PUT',
      body: JSON.stringify(purchase),
    });
  }

  async deletePurchase(id) {
    return this.request(`/compras/${id}`, {
      method: 'DELETE',
    });
  }

  // RRHH/Employees endpoints
  async getEmployees() {
    return this.request('/rrhh/empleados');
  }

  async createEmployee(employee) {
    return this.request('/rrhh/empleados', {
      method: 'POST',
      body: JSON.stringify(employee),
    });
  }

  async updateEmployee(id, employee) {
    return this.request(`/rrhh/empleados/${id}`, {
      method: 'PUT',
      body: JSON.stringify(employee),
    });
  }

  async deleteEmployee(id) {
    return this.request(`/rrhh/empleados/${id}`, {
      method: 'DELETE',
    });
  }

  // RRHH additional endpoints
  async getRrhhDotacion() {
    return this.request('/rrhh/dotacion');
  }

  async getRrhhAsistencia() {
    return this.request('/rrhh/asistencia');
  }

  async getRrhhAusentismo() {
    return this.request('/rrhh/ausentismo');
  }

  async getRrhhClima() {
    return this.request('/rrhh/clima');
  }

  async getRrhhObjetivos() {
    return this.request('/rrhh/objetivos');
  }
}

export default new ApiService();