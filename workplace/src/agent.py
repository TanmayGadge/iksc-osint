from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, InjectedState
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from langgraph.checkpoint.mongodb import MongoDBSaver

from langchain_core.tools import tool, InjectedToolCallId
# from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, BaseMessage, HumanMessage, ToolMessage, AIMessage
from langchain_core.runnables import RunnableConfig

from typing import TypedDict, Annotated, cast, Dict, Any
from pydantic import BaseModel, Field, SecretStr

import json
from dotenv import load_dotenv, find_dotenv
import httpx
import os
from pathlib import Path
from urllib.parse import quote_plus
from pymongo import AsyncMongoClient, MongoClient
from pymongo.errors import PyMongoError
import argparse
from uuid import uuid7

from tools.linkedin_profile_finder import GoogleLinkedInFinder
from src.extract import parse_biodata_image
from src.new_person_core_schema import LinkedInProfile
from src.tool_loader import find_existing_tool, create_langchain_tool_adapter

load_dotenv(find_dotenv())

client = MongoClient(host=os.getenv("MONGODB_CONNECTION_STRING"))

class AgentState(TypedDict):
    initial_user_data: dict
    full_name: str
    biodata_image_url: str
    profiles: list[dict]
    biodata: dict
    top_user_profile_url: str
    linkedin_json: dict
    platform_name: str
    final_data: dict
    
    messages: Annotated[list[BaseMessage], add_messages]



@tool
def fetch_linkedin_profile_urls(state: Annotated[AgentState, InjectedState],
                                tool_call_id: Annotated[str, InjectedToolCallId]):
    """Fetches potential LinkedIn profile urls along with other metadata from given data about the user."""
    
    finder = GoogleLinkedInFinder(state["biodata"])
    results = finder.execute_search(5)

    return Command(
        update={
            "profiles": results,
            "messages": [
                ToolMessage(
                    content="Fetched linkedin profile urls of potential matches to the given user",
                    tool_call_id=tool_call_id
                )
            ]
        }
    )

@tool
def apify_scraper(state: Annotated[AgentState, InjectedState], 
                  tool_call_id: Annotated[str, InjectedToolCallId]):
    """Queries Apify API for both LinkedIn profile data and posts data for the given URL,

    merges them into a single payload, and writes to disk.
    """
    
    with httpx.Client(timeout=120.0) as client:
        headers = {
            "Authorization": f"Bearer {os.getenv('APIFY_API_KEY')}",
            "Content-Type": "application/json",
        }
         
        payload = {
            "queries": [
                state['top_user_profile_url']
            ]
        }
        
        profile_res =  client.post(
                "https://api.apify.com/v2/actors/harvestapi~linkedin-profile-scraper/run-sync-get-dataset-items",
                json=payload,
                headers=headers
        )
        
        posts_payload = {
            "targetUrls": [state['top_user_profile_url']],
            "maxPosts": 10,
            "scrapeComments": True,
            "maxComments": 10,
        }
        posts_res = client.post(
            "https://api.apify.com/v2/actors/harvestapi~linkedin-profile-posts/run-sync-get-dataset-items",
            json=posts_payload,
            headers=headers,
        )
        
        full_name = state['full_name'].lower()
        full_name = full_name.split(" ")
        
        
        if profile_res.status_code in (200, 201) and posts_res.status_code in (
            200,
            201,
        ):
            profile_data = profile_res.json()
            posts_data = posts_res.json()

            
            if isinstance(profile_data, list) and len(profile_data) > 0:
                profile_data[0]["posts"] = posts_data
                dataset_items = profile_data
            elif isinstance(profile_data, dict):
                profile_data["posts"] = posts_data
                dataset_items = [profile_data]
            else:
                dataset_items = profile_data
            relative_path = Path(f"./{full_name[0]}-{full_name[1]}-apify-scraper-response.json")
            abs_path = (Path(__file__).parent / relative_path).resolve()
            
            with open(abs_path, "w", encoding="utf-8") as file:
                json.dump(dataset_items, file, indent=4)
            file.close()

            print(
                "Profile and Posts data written to file 'tanmay-gadge.json' successfully!"
            )

            return Command(
                update={
                    "linkedin_json": dataset_items,
                    "messages": [
                        ToolMessage(
                            content="Successfully fetched profile and posts data",
                            tool_call_id=tool_call_id,
                        )
                    ],
                }
            )
        else:
            error_details = (
                f"Profile Status: {profile_res.status_code} ({profile_res.text}) | "
                f"Posts Status: {posts_res.status_code} ({posts_res.text})"
            )
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=f"Error fetching data: {error_details}",
                            tool_call_id=tool_call_id,
                        )
                    ]
                }
            )

