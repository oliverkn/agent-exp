import asyncio
from app.services.agent_new import Agent, Event, EventTypes
from dotenv import load_dotenv

async def main():
    load_dotenv()
    
    agent = Agent("test-thread")
    event = Event(type=EventTypes.USER, data="Get the latest email for me.")
    agent.handle_event(event)
    
    # Keep the program running to allow async operations to complete
    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
