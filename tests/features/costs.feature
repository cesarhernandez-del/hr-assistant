Feature: Cost per answer
  Every answer says which model was used and how much it cost, and the cost
  levers must not hide failures or leak secrets.

  Scenario: A simple question uses the small model
    Given a costed assistant
    When I ask "¿Quién es EMP-0004?"
    Then the response model is the small model
    And the response route is not empty
    And the response cost is greater than zero

  Scenario: A comparison question uses the large model
    Given a costed assistant
    When I ask "Compara a los empleados del departamento de Finanzas"
    Then the response model is the large model
    And the response route mentions "compara"

  Scenario: A short history window sends fewer input tokens
    Given a costed assistant with history window 2
    And a second costed assistant with history window 20
    When I ask "¿Quién es EMP-0004?" with a history of 10 messages on both
    Then the first assistant used fewer input tokens than the second

  Scenario: A gateway cache hit costs nothing
    Given a gateway assistant whose cache status is "HIT"
    When I ask "¿Quién es EMP-0004?"
    Then the response has at least 1 cached call
    And the response cost is zero

  Scenario: A failing gateway answers 502 and hides the token
    Given a gateway assistant that fails with status 500
    When I ask "¿Quién es EMP-0004?"
    Then the response status is 502
    And the response detail is "model unavailable"
    And the response has a request id
    And neither the response nor the log contain the API token

  Scenario: The metrics add up the cost of every answer
    Given a costed assistant
    When I ask "¿Quién es EMP-0004?"
    And I ask "¿Quién es EMP-0005?"
    Then the metrics cost equals the sum of the answer costs