LOADED_TOOLS_REGISTRY = {
    "fetch_linkedin_profile_urls": fetch_linkedin_profile_urls,
    "apify_scraper": apify_scraper,
}

# model = ChatGoogleGenerativeAI(model='gemini-2.5-flash')
model = ChatOpenAI(
    model="vibeconde-claude-sonnet-5-5-medium",
    api_key=SecretStr(os.getenv("LITELLM_API_KEY") or ""),
    base_url=os.getenv("LITELLM_BASE_URL")
)
model_with_tools = model.bind_tools([fetch_linkedin_profile_urls, apify_scraper])
dynamically_attached_tools = []
LOADED_TOOLS_REGISTRY = {}

    

def biodata_extractor(state: AgentState):
    full_name = state['full_name'].lower()
    full_name = full_name.split(" ")
    
    print(f"Checking cache for biodata file...")
    
    relative_path = f'../json-files/{full_name[0]}-{full_name[1]}.json'
    abs_path = (Path(__file__).parent / relative_path).resolve()
    
    with open(abs_path, "r", encoding='utf-8') as file:
        if file:
            #Search in the database instead of filesystem
            print(f"File {file.name} found in cache.")
            biodata = json.load(file)
            file.close()
        else:
            print("File not found in cache.", "Querying Gemini API to extract JSON data from biodata image...", sep= "\n")
            print(f"\nExtracting biodata from image...", flush=True)
            biodata = parse_biodata_image(state["biodata_image_url"])
            
            print("Writing extracted JSON data to local file...")
            relative_path = Path(f'../json-files/{biodata['first_name']}-{biodata['last_name']}.json')
            abs_path = (Path(__file__).parent / relative_path).resolve()
            
            with open(abs_path, 'w', encoding='utf-8') as file:
                json.dump(biodata, file, indent=4)
            file.close()
            
            try:
                print(f"Inserting user's extracted biodata in mongodb...", flush=True)
                db = client['user-data']
                db['biodata'].insert_one(biodata)
                print(f"Biodata JSON inserted successfully!")
                
            except PyMongoError as e:
                print(f"Error while inserting biodata json into mongodb: {e}")
            
            
            print("JSON data written to local file successfully.\n")
            
    file.close()
    ai_msg = AIMessage(
        content="Use this extracted biodata json to fetch the profile data.\n"
        f"Biodata JSON(separated by triple backticks): ```{biodata}```"
    )
    
    return {"biodata": biodata, "messages": [ai_msg]}

# def tool_resolver(state: AgentState):
#     platform = state['platform_name']
#     tool_path = find_existing_tool(platform_name=platform)
#     global model_with_tools
#     global dynamically_attached_tools
    
#     if not tool_path:
#         print(f"[Tool Resolver] Tool for '{platform}' not found in ./tools/!")
#         user_approval = input("Do you want to call the coding-agent to build it? (y/n): ").lower()
#         if user_approval == 'y':
#             "Call multi-agent coder"
#             print(f"MAS API call not yet implemented")
#         else:
#             print(f"\nExiting workflow as the required tool does not exist...")
#             os._exit(1)
#     else:
#         print(f"Tool found at: {tool_path}")
#         print("Attaching tool to model")
#         from tool_loader import create_langchain_tool_adapter
        
#         tool = create_langchain_tool_adapter(file_path=tool_path, platform_name=platform)
        
#         existing_tools = list(getattr(model_with_tools, "kwargs", {}).get("tools", []))
#         existing_tools.append(tool)
#         dynamically_attached_tools.append(tool_path)
        
#         model_with_tools = model.bind_tools(existing_tools)
#         print("Tool attached successfully!")


