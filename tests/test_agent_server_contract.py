from pathlib import Path


def test_agent_server_exposes_persistent_computer_contract():
    source = Path("src/playwright_server/agent_server.py").read_text()
    required = {
        "computer_start",
        "computer_status",
        "computer_navigate",
        "computer_text",
        "computer_screenshot",
        "computer_click",
        "computer_click_text",
        "computer_fill",
        "computer_download",
        "computer_list_downloads",
        "computer_handoff",
        "computer_close",
    }
    missing = [name for name in sorted(required) if name not in source]
    assert not missing, f"missing tools: {missing}"
