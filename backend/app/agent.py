from openai import OpenAI
import json
import pydantic


from tools import *


class Agent:
    def __init__(self, tool_box: ToolBox, model: str):
        self.tool_box = tool_box
        self.model = model


        self.client = OpenAI(api_key="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")

    def run(self):
        
        messages = []
        messages.append({"role": "developer", "content": [{"type" : "text", "text" : "Your task is to get the latest email by using the available tools."}]})
        
        
        tools = []
        for tool in self.tool_box.get_tools():
            schema = to_function_schema(tool)
            # print(schema)
            tools.append(schema)
            
        # print(json.dumps(tools, indent=4))
        
        for i in range(5):
        
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
                tool_choice="required",
                # parallel_tool_calls=False
            )
            
            response = completion.choices[0].message
            # print(response)
            messages.append(response)
            
            for tool_call in completion.choices[0].message.tool_calls:
                name = tool_call.function.name
                args = tool_call.function.arguments

                print(f"{name}({args})")
                result = tool_box.call(name, args)
                print(result)
                
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result)
                })
        
        pass

def to_function_schema(tool):    
    return {
        "type": "function",
        "function": {
            "name": tool.tool_name,
            "description": tool.tool_description,
            "parameters": {
                "type": "object",
                "properties": tool.args_model.schema()["properties"]},
                "required": list(tool.args_model.schema()["properties"].keys()),
                "additionalProperties": False
            },
            "strict": True
        }
    
tool_box = ToolBox()
tool_box.add_tool(UserInput())
tool_box.add_tool(SetupMSGraph())
tool_box.add_tool(AuthenticateMSGraph())
tool_box.add_tool(GetLatestEmail())

agent = Agent(tool_box, "gpt-4o-mini")

agent.run()