def profile_agent_node(state: AgentState):
    full_name = state['full_name'].lower()
    full_name = full_name.split(" ")
    
    platform = state['platform_name'].lower().strip()
    tool_name = f"fetch_{platform}_profile"
    
    # with open(f'./{full_name[0]}-{full_name[1]}-linkedin.json', "r", encoding='utf-8') as file:
    #     if file:
    #         print(f"File {file.name} found in cache.")
    #         ai_msg = AIMessage(
    #             content=f"LinkedIn data of the user already exists in the cache. In the file ./{full_name[0]}-{full_name[1]}-linkedin.json")
    #         return {"messages": [ai_msg]}
    #     else:
    platform = state['platform_name']
    # system_msg = SystemMessage(
    #     content="You are a tool call agent.\n"
    #     "You're job to call the required tool (with proper arguments) from the given tools to fetch the profile data of the user.\n"
    #     f"Call the appropriate tool to fetch the given user's data from the given platform: {platform}\n"
    #     "DON'T write anh custom search queries, just call the tool."
    # )
    
    system_msg = SystemMessage(
        content=f"You are a tool call agent. Call '{tool_name}' using the given biodata."
    )
    
    # Pass biodata explicitly as JSON to match the tool's input schema
    human_msg = HumanMessage(
        content=f"Fetch the {platform} profile for biodata: {json.dumps(state['biodata'])}"
    )
    
    # Force the model to execute the specific registered tool
    if tool_name in LOADED_TOOLS_REGISTRY:
        model_to_use = model.bind_tools(
            [LOADED_TOOLS_REGISTRY[tool_name]], 
            tool_choice=tool_name
        )
    else:
        model_to_use = model_with_tools
        
    response = model_to_use.invoke([system_msg, human_msg])
    return {"messages": [response]}
    
    # print(f"State[messages]: {state['messages']}")
    # response = model_with_tools.invoke([system_msg] + state['messages'])
    # print(f"Profile agent response: {response}")
    # return {"messages": [response]}
            
    
    
class RankAgentOutput(BaseModel):
    url: str = Field(default="", description="The profile url of the highest-ranked-user.")

def rank_agent_node(state: AgentState):
    system_msg = SystemMessage(content=(
        "Act as social media profile ranker. You will be given a list of profile urls, rank them according to the relevance with the biodata of the given person. \nRank them from highest match to lowest match.\n"
        "Respond only with the given profile object having profiles ranked as per closeness to the biodata object. Response should be a JSON object\n"
        "Make sure the schema of the output JSON is the same as that of the input JSON. Just ranked as per the criteria.\n"
        "If Profiles are not provided in the user's prompt, they "
    ))
    
    # human_msg = HumanMessage(content=(
    #            f"Biodata: {json.dumps(state["biodata"], indent=4)}\nProfiles: {json.dumps(state['profiles'], indent=4)}"))
    
    human_msg = HumanMessage(content=(
        "Use the below mentioned biodata to rank the profiles given by the profile agent.\n"
        f"Biodata(separated by triple backticks): ```{json.dumps(state["biodata"], indent=4)}```"
    ))
    
    message_to_pass = state.get("messages", []) + [system_msg, human_msg]
    
    structured_model = model.with_structured_output(RankAgentOutput)
    response = cast(RankAgentOutput, structured_model.invoke(message_to_pass))
    # print(f"Rank Agent Response: {response}")
    
    ai_msg = AIMessage(content=response.model_dump_json())
    return {'messages': [system_msg, human_msg, ai_msg], "top_user_profile_url": response.url}

def linkedin_profile_agent(state: AgentState):
    full_name = state['full_name'].lower()
    full_name = full_name.split(" ")
    
    # print(f"\nSearching for LinkedIn profile data in cache...")
    # with open(f'./{full_name[0]}-{full_name[1]}-linkedin.json', 'r', encoding='utf-8') as file:
    #     if file:
    #         print(f'Profile Data found in cache...', 'Updating Agent State...', sep="\n")
    #         linkedin_object = json.load(file)
    #         file.close()
            
    #         return Command(
    #             update={
    #                 'linkedin_json': linkedin_object,
    #                 'messages': [
    #                     AIMessage(content="LinkedIn profile data found in cache...")
    #                 ]
    #             }
    #         )
    #     else:
    # print("\nLinkedIn JSON not found in cache.", "Fetching it from the web", sep="\n")
    
    system_msg = SystemMessage(
        content="Call the 'apify_scraper' tool to fetch the LinkedIn profile data for the target URL."
    )
    human_msg = HumanMessage(
        content=f"Fetch the LinkedIn profile of the user from the url given below\n.\
            url(separated by triple backticks): \n\
            ```{state['top_user_profile_url']}```"
    )
    
    # final_prompt = state['messages'] + [system_msg, human_msg]
    # response = model_with_tools.invoke(final_prompt)
    
    model_with_apify = model.bind_tools([apify_scraper], tool_choice="apify_scraper")
    response = model_with_apify.invoke([system_msg, human_msg])
    
    return {"messages": [system_msg, human_msg, response]}

    
    
