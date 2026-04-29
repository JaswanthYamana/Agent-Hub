"""
integrations/ – Framework adapter modules for the Flight Recorder SDK.

Available adapters:
  - langchain_adapter  : LangChain BaseCallbackHandler
  - crewai_adapter     : CrewAI Task / Agent lifecycle hooks
  - autogen_adapter    : AutoGen ConversableAgent middleware

Import example:
    from integrations.langchain_adapter import FlightRecorderCallbackHandler
    from integrations.crewai_adapter    import FlightRecorderCrewAIAdapter
    from integrations.autogen_adapter   import FlightRecorderAutoGenMiddleware
"""
