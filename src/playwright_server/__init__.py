def main():
    from .agent_server import main as agent_main
    return agent_main()

__all__ = ["main"]
