Feature: The reviewer, the fallback model and the latency of questions
  The reviewer may ask the directory agent for one correction, the product
  survives a failing large model, and latency only measures real questions.

  Scenario: The reviewer asks for one correction and then approves
    Given the app runs with "FAKE_REVIEWER_RETRY_ONCE" set to "true"
    When I ask "Quien es EMP-0001?"
    Then the review retries are 1
    And the agents used are "classifier, directory, reviewer, directory, reviewer"
    And the run log records the review reason "Falta el puesto del empleado."

  Scenario: An approved answer reports zero retries and no reason
    Given the app runs with "REVIEWER_ENABLED" set to "true"
    When I ask "Quien es EMP-0001?"
    Then the review retries are 0
    And the run log records no review reason

  Scenario: The correction is requested again for every new question
    Given the app runs with "FAKE_REVIEWER_RETRY_ONCE" set to "true"
    When I ask "Quien es EMP-0001?" twice
    Then every response reports 1 review retries

  Scenario: A disabled reviewer is not called
    Given the app runs with "REVIEWER_ENABLED" set to "false"
    When I ask "Quien es EMP-0001?"
    Then the agents used are "classifier, directory"

  Scenario: A failing large model falls back to the small model
    Given the app runs with "FAKE_FAIL_LARGE" set to "true"
    When I ask "Quien es EMP-0001 y en que departamento trabaja, dame su puesto y su fecha de ingreso completa"
    Then the response fallback is true
    And the log has a model_fallback event

  Scenario: Without failures there is no fallback
    Given the app runs with "FAKE_FAIL_LARGE" set to "false"
    When I ask "Quien es EMP-0001?"
    Then the response fallback is false
    And the log has no model_fallback event

  Scenario: Health checks do not hide the latency of questions
    Given the app measures time with a switchable clock
    When the load balancer calls health 20 times
    And I ask 2 slow questions
    Then the metrics count 2 ask requests and 22 requests
    And the metrics p50 latency is at least 3000 milliseconds

  Scenario: Several kinds of personal data are reported without repeats
    Given the app runs with "REVIEWER_ENABLED" set to "true"
    When I ask "Quien es EMP-0001? Mi tarjeta 4111111111111111 y mi correo a@b.com"
    Then pii detected is "card, email"
    And the text "4111111111111111" is not in the log
