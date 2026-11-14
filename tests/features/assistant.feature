Feature: HR Assistant answers questions about employees
  HR staff ask questions and the agent answers using read-only directory tools.

  Scenario: Looking up an employee by id
    Given an assistant with the sample employee directory
    When I ask "¿Quién es EMP-0004?"
    Then the answer contains "Jorge Díaz"
    And the tools used are "get_employee"
    And token counts are reported

  Scenario: Looking up an employee that does not exist
    Given an assistant with the sample employee directory
    When I ask "¿Quién es EMP-9999?"
    Then the answer contains "EMP-9999"
    And the answer says the employee does not exist

  Scenario: Listing the employees of a department
    Given an assistant with the sample employee directory
    When I ask "¿Quién trabaja en Tecnología?"
    Then the answer contains "Ana López"
    And the answer contains "Marta Ruiz"
    And the answer contains "Jorge Díaz"
    And the answer does not contain "Luis Pérez"
    And the tools used are "search_by_department"

  Scenario: A question without an id or a department gets a suggestion
    Given an assistant with the sample employee directory
    When I ask "Hola"
    Then the answer is "Pregúntame por un empleado (EMP-0001) o un departamento."
    And no tools are used

  Scenario: The step limit is reached before an answer
    Given an assistant limited to 1 step
    When I ask "¿Quién es EMP-0004?"
    Then the answer is "No pude completar la respuesta. Intenta con una pregunta más concreta."

  Scenario Outline: Invalid questions are rejected
    Given an assistant with the sample employee directory
    When I send a question of <length> characters
    Then the API responds with status 422

    Examples:
      | length |
      | 0      |
      | 2001   |

  Scenario: The health endpoint reports the process
    Given an assistant with the sample employee directory
    When I request the health endpoint
    Then the health status is "ok" and the pid is the current process

  Scenario: The history sent by the client is used but never stored
    Given an assistant that records what the model receives
    When I continue a conversation asking "¿Y su departamento?"
    Then the model received the previous conversation before the question
    When I start over asking "Hola"
    Then the model did not receive the previous conversation again

  Scenario: The home page is served with its test ids
    Given an assistant with the sample employee directory
    When I request the home page
    Then the page contains the test ids "question", "send" and "answer"
