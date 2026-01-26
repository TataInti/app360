#!/usr/bin/env python
"""Script de pruebas exhaustivas de todos los módulos"""
import requests
import re
import json
from datetime import date

BASE_URL = "http://127.0.0.1:5001"

class TestRunner:
    def __init__(self):
        self.session = requests.Session()
        self.results = []
        
    def log(self, test_name, success, detail=""):
        status = "✅ PASS" if success else "❌ FAIL"
        self.results.append((test_name, success, detail))
        print(f"{status}: {test_name}" + (f" - {detail}" if detail else ""))
    
    def get_csrf_token(self, url):
        """Obtener CSRF token de una página"""
        resp = self.session.get(url)
        match = re.search(r'name="csrf_token".*?value="([^"]+)"', resp.text)
        if match:
            return match.group(1)
        # También buscar en meta tag
        match = re.search(r'<meta name="csrf-token" content="([^"]+)"', resp.text)
        if match:
            return match.group(1)
        return None
    
    def login(self, username="admin", password="admin123"):
        """Login y obtener sesión"""
        # Obtener CSRF token
        resp = self.session.get(f"{BASE_URL}/")
        csrf = self.get_csrf_token(f"{BASE_URL}/")
        
        if not csrf:
            self.log("Login - Get CSRF", False, "No CSRF token found")
            return False
        
        # Hacer login
        data = {
            "username": username,
            "password": password,
            "csrf_token": csrf
        }
        resp = self.session.post(f"{BASE_URL}/", data=data, allow_redirects=False)
        
        if resp.status_code in [302, 303]:
            self.log("Login", True, f"Redirected to {resp.headers.get('Location')}")
            return True
        else:
            self.log("Login", False, f"Status: {resp.status_code}")
            return False
    
    # ===================== TESORERÍA =====================
    def test_tesoreria(self):
        print("\n=== MÓDULO TESORERÍA ===")
        
        # Panel
        resp = self.session.get(f"{BASE_URL}/tesoreria")
        self.log("Tesorería - Panel", resp.status_code == 200, f"Status: {resp.status_code}")
        
        # Arqueos page
        resp = self.session.get(f"{BASE_URL}/tesoreria/arqueos")
        self.log("Tesorería - Arqueos Page", resp.status_code == 200, f"Status: {resp.status_code}")
        
        # Movimientos page
        resp = self.session.get(f"{BASE_URL}/tesoreria/movimientos")
        self.log("Tesorería - Movimientos Page", resp.status_code == 200, f"Status: {resp.status_code}")
        
        # API - Listar instrumentos
        resp = self.session.get(f"{BASE_URL}/api/tesoreria/instrumentos")
        self.log("Tesorería API - Listar instrumentos", resp.status_code == 200, f"Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            self.log("  -> Instrumentos encontrados", len(data.get('instrumentos', [])) > 0, f"Count: {len(data.get('instrumentos', []))}")
        
        # API - Listar movimientos
        resp = self.session.get(f"{BASE_URL}/api/tesoreria/movimientos")
        self.log("Tesorería API - Listar movimientos", resp.status_code == 200, f"Status: {resp.status_code}")
        
        # API - Listar arqueos
        resp = self.session.get(f"{BASE_URL}/api/tesoreria/arqueos")
        self.log("Tesorería API - Listar arqueos", resp.status_code == 200, f"Status: {resp.status_code}")
        
        # API - Crear movimiento
        csrf = self.get_csrf_token(f"{BASE_URL}/tesoreria")
        data = {
            "tipo": "ingreso",
            "monto": 1000.50,
            "instrumento_id": 1,
            "descripcion": "Test movimiento"
        }
        headers = {"Content-Type": "application/json", "X-CSRFToken": csrf}
        resp = self.session.post(f"{BASE_URL}/api/tesoreria/movimientos", json=data, headers=headers)
        self.log("Tesorería API - Crear movimiento", resp.status_code == 201, f"Status: {resp.status_code}, Response: {resp.text[:100]}")
        
        # API - Crear arqueo
        data = {
            "fecha": date.today().isoformat(),
            "turno": "mañana",
            "saldo_inicial": 5000,
            "saldo_final": 6000.50
        }
        resp = self.session.post(f"{BASE_URL}/api/tesoreria/arqueos", json=data, headers=headers)
        self.log("Tesorería API - Crear arqueo", resp.status_code in [201, 400], f"Status: {resp.status_code}, Response: {resp.text[:100]}")

    # ===================== GASTOS =====================
    def test_gastos(self):
        print("\n=== MÓDULO GASTOS ===")
        
        # Panel
        resp = self.session.get(f"{BASE_URL}/gastos")
        self.log("Gastos - Panel", resp.status_code == 200, f"Status: {resp.status_code}")
        
        # API - Listar categorías
        resp = self.session.get(f"{BASE_URL}/api/gastos/categorias")
        self.log("Gastos API - Listar categorías", resp.status_code == 200, f"Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            self.log("  -> Categorías encontradas", len(data.get('categorias', [])) > 0, f"Count: {len(data.get('categorias', []))}")
        
        # API - Listar proveedores
        resp = self.session.get(f"{BASE_URL}/api/gastos/proveedores")
        self.log("Gastos API - Listar proveedores", resp.status_code == 200, f"Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            self.log("  -> Proveedores encontrados", len(data.get('proveedores', [])) > 0, f"Count: {len(data.get('proveedores', []))}")
        
        # API - Listar gastos
        resp = self.session.get(f"{BASE_URL}/api/gastos/listar")
        self.log("Gastos API - Listar gastos", resp.status_code == 200, f"Status: {resp.status_code}")
        
        # API - Registrar gasto
        csrf = self.get_csrf_token(f"{BASE_URL}/gastos")
        data = {
            "descripcion": "Gasto de prueba",
            "monto": 500.00,
            "categoria_id": 1,
            "proveedor_id": 1,
            "fecha": date.today().isoformat()
        }
        headers = {"Content-Type": "application/json", "X-CSRFToken": csrf}
        resp = self.session.post(f"{BASE_URL}/api/gastos/registrar", json=data, headers=headers)
        self.log("Gastos API - Registrar gasto", resp.status_code == 201, f"Status: {resp.status_code}, Response: {resp.text[:100]}")

    # ===================== RRHH =====================
    def test_rrhh(self):
        print("\n=== MÓDULO RRHH ===")
        
        # Panel
        resp = self.session.get(f"{BASE_URL}/rrhh")
        self.log("RRHH - Panel", resp.status_code == 200, f"Status: {resp.status_code}")
        
        # Empleados
        resp = self.session.get(f"{BASE_URL}/rrhh/empleados")
        self.log("RRHH - Empleados Page", resp.status_code == 200, f"Status: {resp.status_code}")
        
        # Dotación
        resp = self.session.get(f"{BASE_URL}/rrhh/dotacion")
        self.log("RRHH - Dotación Page", resp.status_code == 200, f"Status: {resp.status_code}")
        
        # Ausentismo
        resp = self.session.get(f"{BASE_URL}/rrhh/ausentismo")
        self.log("RRHH - Ausentismo Page", resp.status_code == 200, f"Status: {resp.status_code}")
        
        # API - Turnos
        resp = self.session.get(f"{BASE_URL}/api/rrhh/turnos")
        self.log("RRHH API - Listar turnos", resp.status_code == 200, f"Status: {resp.status_code}")

    # ===================== COMPRAS =====================
    def test_compras(self):
        print("\n=== MÓDULO COMPRAS ===")
        
        # Panel
        resp = self.session.get(f"{BASE_URL}/compras")
        self.log("Compras - Panel", resp.status_code == 200, f"Status: {resp.status_code}")
        
        # Nueva orden
        resp = self.session.get(f"{BASE_URL}/compras/orden-nueva")
        self.log("Compras - Nueva Orden Page", resp.status_code == 200, f"Status: {resp.status_code}")

    # ===================== VENTAS =====================
    def test_ventas(self):
        print("\n=== MÓDULO VENTAS ===")
        
        # Lista
        resp = self.session.get(f"{BASE_URL}/ventas")
        self.log("Ventas - Lista", resp.status_code == 200, f"Status: {resp.status_code}")
        
        # Nueva venta
        resp = self.session.get(f"{BASE_URL}/ventas/nuevo")
        self.log("Ventas - Nueva Venta Page", resp.status_code == 200, f"Status: {resp.status_code}")

    # ===================== CRM/LEADS =====================
    def test_crm(self):
        print("\n=== MÓDULO CRM/LEADS ===")
        
        # Lista de leads
        resp = self.session.get(f"{BASE_URL}/leads")
        self.log("CRM - Lista Leads", resp.status_code == 200, f"Status: {resp.status_code}")
        
        # Nuevo lead
        resp = self.session.get(f"{BASE_URL}/leads/new")
        self.log("CRM - Nuevo Lead Page", resp.status_code == 200, f"Status: {resp.status_code}")
        
        # Campañas
        resp = self.session.get(f"{BASE_URL}/campaigns")
        self.log("CRM - Campañas", resp.status_code == 200, f"Status: {resp.status_code}")

    # ===================== PRODUCTS/STOCK =====================
    def test_products(self):
        print("\n=== MÓDULO PRODUCTS/STOCK ===")
        
        # Lista productos
        resp = self.session.get(f"{BASE_URL}/products")
        self.log("Products - Lista", resp.status_code == 200, f"Status: {resp.status_code}")
        
        # Nuevo producto
        resp = self.session.get(f"{BASE_URL}/products/new")
        self.log("Products - Nuevo Page", resp.status_code == 200, f"Status: {resp.status_code}")
        
        # Stock
        resp = self.session.get(f"{BASE_URL}/stock")
        self.log("Stock - Lista", resp.status_code == 200, f"Status: {resp.status_code}")

    # ===================== COMERCIAL =====================
    def test_comercial(self):
        print("\n=== MÓDULO COMERCIAL ===")
        
        # Página de objetivos
        resp = self.session.get(f"{BASE_URL}/comercial/objetivos")
        self.log("Comercial - Objetivos Page", resp.status_code == 200, f"Status: {resp.status_code}")
        
        # API - Listar vendedores
        resp = self.session.get(f"{BASE_URL}/api/comercial/vendedores")
        self.log("Comercial API - Vendedores", resp.status_code == 200, f"Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            vendedores = data.get('vendedores', [])
            mensaje = data.get('mensaje', '')
            if len(vendedores) > 0:
                self.log("  -> Vendedores encontrados", True, f"Count: {len(vendedores)}")
            else:
                self.log("  -> Sin vendedores (configurar en RRHH)", True, f"Mensaje: {mensaje[:50] if mensaje else 'N/A'}")
        
        # API - Listar objetivos
        resp = self.session.get(f"{BASE_URL}/api/comercial/objetivos")
        self.log("Comercial API - Objetivos", resp.status_code == 200, f"Status: {resp.status_code}")
        
        # API - Ranking
        resp = self.session.get(f"{BASE_URL}/api/comercial/ranking")
        self.log("Comercial API - Ranking", resp.status_code == 200, f"Status: {resp.status_code}")
        
        # Promociones
        resp = self.session.get(f"{BASE_URL}/api/comercial/promociones")
        self.log("Comercial API - Promociones", resp.status_code == 200, f"Status: {resp.status_code}")

    # ===================== DASHBOARD =====================
    def test_dashboard(self):
        print("\n=== MÓDULO DASHBOARD ===")
        
        resp = self.session.get(f"{BASE_URL}/dashboard")
        self.log("Dashboard - Principal", resp.status_code == 200, f"Status: {resp.status_code}")
        
        resp = self.session.get(f"{BASE_URL}/comercial/objetivos")
        self.log("Dashboard - Comercial Objetivos", resp.status_code == 200, f"Status: {resp.status_code}")

    # ===================== ADMIN =====================
    def test_admin(self):
        print("\n=== MÓDULO ADMIN ===")
        
        resp = self.session.get(f"{BASE_URL}/admin")
        self.log("Admin - Panel", resp.status_code == 200, f"Status: {resp.status_code}")

    def run_all(self):
        print("="*60)
        print("INICIO DE PRUEBAS EXHAUSTIVAS - APP360")
        print("="*60)
        
        # Login primero
        if not self.login():
            print("❌ No se pudo hacer login. Abortando pruebas.")
            return
        
        # Ejecutar todas las pruebas
        self.test_dashboard()
        self.test_tesoreria()
        self.test_gastos()
        self.test_rrhh()
        self.test_compras()
        self.test_ventas()
        self.test_crm()
        self.test_products()
        self.test_comercial()
        self.test_admin()
        
        # Resumen
        print("\n" + "="*60)
        print("RESUMEN DE PRUEBAS")
        print("="*60)
        passed = sum(1 for r in self.results if r[1])
        failed = sum(1 for r in self.results if not r[1])
        print(f"✅ Pasaron: {passed}")
        print(f"❌ Fallaron: {failed}")
        print(f"Total: {len(self.results)}")
        
        if failed > 0:
            print("\nPRUEBAS FALLIDAS:")
            for name, success, detail in self.results:
                if not success:
                    print(f"  - {name}: {detail}")

if __name__ == "__main__":
    runner = TestRunner()
    runner.run_all()
