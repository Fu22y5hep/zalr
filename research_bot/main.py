import argparse
import asyncio

from .manager import ResearchManager


async def main() -> None:
    # Set up argument parser
    parser = argparse.ArgumentParser(description="Research Bot - Automated research assistant")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode with detailed logging")
    args = parser.parse_args()
    
    query = input("What would you like to research? ")
    await ResearchManager(debug=args.debug).run(query)


if __name__ == "__main__":
    asyncio.run(main()) 