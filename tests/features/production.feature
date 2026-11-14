Feature: Safe production access
  Only clients with a key can ask, nobody can flood the service, and an unsafe
  production configuration never starts.

  Scenario: Asking without a valid key is rejected
    Given a secured assistant
    When I ask "Who is EMP-0004?" without a key
    Then the response status is 401
    And the response detail is "invalid or missing API key"
    When I ask "Who is EMP-0004?" with the key "not-a-real-key"
    Then the response status is 401
    And the response detail is "invalid or missing API key"

  Scenario: Only ask and metrics need a key
    Given a secured assistant
    When I read the metrics without a key
    Then the response status is 401
    When I read the metrics as "alice"
    Then the response status is 200
    When I open the root page, health and docs without a key
    Then all three open pages answer 200

  Scenario: The client name reaches the log and the audit
    Given a secured assistant
    When "alice" asks "Who is EMP-0004?"
    And "bob" asks "Who is EMP-0001?"
    Then the response status is 200
    And the agent_run events belong to "alice" and then "bob"
    And the audit event for employee EMP-0004 belongs to "alice"

  Scenario: The key is never written to the log or to a response
    Given a secured assistant
    When "alice" asks "Who is EMP-0004?"
    And I ask "Who is EMP-0004?" with the key "alice-key-0123456789abcdeX"
    Then the key of "alice" is not in the log
    And the key of "alice" is not in any response

  Scenario: The third request in a minute is limited and the window reopens
    Given a secured assistant with a limit of 2 requests per minute
    When "alice" asks 3 times in a row
    Then the response status is 429
    And the response detail is "rate limit exceeded"
    And the Retry-After header is between 1 and 60
    When "bob" asks "Who is EMP-0001?"
    Then the response status is 200
    When the clock advances 60 seconds
    And "alice" asks "Who is EMP-0004?"
    Then the response status is 200

  Scenario: Requests with an invalid key do not use the quota of a client
    Given a secured assistant with a limit of 2 requests per minute
    When I ask "Who is EMP-0004?" with the key "not-a-real-key" 5 times
    And "alice" asks "Who is EMP-0004?"
    Then the response status is 200

  Scenario Outline: Production refuses an unsafe configuration
    When I start the assistant with the environment <settings>
    Then the start is refused with a message about <reason>

    Examples:
      | settings                                                        | reason       |
      | ENVIRONMENT=production MODEL_PROVIDER=fake API_KEYS=a:KEYKEYKEYKEYKEYKEYKEY | fake         |
      | ENVIRONMENT=production MODEL_PROVIDER=gateway API_KEYS=                     | API_KEYS     |
      | ENVIRONMENT=production MODEL_PROVIDER=gateway API_KEYS=a:short              | 16           |

  Scenario: A malformed API_KEYS blocks the start without revealing the value
    When I start the assistant with the environment API_KEYS=just-a-secret-value
    Then the start is refused with a message about entry 1
    And the message gives the length 19
    And the message does not contain "just-a-secret-value"
