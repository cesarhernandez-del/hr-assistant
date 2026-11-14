"""Directorio de empleados de solo lectura."""

import json
from pathlib import Path
from typing import Dict, List, Optional


class Directory:
    """Consulta empleados cargados en memoria.

    :param employees: Lista de empleados (diccionarios).
    :type employees: list
    """

    def __init__(self, employees: List[dict]):
        self._employees = [dict(item) for item in employees]

    @classmethod
    def from_file(cls, path: Path) -> "Directory":
        """Carga el directorio desde un archivo JSON.

        :param path: Ruta del archivo.
        :type path: Path
        :return: Directorio con los empleados del archivo.
        :rtype: Directory
        """
        with open(path, encoding="utf-8") as handle:
            return cls(json.load(handle))

    def departments(self) -> List[str]:
        """Devuelve los departamentos existentes, sin repetir.

        :return: Nombres de departamento en orden de aparición.
        :rtype: list
        """
        return list(dict.fromkeys(e["department"] for e in self._employees))

    def get_employee(self, employee_id: str) -> Optional[Dict]:
        """Busca un empleado por id.

        :param employee_id: Id, por ejemplo ``EMP-0004``.
        :type employee_id: str
        :return: El empleado o ``None`` si no existe.
        :rtype: dict or None
        """
        for employee in self._employees:
            if employee["id"] == employee_id:
                return dict(employee)
        return None

    def search_by_department(self, department: str) -> List[Dict]:
        """Lista los empleados de un departamento, sin distinguir mayúsculas.

        :param department: Nombre del departamento.
        :type department: str
        :return: Empleados del departamento (vacío si no existe).
        :rtype: list
        """
        wanted = department.casefold()
        return [
            dict(e) for e in self._employees if e["department"].casefold() == wanted
        ]