class ValidationAgentOutput(BaseModel):
    score: int = Field(default=-1, description="The closeness/match score that determines how close of a match is the given biodata and the retrieved linkedin profile. Value of the score is between 0 and 1 both values included (i.e. continuous range of [0, 1])")
    summary: str = Field(default="", description="A Summary of the user's linkedin profile based on the 'linkedin_json' JSON object fetched from the apify api.")
    

def validation_agent_node(state: AgentState):
    # model = ChatGoogleGenerativeAI(model='gemini-2.5-flash')
    platform = state.get('platform_name', '').strip().lower()
    
    retrieved_profile_data = state.get("linkedin_json")
    if not retrieved_profile_data:
        for msg in reversed(state.get("messages", [])):
            if isinstance(msg, ToolMessage):
                retrieved_profile_data = msg.content
                break

    human_msg = HumanMessage(
        content=f"""Compare the given biodata of the person with their retrieved {platform} profile data and determine if the data represents the same person.\n

        Biodata (separated by triple backticks):\n
        ```{json.dumps(state.get('biodata', {}), indent=2)}```
        """
    )
    
    system_msg = SystemMessage(
        content=(
            f"Act as an expert profile judge. Compare the target person's biodata with "
            f"their retrieved {platform} profile data to determine if they belong to the same person.\n"
            f"Assign a similarity score between 0 and 1, provide a single-sentence verdict, "
            f"and write a short summary based strictly on the retrieved profile data."
        )
    )

    messages_to_pass = state.get("messages", []) + [system_msg, human_msg]
    
    structured_model = model.with_structured_output(ValidationAgentOutput)
    response = cast(ValidationAgentOutput, structured_model.invoke(messages_to_pass))
    
    # print(f"Validation Agent response: \n{response}")
    ai_msg = AIMessage(
        content=response.model_dump_json()
    )
    return {"messages": [system_msg, human_msg, ai_msg]}
    
def route_after_tools(state: AgentState) -> str:
    linkedin_data = state.get('linkedin_json')
    platform = state.get('platform_name', "").lower().strip()
    
    if linkedin_data and len(linkedin_data) > 0:
        return 'validation_agent'
    
    if platform == 'linkedin':
        return 'rank_agent'
    else:
        return'validation_agent'

def route_after_rank(state: AgentState) -> str:
    platform = state.get("platform_name", "").lower().strip()
    
    # Explicitly route to linkedin_agent only when handling LinkedIn
    if platform == "linkedin":
        return "linkedin_agent"
    
    # Otherwise, pass back to dynamic tools node
    return "tools"

def form_data_extractor(state: AgentState):
    
    system_prompt = SystemMessage(
        content="""You are an extraction assistant. Analyze the provided LinkedIn profile JSON and extract the candidate's details into the structured form schema.

        Global Rules:
        - Convert all date strings to MM/YYYY format where applicable.
        - If data for an optional field is absent in the source JSON, leave it as null/None.
        """
    )
    
    user_prompt = HumanMessage(content=f"""
        Extract the details from the profile JSON mentioned below
        
        User's LinkedIn JSON(separated by triple backticks):
        ```
        {state["linkedin_json"]}
        ```
        """
    )
    
    full_prompt = state['messages'] + [system_prompt, user_prompt]
    
    structured_model = model.with_structured_output(LinkedInProfile)
    response = cast(LinkedInProfile, structured_model.invoke(full_prompt))
    
    
    # print(f"Extraction model response: {response}")
    
    return {"final_data": response.model_dump()}

def tool_resolver(state: AgentState):
    platform = state['platform_name']
    tool_path = find_existing_tool(platform_name=platform)
    global model_with_tools, LOADED_TOOLS_REGISTRY
    
    if not tool_path:
        print(f"[Tool Resolver] Tool for '{platform}' not found in ./tools/!")
        user_approval = input("Do you want to call the coding-agent to build it? (y/n): ").lower()
        
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "--dev", 
            action='store_true', 
            default=False, 
            help="Enable dev mode and call the coding agent to build dynamic tools."
        )
        
        args = parser.parse_args()
        
        
        if user_approval == 'y' and args.dev:
            print("MAS API call not yet implemented")
            os._exit(1)
        else:
            print("\nExiting workflow as the required tool does not exist & dev mode is not enabled...")
            os._exit(1)
    else:
        print(f"Tool found at: {tool_path}")
        dynamic_tool = create_langchain_tool_adapter(file_path=tool_path, platform_name=platform)
        
        # Register in dynamic dictionary and re-bind model
        LOADED_TOOLS_REGISTRY[dynamic_tool.name] = dynamic_tool
        model_with_tools = model.bind_tools(list(LOADED_TOOLS_REGISTRY.values()))
        print(f"Tool '{dynamic_tool.name}' attached successfully!")

