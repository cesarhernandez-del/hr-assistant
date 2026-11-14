Feature: Observability of every request
  Anyone can find out what happened with a request from its id, the JSON log
  and the process metrics, without the log ever holding personal text.

  Scenario: A request without an id gets a generated one
    Given an observed assistant
    When I send "Who is EMP-0004?"
    Then the X-Request-ID header is a valid UUID
    And the response body request_id equals the header

  Scenario: The id sent by the client is kept everywhere
    Given an observed assistant
    When I call with request id "demo-123" asking "Who is EMP-0004?"
    Then the X-Request-ID header is "demo-123"
    And the response body request_id is "demo-123"
    And every log line carries the request id "demo-123"

  Scenario: Every request leaves a request event
    Given an observed assistant
    When I send "Who is EMP-0004?"
    Then the log has a request event for POST /ask with status 200
    And that request event has a latency of 250 ms

  Scenario: An agent run is logged without the question or the answer
    Given an observed assistant
    When I send "Tell me about EMP-0004 please"
    Then the log has an agent_run event with 2 steps and stopped "answer"
    And the log does not contain "Tell me about EMP-0004 please"
    And the log does not contain "Jorge"

  Scenario: Each tool call is audited
    Given an observed assistant
    When I send "Who is EMP-0004?"
    Then the log has an audit event for tool "get_employee" with employee EMP-0004

  Scenario: An internal failure returns a safe 500 and an error event
    Given an assistant whose model fails with a secret message
    When I send "Who is EMP-0004?"
    Then the response status is 500
    And the response detail is "internal error"
    And the response body request_id equals the header
    And the log has an error event of type "RuntimeError"
    And the log does not contain "secret boom"

  Scenario: Metrics summarize the requests of the process
    Given an observed assistant
    When I send "Who is EMP-0004?"
    And I send "Who is EMP-0001?"
    And I read the metrics
    Then the metrics show at least 2 requests and an error rate of 0
    And the metrics show p50, p95, token counts and the pid
    And the service level objective is met

  Scenario: The service level objective is missed when requests are slow
    Given an observed assistant where each request takes 3 seconds
    When I send "Who is EMP-0004?"
    And I read the metrics
    Then the service level objective is not met
