#!/usr/bin/env python3
"""
Main entry point for the Agnikul Agent application.
Supports both CLI and server modes.
"""

import sys
import argparse
import asyncio
import uvicorn

from dispatcher import run_agent


async def cli_mode(question: str):
    """Run agent in CLI mode."""
    print(f"Question: {question}\n")
    result = await run_agent(question)
    print(f"\nFinal Result: {result}")


def server_mode(host: str = "0.0.0.0", port: int = 8000, reload: bool = False):
    """Run agent as FastAPI server."""
    print(f"Starting server on {host}:{port}")
    print(f"Reload mode: {reload}")
    print("\nAvailable endpoints:")
    print(f"  - POST http://{host}:{port}/v1/query - Non-streaming queries")
    print(f"  - POST http://{host}:{port}/v1/stream - Streaming queries")
    print(f"  - GET  http://{host}:{port}/v1/tools - List available tools")
    print(f"  - GET  http://{host}:{port}/health - Health check")
    print(f"  - POST http://{host}:{port}/v1/upload - File upload")
    print("\nPress CTRL+C to stop\n")
    
    uvicorn.run(
        "api:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info"
    )


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Agnikul Agent - LangChain 1.0+ powered assistant with tool calling and reasoning"
    )
    
    subparsers = parser.add_subparsers(dest="mode", help="Mode to run the agent")
    
    # CLI mode
    cli_parser = subparsers.add_parser("cli", help="Run agent in CLI mode")
    cli_parser.add_argument("question", type=str, help="Question to ask the agent")
    
    # Server mode
    server_parser = subparsers.add_parser("server", help="Run agent as FastAPI server")
    server_parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind to")
    server_parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    server_parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    
    args = parser.parse_args()
    
    if args.mode == "cli":
        asyncio.run(cli_mode(args.question))
    elif args.mode == "server":
        server_mode(host=args.host, port=args.port, reload=args.reload)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()