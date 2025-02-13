from sqlalchemy import event
from .models import Message
from .connections import manager
import asyncio
import logging

logger = logging.getLogger(__name__)

def setup_db_events(db):
    @event.listens_for(Message, 'after_insert')
    def after_message_insert(mapper, connection, message):
        try:
            thread_id = message.thread_id
            logger.info(f"Message insert detected for thread {thread_id}")
            asyncio.create_task(manager.broadcast_to_thread(thread_id, {
                "type": "message_update",
                "thread_id": thread_id
            }))
            logger.info(f"Broadcast message sent for thread {thread_id}")
        except Exception as e:
            logger.error(f"Error in message insert event handler: {str(e)}")

    @event.listens_for(Message, 'after_update')
    def after_message_update(mapper, connection, message):
        try:
            thread_id = message.thread_id
            logger.info(f"Message update detected for thread {thread_id}")
            asyncio.create_task(manager.broadcast_to_thread(thread_id, {
                "type": "message_update",
                "thread_id": thread_id
            }))
            logger.info(f"Broadcast message sent for thread {thread_id}")
        except Exception as e:
            logger.error(f"Error in message update event handler: {str(e)}")

    @event.listens_for(Message, 'after_delete')
    def after_message_delete(mapper, connection, message):
        try:
            thread_id = message.thread_id
            logger.info(f"Message delete detected for thread {thread_id}")
            asyncio.create_task(manager.broadcast_to_thread(thread_id, {
                "type": "message_update",
                "thread_id": thread_id
            }))
            logger.info(f"Broadcast message sent for thread {thread_id}")
        except Exception as e:
            logger.error(f"Error in message delete event handler: {str(e)}") 