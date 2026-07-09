import argparse
import json

from app.router import route_ticket


def main() -> None:
    parser = argparse.ArgumentParser(description="Route a support ticket")
    parser.add_argument("ticket", nargs="?", default="", help="Ticket text to route")
    args = parser.parse_args()

    ticket_text = args.ticket.strip()
    result = route_ticket(ticket_text)
    provider = result.get("provider", "unknown")
    error = result.get("provider_error")
    print(f"Provider used: {provider}")
    if error:
        print(f"Provider error: {error}")
    print()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