def dynamic_tool_node(state: AgentState):
    """Custom Tool Node that dynamically executes registered tools."""
    last_message = state["messages"][-1]
    

    if isinstance(last_message, AIMessage):
        if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
            return {}
        tool_call = last_message.tool_calls[0]
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        tool_call_id = tool_call["id"]

        if tool_name not in LOADED_TOOLS_REGISTRY:
            raise KeyError(f"Tool '{tool_name}' is not registered in LOADED_TOOLS_REGISTRY.")

        target_tool = LOADED_TOOLS_REGISTRY[tool_name]
        
        # Execute tool (handles both standard tools and Command return tools)
        tool_result = target_tool.invoke({
            "state": state,
            "tool_call_id": tool_call_id,
            **tool_args
        })

        # If tool returns a LangGraph Command object, return it directly
        if isinstance(tool_result, Command):
            return tool_result
            
        return {
            "messages": [
                ToolMessage(content=str(tool_result), tool_call_id=tool_call_id)
            ]
        }
    else:
        print(f"\nLast message is not an AI message and thus does not contain a tool call.")
    
    

# tool_node = ToolNode(tools=[fetch_linkedin_profile_urls, apify_scraper] + dynamically_attached_tools)

workflow = StateGraph(AgentState)
workflow.add_node("biodata_agent", biodata_extractor)
workflow.add_node('tool_resolver', tool_resolver)
workflow.add_node("profile_agent", profile_agent_node)
workflow.add_node("rank_agent", rank_agent_node)
workflow.add_node('tools', dynamic_tool_node)
workflow.add_node('validation_agent', validation_agent_node)
workflow.add_node('linkedin_agent', linkedin_profile_agent)
workflow.add_node('extraction_agent', form_data_extractor)

workflow.add_edge(START, 'biodata_agent')
workflow.add_edge('biodata_agent', 'tool_resolver')
workflow.add_edge('tool_resolver', 'profile_agent')
workflow.add_edge('profile_agent', 'tools')
# workflow.add_edge('rank_agent', 'linkedin_agent')
workflow.add_conditional_edges(
    "tools", route_after_tools, 
    {
        "rank_agent": "rank_agent",
        "validation_agent": "validation_agent",
    }
)
workflow.add_conditional_edges('rank_agent', route_after_rank, {
    "linkedin_agent": 'linkedin_agent',
    "tools": 'tools'
})

workflow.add_edge('linkedin_agent', 'tools')
workflow.add_edge('validation_agent', 'extraction_agent')
workflow.add_edge('extraction_agent', END)

# starting_user_data = {
#     "first_name": "Tanmay",
#     "last_name": "gadge",
#     "employer": "IKSC Knowledge Bridge",
#     "role": [],
#     "education": ["Bachelor of Technology", "BTech.", "MIT-World Peace University"],
#     "hometown": "Pune",
#     "current_city": "Pune"
# }

relative_path = Path("../../biodata/images/rohan-patil-biodata.jpeg")
script_path = Path(__file__).parent
abs_path = (script_path / relative_path).resolve()

# rohan_biodata_json
# with open(Path(__file__).parent / "../json-files/Rohan-Patil.json")

initial_input: AgentState = {
    "initial_user_data": {},
    "biodata_image_url": str(abs_path),
    "full_name": "Rohan Patil",
    "profiles": [],
    "biodata": {},
    "linkedin_json": {},
    "top_user_profile_url": "",
    "platform_name": "Facebook",
    "final_data": {},
    "messages": [
        HumanMessage(
            content="Retrieve the Facebook profile data of the Given person."
        )
    ]
}

# memory = MemorySaver()

# app = workflow.compile(
    # checkpointer=memory,
    # interrupt_after=['rank_agent']
# )

# configuration: RunnableConfig = {
#     "configurable": {"thread_id": "thread_1"}
# }


# response = app.invoke(initial_input, config=configuration)
# stream = app.stream_events(initial_input, version="v3")

# for message in stream.messages:
#     print(f"[{message.node}] ", end="")
#     for delta in message.text:
#         print(delta, end="", flush=True)


