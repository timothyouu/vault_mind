# vault-mind-orchestrate

A Fetch.ai chat agent (ASI:One ready) built on the uAgents framework. It speaks the chat
protocol, so it's ASI:One ready out of the box. Generated with
[create-fetch-agent](https://github.com/anishkancherla-fetchai/create-fetch-agent).

## Setup

The agent's seed is already generated in `.env`. Install dependencies:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
make run
```

The agent starts on port 8000 and logs its address and an
Agentverse inspector URL.

## Where to add your logic

`agent.py` has an `agent_workflow(query)` function — the single extension point.
Return the response string for a given user query:

```python
def agent_workflow(query: str) -> str:
    return my_llm_call(query)
```

## Talk to it on ASI:One

`mailbox=True` and `publish_agent_details=True` are set, so connect `vault_mind_orchestrate`
through the Agentverse inspector and chat with it via ASI:One. The inspector URL
is logged on startup.
