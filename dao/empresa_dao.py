"""DAO del perfil de la empresa emisora (esquema monoempresa: se usa la primera fila de `empresa`)."""
from typing import Optional

from core.models import Empresa
from core.validators import (
    validar_cuenta_corriente, validar_entero_rango, validar_ruc, validar_telefono, validar_texto,
)
from dao.base_dao import BaseDAO

_SELECT = """
    SELECT e.ruc_empresa, e.razon_social_empresa, e.direccion_empresa, e.telefono_empresa,
           e.cuenta_corriente, e.id_distrito,
           di.nombre AS distrito, p.nombre AS provincia, dep.nombre AS departamento
    FROM empresa e
    JOIN distrito di      ON di.id_distrito = e.id_distrito
    JOIN provincia p      ON p.id_provincia = di.id_provincia
    JOIN departamento dep ON dep.id_departamento = p.id_departamento
"""


class EmpresaDAO(BaseDAO):

    def obtener(self) -> Optional[dict]:
        """Empresa emisora vigente (la primera registrada) o None si aún no se configuró."""
        return self._consultar_uno(
            _SELECT + " ORDER BY e.ruc_empresa LIMIT 1", contexto="No se pudo consultar la empresa emisora"
        )

    @staticmethod
    def _validar(e: Empresa) -> Empresa:
        return Empresa(
            ruc_empresa=validar_ruc(e.ruc_empresa, "RUC de la empresa"),
            razon_social_empresa=validar_texto(e.razon_social_empresa, "razón social", 50),
            direccion_empresa=validar_texto(e.direccion_empresa, "dirección", 50),
            telefono_empresa=validar_telefono(e.telefono_empresa),
            cuenta_corriente=validar_cuenta_corriente(e.cuenta_corriente),
            id_distrito=validar_entero_rango(e.id_distrito, "distrito", 1, 65535),
        )

    def guardar(self, empresa: Empresa, ruc_anterior: Optional[str] = None) -> None:
        """Inserta la empresa, o la actualiza si ya existe.

        Si el RUC cambió se actualiza la clave primaria: las facturas emitidas siguen enlazadas
        gracias a ON UPDATE CASCADE.
        """
        e = self._validar(empresa)
        if ruc_anterior:
            filas = self._ejecutar(
                "UPDATE empresa SET ruc_empresa=%s, razon_social_empresa=%s, direccion_empresa=%s, "
                "telefono_empresa=%s, cuenta_corriente=%s, id_distrito=%s WHERE ruc_empresa=%s",
                (e.ruc_empresa, e.razon_social_empresa, e.direccion_empresa, e.telefono_empresa,
                 e.cuenta_corriente, e.id_distrito, validar_ruc(ruc_anterior)),
                "No se pudo actualizar la empresa",
            )
            if filas:
                return
        self._ejecutar(
            "INSERT INTO empresa (ruc_empresa, razon_social_empresa, direccion_empresa, "
            "telefono_empresa, cuenta_corriente, id_distrito) VALUES (%s,%s,%s,%s,%s,%s)",
            (e.ruc_empresa, e.razon_social_empresa, e.direccion_empresa, e.telefono_empresa,
             e.cuenta_corriente, e.id_distrito),
            "No se pudo registrar la empresa",
        )
