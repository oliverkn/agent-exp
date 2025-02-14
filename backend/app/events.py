from sqlalchemy import event
from .models import Message
from .connections import manager
import asyncio
import logging

logger = logging.getLogger(__name__)

def setup_db_events(db):
    def handle_message_event(mapper, connection, message, event_type='message_update'):
        try:
            thread_id = message.thread_id
            logger.info(f"Message {event_type} detected for thread {thread_id}")
            
            # Create a dict representation of the message, handling null values
            message_dict = {
                "id": message.id,
                "role": message.role,
                "content": message.content if message.content is not None else None,
                "agent_state": message.agent_state if message.agent_state is not None else None,
                "created_at": str(message.created_at),
                "tool_name": message.tool_name if message.tool_name is not None else None,
                "tool_call_id": message.tool_call_id if message.tool_call_id is not None else None,
                "tool_result": message.tool_result if message.tool_result is not None else None
            }
            
            # Remove None values to ensure clean JSON
            message_dict = {k: v for k, v in message_dict.items() if v is not None}
            
            event_data = {
                "event_type": event_type,
                "thread_id": thread_id,
                "message": message_dict
            }
            
            # Create a new event loop in a separate thread for the broadcast
            def run_broadcast():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(manager.broadcast_to_thread(thread_id, event_data))
                finally:
                    loop.close()
            
            # Run the broadcast in a separate thread
            import threading
            thread = threading.Thread(target=run_broadcast)
            thread.start()
            
            # manager.broadcast_to_thread(thread_id, event_data)
            
            logger.info(f"Broadcast message sent for thread {thread_id}: {event_data}")
        except Exception as e:
            logger.error(f"Error in message {event_type} event handler: {str(e)}")

    # Set up event listeners using the unified handler
    event.listen(Message, 'after_insert', 
                lambda m, c, msg: handle_message_event(m, c, msg, 'message_insert'))
    event.listen(Message, 'after_update', 
                lambda m, c, msg: handle_message_event(m, c, msg, 'message_update'))
    event.listen(Message, 'after_delete', 
                lambda m, c, msg: handle_message_event(m, c, msg, 'message_update')) 