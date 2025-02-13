import asyncio
import logging
import sys
from dotenv import load_dotenv

from .. import models, database

print("Script starting...")

# Configure logging first
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    force=True,
    handlers=[logging.StreamHandler(sys.stdout)]  # Explicitly use stdout
)
logger = logging.getLogger(__name__)
print("Logging configured")

load_dotenv()

from app.services.agent_new import Agent, Event, EventTypes

async def main():
    
    # Create database tables
    models.Base.metadata.create_all(bind=database.engine)
    
    print("Entering main()")
    logger.info("Starting test run")
    agent = Agent("test-thread")
    
    try:
        # Make handle_event awaitable
        agent.handle_event(Event(type=EventTypes.USER, data="Get the latest email for me. Start by asking me for the login credentials."))
        
        # Keep the event loop running
        while True:
            print("Tick...")
            logger.debug("Waiting for events to complete...")
            await asyncio.sleep(10)
    except KeyboardInterrupt:
        logger.info("Test run interrupted")
    except Exception as e:
        logger.error(f"Error in main: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nScript interrupted by user")
    except Exception as e:
        print(f"Fatal error: {e}")