# print("--------Execution paused for human approval---------\n")

# state = app.get_state(configuration)
# print(f"State.next: {state.next}\n")

# print(f"\nRetrieved user profiles: {state.values['profiles']}")
# print(f"Last message in Agent State: {state.values['messages'][-1]}")
# print(f"Top user profile url: {state.values['top_user_profile_url']}")
# print(f"linkedin_json size: {len(list(state.values['linkedin_json'].keys()))}")
    

# user_approval = input("Do you approve the results? (y/n): ").lower()

# if user_approval == 'y':
#     print("Resuming Execution...")
#     response = app.invoke(None, config=configuration)
#     state = app.get_state(configuration)
#     print(f"Last Message in agent state: {response['messages'][-1]}")
    
#     full_name = state.values['full_name'].lower()
#     full_name = full_name.split(" ")
    
#     final_data = state.values['final_data']
#     print(f"Final_data keys: {list(final_data.keys())[:20]}")
    
#     with open(f'../json-files/{full_name[0]}-{full_name[1]}-formatted-linkedin-test.json', 'w', encoding='utf-8') as file:
#         json.dump(final_data, file, indent=4)
#         print(f"Final Data written successfully in ../json-files/{full_name[0]}-{full_name[1]}-formatted-linkedin.json")
#     file.close()
    
# else:
#     os._exit(1)
    
    
# saver_client = MongoClient(os.getenv("MONGODB_CONNECTION_STRING"))

# 2. Compile without interrupts
checkpointer = MongoDBSaver(client, db_name="osint_agent_logs", collection_name="checkpoints")
app = workflow.compile(
    checkpointer=checkpointer,
    interrupt_after=['biodata_agent']       
)

agent_run_id = uuid7()

configuration: RunnableConfig = {
    "configurable": {"thread_id": agent_run_id}
}



print("Starting Agent Execution Pipeline...\n", flush=True)
# async def run_agent():
#     async with await app.astream_events(initial_input, config=configuration, version="v3") as stream:
#         async for message in stream.messages:
#             node_name = getattr(message, "node", "agent")
            
#             text_chunk = str(message.text)      
#             print(f"[{node_name}] {text_chunk}", end="", flush=True)      

# async def resume_agent(configuration):
#     async with await app.astream_events(None, config=configuration, version="v3") as stream:
#         async for message in stream.messages:
#             node_name = getattr(message, "node", "agent")
            
#             text_chunk = str(message.text)
#             print(f"[{node_name}] {text_chunk}", end="", flush=True)
            

stream = app.stream_events(
    initial_input, 
    config=configuration, 
    version='v3'
)          

with app.stream_events(initial_input, config=configuration, version="v3") as stream:
    for message in stream.messages:
        node_name = getattr(message, "node", "agent")
        print(f"[{node_name}] ", end="", flush=True)
        for delta in message.text:
            print(delta, end="", flush=True)


# initial_output = run_agent()
snapshot = app.get_state(config=configuration)
biodata_json = dict(snapshot.values['biodata'])


print(f"Execution paused for human approval...", flush=True)
print(f"\nBiodata JSON extracted from the biodata image:\n{json.dumps(biodata_json, indent=4)}\n", flush=True)

approval = input("Do you approve the results? (y/n): ").lower()

if approval == 'y':
    # final_output = resume_agent(configuration)
    with app.stream_events(None, config=configuration, version="v3") as stream:
        for message in stream.messages:
            node_name = getattr(message, "node", "agent")
            print(f"[{node_name} ]", end="", flush=True)
            for delta in message.text:
                print(delta, end="", flush=True)
        
else:
    print(f"\nExiting workflow execution...")
    os._exit(1)

# for event in stream:
#     if event['event'] == 'on_chat_model_stream':
#         print(event['data']['chunk'].content, end="",)

# for message in stream.messages:
#     node_name = getattr(message, "node", "agent")
#     print(f"[{node_name}] ", end="")
    
#     if isinstance(message, ToolMessage):
#         print(f"Tool Output:\n{message.content}", flush=True)
#     elif isinstance(message, AIMessage):
#         for delta in message.text:
#             print(delta, flush=True, end="")
#     elif hasattr(message, 'content'):
#         print(message.content, flush=True)
    

print("\n\nExecution Complete!")



"""
— Maybe add another agent that re-structures the task according to the data required for this workflow
— Look into recursive self-improvement for AI agents
"""
