# AI Cloud & DevOps Agent – Guardrail Module

## 1. Purposes

`guardrail.py` is an application-level security and policy layer for an
AI agent that works with Cloud and DevOps systems.

The guardrail is designed to sit between:

```text
User
  |
  v
guardrail.py
  |
  +---- BLOCKED ----> Safe error message
  |
  +---- ALLOWED ----> AI Agent
                         |
                         +--> AWS
                         +--> Jenkins
                         +--> Bitbucket/Git
                         +--> Terraform
                         +--> Docker/Kubernetes
                         +--> Logs/Monitoring
                         |
                         v
                    AI Response
                         |
                         v
                 sanitize_response()
                         |
                         v
                       User
```

## 2. What the script protects against

The current version contains these controls:

### A. Empty requests

Empty or whitespace-only requests are rejected.

### B. Prompt injection

The module detects common attempts such as:

- Ignore previous instructions
- Reveal the system prompt
- Bypass guardrails
- Disable safety
- Jailbreak the agent

These requests are classified as `CRITICAL`.

### C. Secret and credential detection

The module checks for common secret patterns including:

- AWS access key IDs
- AWS secret access key assignments
- Passwords
- API keys
- Tokens
- Private keys
- Bearer tokens

The request is blocked when a potential secret is detected.

IMPORTANT:
This is pattern-based detection. It should not be treated as a complete
secret scanner. Production systems should also use a secrets manager and
secret-scanning tools.

### D. Dangerous operating-system commands

The script blocks patterns associated with destructive operations, including:

- `rm -rf /`
- `rm -rf *`
- `mkfs`
- `dd ... of=/dev/...`
- shutdown/reboot/poweroff
- disk formatting tools
- dangerous Windows delete commands
- PowerShell `Remove-Item -Recurse -Force`
- registry deletion
- disabling some system/network controls

### E. Dangerous AWS operations

The script detects potentially destructive AWS CLI/API operations such as:

- `terminate-instances`
- `delete-bucket`
- `delete-object`
- IAM deletion
- RDS deletion
- Lambda deletion
- CloudFormation stack deletion
- ECS/EKS deletion

These are classified as `HIGH`.

### F. Production destructive operations

If a request contains a production indicator such as:

- `production`
- `prod`
- `prd`

and also contains a destructive operation such as:

- delete
- terminate
- destroy
- drop
- truncate
- remove
- purge
- wipe
- revoke

the request is blocked and classified as `CRITICAL`.

For a real production agent, this should eventually become an approval
workflow rather than a simple block.

### G. Scope control

The agent is intended for AI + Cloud + DevOps work.

Examples of allowed topics:

- AWS
- Jenkins
- Bitbucket
- Git
- Terraform
- Docker
- Kubernetes
- Linux
- PowerShell
- Python
- CloudWatch
- EC2
- S3
- Lambda
- IAM
- VPC
- EKS
- ECS
- Fargate
- CI/CD
- SRE
- Monitoring
- Logs
- Automation
- Aras Innovator

A general request such as "Tell me a movie story" is rejected as
outside the intended scope.

## 3. Main classes and functions

### `GuardrailResult`

This dataclass represents the result of a guardrail check.

Fields:

```text
allowed
reason
risk_level
sanitized_input
```

Example:

```python
GuardrailResult(
    allowed=True,
    reason="Request passed guardrail validation.",
    risk_level="LOW",
    sanitized_input="How do I check EC2 CPU usage?"
)
```

### `DevOpsGuardrail`

This is the main guardrail class.

Important methods:

```text
validate_request()
detect_prompt_injection()
detect_secret()
detect_dangerous_command()
detect_dangerous_aws_operation()
is_production_destructive_operation()
is_in_scope()
sanitize_response()
```

### `validate_request()`

This is the main entry point.

The checks are intentionally performed before the request reaches the
AI agent or DevOps tools.

Flow:

```text
User Request
    |
    v
Empty check
    |
    v
Prompt Injection?
    |
    v
Secret?
    |
    v
Dangerous Shell Command?
    |
    v
Dangerous AWS Operation?
    |
    v
Production + Destructive?
    |
    v
Within DevOps Scope?
    |
    v
ALLOW
```

