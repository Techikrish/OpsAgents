# Configuration Reference

OpsAgents loads configuration details in the following order of priority:
1. CLI flags (`--provider`, `--model`, `--aws-profile`, `--aws-region`)
2. Environment variables (`OPSAGENTS_LLM_PROVIDER`, etc.)
3. `config.yml` / `config.yaml` in the active directory
4. `~/.opsagents/config.yml`
5. Default parameters

## Configuration Schema

A typical configuration file structure is defined in [config.example.yml](../config.example.yml):

```yaml
llm:
  provider: openai          # openai | anthropic | google | bedrock | azure | ollama
  model: gpt-4o             # Target model name
  temperature: 0.1
  max_tokens: 4096

approval:
  default_policy: prompt    # auto | prompt
  risk_levels:
    low: auto               # Skip prompt for read-only actions
    medium: prompt          # Ask for mutation actions
    high: prompt            # Ask for destructive actions
    critical: confirm       # Require CONFIRM typing

aws:
  profile: default
  region: us-east-1

logging:
  level: INFO
```
