from ..models import Thread, Message
from ..schemas import MessageCreate

agents = {}

@app.post("/api/threads/{thread_id}/start_agent_loop")
async def start_agent_loop():
    if thread_id not in agent_loops:
        agent = Agent()
        agents[thread_id] = agent
    else:
        agent = agents[thread_id]
        
    agent.start()
    
    pass

@app.post("/api/threads/{thread_id}/stop_agent_loop")
async def stop_agent_loop():
    if thread_id in agents:
        agents[thread_id].stop()
        
    pass

@app.post("/api/threads/{thread_id}/interrupt_agent_loop")
async def interrupt_agent_loop(user_message):
    if thread_id in agents:
        agents[thread_id].add_user_interrupt(user_message)
        
    pass

@app.get("/api/threads/{thread_id}/get_state_and_messages")
async def get_state_and_messages(start: int, end: int):
    # the state contains information about if the agent is running, the current sequence number
    pass

@app.post("/api/threads/{thread_id}/submit_user_input")
async def submit_user_input(user_message):
    pass

@app.websocket("/api/threads/{thread_id}/websocket")
async def websocket_endpoint(self):
    pass

class Agent:
    on_new_message = None
    
    def __init__(self, thread: Thread):
        self.thread = thread
    
    def start(self):
        self.task = asyncio.create_task(self.run())
        self.running = True
        
    def stop(self):
        self.running = False
        if hasattr(self, 'task'):
            self.task.cancel()
    
    def add_user_interrupt(self, user_message):
        # stops the loop without waiting for current step to finish
        # add user interrupt message to stack
        # continue loop 
        pass
    
    async def run(self):
        while self.running:
            await self.run_step()
    
    async def run_step(self):
        # run one step of the agent loop (llm call + tool call)
        # add messages to the db and callback on_new_message
        pass
    
    
    