The first failed check returns a `GuardrailResult`.

## 4. How to use it

Place `guardrail.py` in your agent project.

Example project:

```text
ai-cloud-devops-agent/
|
+-- agent.py
+-- guardrail.py
+-- tools.py
+-- config.py
+-- requirements.txt
+-- README.md
```

In `agent.py`:

```python
from guardrail import validate_request, sanitize_response


def run_agent(user_input):

    result = validate_request(user_input)

    if not result.allowed:
        return f"Request blocked: {result.reason}"

    # Call your AI agent here.
    response = agent.invoke(user_input)

    # Protect the response before returning it.
    return sanitize_response(response)
```

## 5. Testing the file

Run:

```bash
python guardrail.py
```

The script includes sample requests and prints:

```text
Request: How do I create an EC2 instance?
Allowed: True
Risk: LOW
Reason: Request passed guardrail validation.
```

For a blocked request you should see something similar to:

```text
Request: Run rm -rf /
Allowed: False
Risk: CRITICAL
Reason: Potentially destructive shell/system command detected.
```

## 6. Important limitation

Do NOT use this file as the only security control for a production
Cloud/DevOps agent.

A secure architecture should use multiple layers:

```text
                    USER
                      |
                      v
              INPUT GUARDRAIL
                      |
                      v
                 AI / LLM
                      |
                      v
              TOOL PERMISSION
                      |
             +--------+--------+
             |                 |
          READ TOOL         WRITE TOOL
             |                 |
             |           APPROVAL REQUIRED
             |                 |
             |          +------+------+
             |          |             |
             |         DEV           PROD
             |          |             |
             |       Approval      Human Approval
             |                         |
             +------------+------------+
                          |
                          v
                    AWS / Jenkins /
                    Git / Kubernetes
                          |
                          v
                  OUTPUT GUARDRAIL
                          |
                          v
                         USER
```

Infrastructure-level controls should still include:

- AWS IAM least privilege
- AWS Organizations SCPs where appropriate
- Separate Dev/QA/Prod roles
- Jenkins authorization
- Bitbucket permissions
- Secrets Manager/Parameter Store
- Network restrictions
- CloudTrail
- CloudWatch
- Audit logging
- Human approval for sensitive production actions

## 7. Recommended production improvement

For the first version, dangerous production actions are blocked.

A better second version should return an approval requirement:

```text
User
 |
 | "Restart production service"
 v
Guardrail
 |
 +--> LOW/Routine ----> Execute
 |
 +--> MEDIUM ----------> Additional validation
 |
 +--> HIGH ------------> Approval
 |
 +--> CRITICAL --------> Block
```

For example:

```python
if action == "restart_production":
    return ApprovalRequired(
        reason="Production action requires approval"
    )
```

This allows the agent to be useful without giving an LLM unrestricted
control over production infrastructure.

## 8. Response sanitization

`sanitize_response()` should be called after the AI/tool response and
before displaying the response to the user.

Example:

```python
response = """
AWS_ACCESS_KEY_ID=AKIA1234567890123456
"""

safe_response = sanitize_response(response)
```

The result replaces the detected access key with:

```text
[REDACTED_AWS_ACCESS_KEY]
```

This provides a second protection layer in case a secret enters the
agent's output.

## 9. Recommended next modules

For a complete AI Cloud & DevOps agent, this file should eventually be
combined with:

```text
guardrail.py
     |
     +-- authentication.py
     +-- authorization.py
     +-- approval.py
     +-- audit_logger.py
     +-- tool_registry.py
     +-- secrets_manager.py
     +-- agent.py
     +-- aws_tools.py
     +-- jenkins_tools.py
     +-- git_tools.py
     +-- kubernetes_tools.py
```

The most important distinction is:

**Guardrail = "Is this request/action allowed?"**

**Authorization = "Is this user allowed to perform it?"**

**Approval = "Does this sensitive action require human approval?"**

**IAM/tool permissions = "Can the underlying system actually perform it?"**

All four should be used for a production DevOps agent.

## 10. Version

Initial version: `1.0`

Target: AI + Cloud + DevOps Agent

Language: Python 3

Dependencies: Python standard library only
