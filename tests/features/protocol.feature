Feature: Protocol with the real model
  The gateway provider teaches the JSON protocol to the real model and
  tolerates answers that are not clean JSON, without changing the agent.

  Scenario: A JSON answer inside a code block is understood
    Given a gateway assistant whose model replies with a fenced JSON answer
    When I ask "¿Quién es EMP-0004?"
    Then the response status is 200
    And the response answer is "respuesta lista"

  Scenario: A JSON answer surrounded by text is understood
    Given a gateway assistant whose model replies with text around the JSON
    When I ask "¿Quién es EMP-0004?"
    Then the response status is 200
    And the response answer is "respuesta lista"

  Scenario: A reply without JSON is an invalid answer, not a server error
    Given a gateway assistant whose model replies with plain text
    When I ask "¿Quién es EMP-0004?"
    Then the response status is 200
    And the response answer says the model reply was not understood

  Scenario: The system message is sent first and outside the history window
    Given a gateway assistant with history window 2
    When I ask "¿Quién es EMP-0004?" with a history of 10 messages
    Then the gateway received 4 messages
    And the first message sent to the gateway has the system role
    And the last message sent to the gateway is the question
