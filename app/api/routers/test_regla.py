from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
import httpx
import time
from datetime import datetime
from typing import List

from app.db.database import get_db
from app.core.security import get_current_user
from app.schemas.test_regla import TestResultItem, TestSummary

router = APIRouter(prefix="/test-regla-articulo", tags=["Testing - Regla Artículo"])


class ReglaArticuloAPITester:
    def __init__(self, base_url: str = "http://localhost:8000", token: str = None):
        self.base_url = base_url
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}" if token else "",
            "Content-Type": "application/json"
        }
        self.results = []
        
    def log_result(self, test_name: str, passed: bool, duration_ms: float, details: str = ""):
        """Registra resultado de una prueba"""
        result = {
            "test": test_name,
            "passed": passed,
            "duration_ms": round(duration_ms, 2),
            "details": details,
            "timestamp": datetime.now().isoformat()
        }
        self.results.append(result)
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} | {test_name} | {duration_ms:.2f}ms | {details}")
        
    def measure_request(self, method: str, endpoint: str, **kwargs):
        """Mide tiempo de respuesta de una petición"""
        url = f"{self.base_url}{endpoint}"
        start = time.time()
        try:
            response = requests.request(method, url, headers=self.headers, **kwargs)
            duration_ms = (time.time() - start) * 1000
            return response, duration_ms
        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            return None, duration_ms

    # ============================================================
    # PRUEBAS DE LISTADO (GET /reglas/articulos)
    # ============================================================
    def test_listar_reglas(self):
        """Prueba GET /reglas/articulos"""
        response, duration = self.measure_request("GET", "/reglas/articulos")
        
        if response and response.status_code == 200:
            data = response.json()
            self.log_result(
                "Listar reglas",
                True,
                duration,
                f"Retornó {len(data)} reglas"
            )
            return data
        else:
            self.log_result(
                "Listar reglas",
                False,
                duration,
                f"Status: {response.status_code if response else 'Error'}"
            )
            return []

    def test_listar_con_inactivas(self):
        """Prueba GET /reglas/articulos?incluir_inactivas=true"""
        response, duration = self.measure_request(
            "GET", 
            "/reglas/articulos?incluir_inactivas=true"
        )
        
        if response and response.status_code == 200:
            data = response.json()
            self.log_result(
                "Listar con inactivas",
                True,
                duration,
                f"Retornó {len(data)} reglas (incluye inactivas)"
            )
        else:
            self.log_result(
                "Listar con inactivas",
                False,
                duration,
                f"Status: {response.status_code if response else 'Error'}"
            )

    # ============================================================
    # PRUEBAS DE OBTENER (GET /reglas/articulos/{id})
    # ============================================================
    def test_obtener_regla_existente(self, id_tipo: int = 1):
        """Prueba GET /reglas/articulos/{id} con ID existente"""
        response, duration = self.measure_request(
            "GET",
            f"/reglas/articulos/{id_tipo}"
        )
        
        if response and response.status_code == 200:
            data = response.json()
            self.log_result(
                f"Obtener regla {id_tipo}",
                True,
                duration,
                f"Tipo: {data.get('tipo_nombre', 'N/A')}"
            )
            return data
        else:
            self.log_result(
                f"Obtener regla {id_tipo}",
                False,
                duration,
                f"Status: {response.status_code if response else 'Error'}"
            )
            return None

    def test_obtener_regla_inexistente(self):
        """Prueba GET /reglas/articulos/99999 (no existe)"""
        response, duration = self.measure_request(
            "GET",
            "/reglas/articulos/99999"
        )
        
        passed = response and response.status_code == 404
        self.log_result(
            "Obtener regla inexistente",
            passed,
            duration,
            f"Status: {response.status_code if response else 'Error'} (esperado 404)"
        )

    # ============================================================
    # PRUEBAS DE CREACIÓN (POST /reglas/articulos)
    # ============================================================
    def test_crear_regla_valida(self, id_tipo: int = 100):
        """Prueba POST /reglas/articulos con datos válidos"""
        payload = {
            "id_tipo": id_tipo,
            "admite_comprar": True,
            "admite_recoleccion": True,
            "valor_max_domicilio": 5000.00,
            "requiere_dos_personas": False,
            "requiere_serie": True,
            "requiere_prueba": True,
            "activo": True
        }
        
        response, duration = self.measure_request(
            "POST",
            "/reglas/articulos",
            json=payload
        )
        
        if response and response.status_code == 201:
            data = response.json()
            self.log_result(
                "Crear regla válida",
                True,
                duration,
                f"ID: {data.get('id_tipo')}"
            )
            return data
        else:
            self.log_result(
                "Crear regla válida",
                False,
                duration,
                f"Status: {response.status_code if response else 'Error'}"
            )
            return None

    def test_crear_regla_sin_id_tipo(self):
        """Prueba POST sin id_tipo (debe fallar)"""
        payload = {
            "admite_comprar": True,
            "admite_recoleccion": False
        }
        
        response, duration = self.measure_request(
            "POST",
            "/reglas/articulos",
            json=payload
        )
        
        passed = response and response.status_code == 400
        self.log_result(
            "Crear sin id_tipo",
            passed,
            duration,
            f"Status: {response.status_code if response else 'Error'} (esperado 400)"
        )

    def test_crear_regla_valor_negativo(self):
        """Prueba POST con valor_max_domicilio negativo (debe fallar)"""
        payload = {
            "id_tipo": 101,
            "admite_comprar": True,
            "admite_recoleccion": True,
            "valor_max_domicilio": -100.00,
            "requiere_dos_personas": False,
            "requiere_serie": False,
            "requiere_prueba": False,
            "activo": True
        }
        
        response, duration = self.measure_request(
            "POST",
            "/reglas/articulos",
            json=payload
        )
        
        passed = response and response.status_code == 400
        self.log_result(
            "Crear con valor negativo",
            passed,
            duration,
            f"Status: {response.status_code if response else 'Error'} (esperado 400)"
        )

    def test_crear_regla_duplicada(self, id_tipo: int = 1):
        """Prueba POST con id_tipo ya existente (debe fallar 409)"""
        payload = {
            "id_tipo": id_tipo,
            "admite_comprar": True,
            "admite_recoleccion": False,
            "requiere_dos_personas": False,
            "requiere_serie": False,
            "requiere_prueba": False,
            "activo": True
        }
        
        response, duration = self.measure_request(
            "POST",
            "/reglas/articulos",
            json=payload
        )
        
        passed = response and response.status_code == 409
        self.log_result(
            "Crear regla duplicada",
            passed,
            duration,
            f"Status: {response.status_code if response else 'Error'} (esperado 409)"
        )

    # ============================================================
    # PRUEBAS DE ACTUALIZACIÓN (PUT /reglas/articulos/{id})
    # ============================================================
    def test_actualizar_regla(self, id_tipo: int = 1):
        """Prueba PUT /reglas/articulos/{id}"""
        payload = {
            "admite_comprar": False,
            "admite_recoleccion": True,
            "valor_max_domicilio": 3000.00,
            "requiere_dos_personas": True,
            "requiere_serie": False,
            "requiere_prueba": True,
            "activo": True
        }
        
        response, duration = self.measure_request(
            "PUT",
            f"/reglas/articulos/{id_tipo}",
            json=payload
        )
        
        if response and response.status_code == 200:
            data = response.json()
            self.log_result(
                f"Actualizar regla {id_tipo}",
                True,
                duration,
                f"Valor max: {data.get('valor_max_domicilio')}"
            )
            return data
        else:
            self.log_result(
                f"Actualizar regla {id_tipo}",
                False,
                duration,
                f"Status: {response.status_code if response else 'Error'}"
            )
            return None

    def test_actualizar_regla_inexistente(self):
        """Prueba PUT con ID inexistente"""
        payload = {
            "admite_comprar": True,
            "admite_recoleccion": False,
            "requiere_dos_personas": False,
            "requiere_serie": False,
            "requiere_prueba": False,
            "activo": True
        }
        
        response, duration = self.measure_request(
            "PUT",
            "/reglas/articulos/99999",
            json=payload
        )
        
        passed = response and response.status_code == 404
        self.log_result(
            "Actualizar regla inexistente",
            passed,
            duration,
            f"Status: {response.status_code if response else 'Error'} (esperado 404)"
        )

    # ============================================================
    # PRUEBAS DE ELIMINACIÓN (DELETE /reglas/articulos/{id})
    # ============================================================
    def test_eliminar_regla(self, id_tipo: int = 100):
        """Prueba DELETE /reglas/articulos/{id} (soft delete)"""
        response, duration = self.measure_request(
            "DELETE",
            f"/reglas/articulos/{id_tipo}"
        )
        
        if response and response.status_code == 200:
            data = response.json()
            passed = data.get("activo") == False
            self.log_result(
                f"Eliminar regla {id_tipo}",
                passed,
                duration,
                "Soft delete exitoso" if passed else "Error: activo no cambió"
            )
        else:
            self.log_result(
                f"Eliminar regla {id_tipo}",
                False,
                duration,
                f"Status: {response.status_code if response else 'Error'}"
            )

    def test_eliminar_regla_inexistente(self):
        """Prueba DELETE con ID inexistente"""
        response, duration = self.measure_request(
            "DELETE",
            "/reglas/articulos/99999"
        )
        
        passed = response and response.status_code == 404
        self.log_result(
            "Eliminar regla inexistente",
            passed,
            duration,
            f"Status: {response.status_code if response else 'Error'} (esperado 404)"
        )

    # ============================================================
    # PRUEBAS DE RENDIMIENTO
    # ============================================================
    def test_rendimiento_listado(self, iterations: int = 10):
        """Mide rendimiento promedio del listado"""
        durations = []
        
        for i in range(iterations):
            response, duration = self.measure_request("GET", "/reglas/articulos")
            if response and response.status_code == 200:
                durations.append(duration)
        
        if durations:
            avg_duration = sum(durations) / len(durations)
            min_duration = min(durations)
            max_duration = max(durations)
            
            passed = avg_duration < 200  # Menos de 200ms promedio
            self.log_result(
                "Rendimiento listado",
                passed,
                avg_duration,
                f"Min: {min_duration:.2f}ms, Max: {max_duration:.2f}ms"
            )

    def test_rendimiento_obtencion(self, id_tipo: int = 1, iterations: int = 10):
        """Mide rendimiento promedio de obtención"""
        durations = []
        
        for i in range(iterations):
            response, duration = self.measure_request(
                "GET",
                f"/reglas/articulos/{id_tipo}"
            )
            if response and response.status_code == 200:
                durations.append(duration)
        
        if durations:
            avg_duration = sum(durations) / len(durations)
            min_duration = min(durations)
            max_duration = max(durations)
            
            passed = avg_duration < 100  # Menos de 100ms promedio
            self.log_result(
                "Rendimiento obtención",
                passed,
                avg_duration,
                f"Min: {min_duration:.2f}ms, Max: {max_duration:.2f}ms"
            )

    # ============================================================
    # EJECUCIÓN DE SUITE COMPLETA
    # ============================================================
    def run_all_tests(self):
        """Ejecuta todas las pruebas"""
        print("\n" + "="*80)
        print("INICIANDO SUITE DE PRUEBAS - REGLA TIPO ARTÍCULO API")
        print("="*80 + "\n")
        
        # 1. Pruebas de listado
        print("\n--- PRUEBAS DE LISTADO ---")
        self.test_listar_reglas()
        self.test_listar_con_inactivas()
        
        # 2. Pruebas de obtención
        print("\n--- PRUEBAS DE OBTENCIÓN ---")
        self.test_obtener_regla_existente(1)
        self.test_obtener_regla_inexistente()
        
        # 3. Pruebas de creación
        print("\n--- PRUEBAS DE CREACIÓN ---")
        self.test_crear_regla_valida(100)
        self.test_crear_regla_sin_id_tipo()
        self.test_crear_regla_valor_negativo()
        self.test_crear_regla_duplicada(1)
        
        # 4. Pruebas de actualización
        print("\n--- PRUEBAS DE ACTUALIZACIÓN ---")
        self.test_actualizar_regla(1)
        self.test_actualizar_regla_inexistente()
        
        # 5. Pruebas de eliminación
        print("\n--- PRUEBAS DE ELIMINACIÓN ---")
        self.test_eliminar_regla(100)
        self.test_eliminar_regla_inexistente()
        
        # 6. Pruebas de rendimiento
        print("\n--- PRUEBAS DE RENDIMIENTO ---")
        self.test_rendimiento_listado(10)
        self.test_rendimiento_obtencion(1, 10)
        
        # Resumen
        self.print_summary()
    
    def print_summary(self):
        """Imprime resumen de resultados"""
        print("\n" + "="*80)
        print("RESUMEN DE PRUEBAS")
        print("="*80)
        
        total = len(self.results)
        passed = sum(1 for r in self.results if r["passed"])
        failed = total - passed
        
        print(f"\nTotal de pruebas: {total}")
        print(f"✅ Exitosas: {passed}")
        print(f"❌ Fallidas: {failed}")
        print(f"Tasa de éxito: {(passed/total*100):.1f}%")
        
        # Tiempos
        avg_duration = sum(r["duration_ms"] for r in self.results) / total
        print(f"\nTiempo promedio: {avg_duration:.2f}ms")
        
        # Pruebas fallidas
        if failed > 0:
            print("\n--- PRUEBAS FALLIDAS ---")
            for r in self.results:
                if not r["passed"]:
                    print(f"❌ {r['test']}: {r['details']}")
        
        print("\n" + "="*80 + "\n")

