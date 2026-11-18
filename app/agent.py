"""Agente con bucle acotado y dos herramientas de solo lectura."""

import json
from typing import Dict, List, Optional

from app.directory import Directory
from app.llm import TOOL_RESULT_PREFIX

LIMIT_ANSWER = "No pude completar la respuesta. Intenta con una pregunta más concreta."
INVALID_ANSWER = "No pude entender la respuesta del modelo. Intenta de nuevo."


class Agent:
    """Agente que alterna entre el modelo y las herramientas.

    :param model: Modelo con ``complete(messages)``.
    :param directory: Directorio de empleados.
    :type directory: Directory
    :param max_steps: Tope de vueltas del bucle.
    :type max_steps: int
    :param on_tool: Observador ``on_tool(name, args)`` llamado por cada
        herramienta (para el evento ``audit``).
    :param tracer: Trazador opcional para marcar cada herramienta.
    """

    def __init__(
        self, model, directory: Directory, max_steps: int, on_tool=None, tracer=None
    ):
        self._model = model
        self._directory = directory
        self._max_steps = max_steps
        self._on_tool = on_tool
        self._execute = self._run_tool
        if tracer is not None:
            self._execute = tracer.traceable(name="tool", run_type="tool")(
                self._run_tool
            )

    def _run_tool(self, name: str, args: dict) -> str:
        """Ejecuta una herramienta y devuelve su resultado como texto.

        :param name: Nombre de la herramienta.
        :type name: str
        :param args: Argumentos pedidos por el modelo.
        :type args: dict
        :return: Resultado legible para el modelo.
        :rtype: str
        """
        try:
            if name == "get_employee":
                employee_id = str(args["employee_id"])
                employee = self._directory.get_employee(employee_id)
                if employee is None:
                    return f"El empleado {employee_id} no existe."
                return json.dumps(employee, ensure_ascii=False)
            department = str(args["department"])
            found = self._directory.search_by_department(department)
            if not found:
                return f"No hay empleados en el departamento {department}."
            return json.dumps(found, ensure_ascii=False)
        except (KeyError, TypeError):
            return f"Argumentos inválidos para {name}."

    def _tokens(self) -> tuple:
        """Lee los contadores acumulados del modelo (0 si no los tiene)."""
        return (
            getattr(self._model, "input_tokens", 0),
            getattr(self._model, "output_tokens", 0),
        )

    def run(self, question: str, history: Optional[List[Dict[str, str]]] = None):
        """Responde una pregunta.

        :param question: Pregunta de la persona.
        :type question: str
        :param history: Mensajes previos enviados por el cliente.
        :type history: list or None
        :return: ``answer``, ``steps``, ``tools_used``, ``tool_results``,
            ``input_tokens``, ``output_tokens`` y ``stopped`` (``answer``,
            ``max_steps`` o ``invalid``).
        :rtype: dict
        """
        messages = [dict(m) for m in (history or [])]
        messages.append({"role": "user", "content": question})
        start = self._tokens()
        tools_used: List[str] = []
        tool_results: List[str] = []
        steps = 0
        answer = LIMIT_ANSWER
        stopped = "max_steps"
        while steps < self._max_steps:
            steps += 1
            try:
                decoded = json.loads(self._model.complete(messages))
            except json.JSONDecodeError:
                decoded = None
            if not isinstance(decoded, dict):
                answer = INVALID_ANSWER
                stopped = "invalid"
                break
            if "answer" in decoded:
                answer = str(decoded["answer"])
                stopped = "answer"
                break
            name = decoded.get("tool")
            args = decoded.get("args")
            if name in ("get_employee", "search_by_department"):
                args = args if isinstance(args, dict) else {}
                tools_used.append(name)
                if self._on_tool is not None:
                    self._on_tool(name, args)
                result = self._execute(name, args)
                tool_results.append(result)
            else:
                result = f"Herramienta desconocida: {name}."
            messages.append({"role": "user", "content": TOOL_RESULT_PREFIX + result})
        end = self._tokens()
        return {
            "answer": answer,
            "steps": steps,
            "tools_used": tools_used,
            "tool_results": tool_results,
            "input_tokens": end[0] - start[0],
            "output_tokens": end[1] - start[1],
            "stopped": stopped,
        }
