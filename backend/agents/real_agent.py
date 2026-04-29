"""
real_agent.py - A real LangChain ReAct agent demonstrating AgentScope telemetry.

This agent uses actual OpenAI LLM calls and LangChain tools to perform a
simulated flight booking workflow. Because it is instrumented with the 
FlightRecorderCallbackHandler, all of its reasoning steps and tool calls
will appear in the AgentScope dashboard alongside the simulated traces.

Usage:
    # 1. Start your local LLM server (e.g. LM Studio on port 1234)
    # 2. Configure backend/.env
    # 3. Run:
    python real_agent.py
"""

import os
import uuid
import time
import random
import json
from datetime import datetime
from typing import Dict, Any, List

from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage
from langgraph.prebuilt import create_react_agent
from core.models import TaskRequest, Trace

# Load the AgentScope SDKs and adapters
# Depending on where this is run from, setup path so it can import backend modules
import sys
from pathlib import Path
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

from sdk import Tracer
from integrations.langchain_adapter import FlightRecorderCallbackHandler

# ---------------------------------------------------------------------------
# Definining real Tools but with Mock implementations for the demonstration.
# In a true deployment these would hit live APIs.
# ---------------------------------------------------------------------------

@tool
def flight_search_api(origin: str, destination: str, date: str, passengers: int) -> str:
    """Search for available flights using the AviationStack real-time Flights API.
    
    Args:
        origin: IATA airport code (e.g. MAA for Chennai)
        destination: IATA airport code (e.g. DEL for Delhi)
        date: ISO-8601 date (YYYY-MM-DD)
        passengers: integer number of passengers
    """
    print(f"✈️  Searching flights for {passengers} pax from {origin} → {destination} on {date}...")
    api_key = os.environ.get("AVIATIONSTACK_API_KEY")
    if api_key:
        print("   [INFO] Hitting AviationStack real-time flights endpoint...")
        try:
            import requests
            # AviationStack free tier only supports HTTP (not HTTPS)
            # and does NOT allow flight_date (paid feature) — use live real-time data
            params = {
                "access_key": api_key,
                "dep_iata":   origin.upper(),
                "arr_iata":   destination.upper(),
                "limit": 5,
            }
            res = requests.get("http://api.aviationstack.com/v1/flights", params=params, timeout=12)
            res.raise_for_status()
            data = res.json()

            raw_flights = data.get("data", [])
            if raw_flights:
                flights = []
                seen = set()
                for f in raw_flights:
                    airline   = (f.get("airline") or {}).get("name", "Unknown")
                    iata_num  = (f.get("flight") or {}).get("iata", f"F{random.randint(100,999)}")
                    dep_time  = str((f.get("departure") or {}).get("scheduled", ""))[:16][-5:] or "TBD"  # type: ignore
                    # AviationStack free plan doesn't include price — simulate one per airline
                    price     = random.randint(3000, 12000)
                    flight_id = f"FL-{iata_num}"
                    if flight_id not in seen:
                        seen.add(flight_id)
                        flights.append({
                            "id": flight_id,
                            "airline": airline,
                            "flight_number": iata_num,
                            "price": price,
                            "departure": dep_time,
                            "origin": origin.upper(),
                            "destination": destination.upper(),
                        })
                print(f"   [INFO] AviationStack returned {len(flights)} flights.")
                return json.dumps(flights[:3])  # type: ignore
            else:
                print("   [INFO] AviationStack returned 0 flights for this route/date. Falling back to mock.")
        except Exception as e:
            print(f"   [ERROR] AviationStack call failed ({e}). Falling back to realistic mock...")
    else:
        print("   [WARN] AVIATIONSTACK_API_KEY missing. Falling back to realistic simulated data...")
        time.sleep(random.uniform(1.0, 2.5))

    # Realistic mock with India-relevant airlines and INR-range prices
    airlines = [
        ("IndiGo",          f"6E-{random.randint(100,999)}", random.randint(3200, 5000)),
        ("Air India",       f"AI-{random.randint(100,999)}", random.randint(4500, 7000)),
        ("SpiceJet",        f"SG-{random.randint(100,999)}", random.randint(3000, 4800)),
    ]
    flights = [
        {
            "id": f"FL-{fn}",
            "airline": name,
            "flight_number": fn,
            "price": price,
            "departure": f"{random.randint(5,22):02d}:{random.choice(['00','15','30','45'])}",
            "origin": origin.upper(),
            "destination": destination.upper(),
        }
        for name, fn, price in airlines
    ]
    return json.dumps(flights)

@tool
def price_comparison_tool(flights_json: str) -> str:
    """Compare prices across multiple flight options and identify the cheapest.
    
    Args:
        flights_json: A JSON format string containing the list of flight dictionaries returned by flight_search_api.
    """
    print(f"⚖️ Comparing prices for provided flights...")
    time.sleep(random.uniform(0.5, 1.5))
    try:
        flights = json.loads(flights_json)
        if not flights or not isinstance(flights, list):
             return '{"error": "No valid flight data provided. Please provide the JSON array from flight_search_api."}'
             
        # Find the flight with the minimum price
        cheapest = min(flights, key=lambda f: f.get("price", float('inf')))
        
        return json.dumps({
            "recommendation": cheapest,
            "reason": f"Evaluated as the most cost-effective option available at ${cheapest.get('price')}."
        })
    except Exception as e:
         return f'{{"error": "Failed to parse flights_json: {e}"}}'

@tool
def booking_api(flight_id: str, passenger_name: str, passenger_email: str, payment_token: str) -> str:
    """Book a selected flight for a passenger.
    
    Args:
        flight_id: unique flight identifier
        passenger_name: full name of primary passenger
        passenger_email: passenger contact email
        payment_token: tokenised payment method
    """
    print(f"🎫 Contacting reservation system to book {flight_id} for {passenger_name}...")
    
    # Simulate network latency and processing time typical of legacy airline systems (1.5s to 4s)
    time.sleep(random.uniform(1.5, 4.0))
    
    # Simulate basic validation
    if "@" not in passenger_email or "." not in passenger_email:
        return '{"status": "failed", "error": "Invalid email address format.", "code": 400}'
        
    booking_id = f"BK-{str(uuid.uuid4())[:6].upper()}"  # type: ignore
    pnr = "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=6))
    
    response = {
        "status": "confirmed",
        "data": {
            "booking_reference": booking_id,
            "pnr": pnr,
            "passenger": passenger_name,
            "flight_id": flight_id,
            "created_at": datetime.utcnow().isoformat() + "Z"
        },
        "meta": {"system": "Amadeus/Mockv2", "latency_ms": random.randint(1500, 4000)}
    }
    return json.dumps(response)

@tool
def payment_api(booking_id: str, amount: float, payment_method: str) -> str:
    """Process payment for a confirmed booking via Payment Gateway.
    
    Args:
        booking_id: booking reference string
        amount: amount in USD
        payment_method: 'card' or 'wallet'
    """
    print(f"💳 Handshaking with secure payment gateway for ${amount} on {booking_id}...")
    
    # Simulate payment processing delay (2s to 5s)
    time.sleep(random.uniform(2.0, 5.0))
    
    # Simulate occasional randomized gateway declines (approx 5% chance)
    if random.random() < 0.05:
        return '{"status": "declined", "error": "Issuer declined the transaction. Try another card.", "code": 402}'
        
    response = {
        "status": "success",
        "data": {
            "transaction_id": f"TXN-{random.randint(100000, 999999)}",
            "auth_code": "".join(random.choices("0123456789", k=6)),
            "amount_processed": amount,
            "currency": "USD",
            "method": payment_method
        },
        "meta": {"gateway": "Stripe/Mockv2", "risk_score": round(float(random.uniform(0.01, 0.1)), 3)}
    }
    return json.dumps(response)

@tool
def email_api(to: str, subject: str, body: str) -> str:
    """Send an email to a recipient using a REAL SMTP server.
    
    Args:
        to: recipient email address
        subject: email subject line
        body: email body (plain text or HTML)
    """
    print(f"📧 Sending confirmation email to {to}...")
    
    smtp_host = os.environ.get("SMTP_HOST")
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASS")
    
    if smtp_host and smtp_user and smtp_pass:
        print(f"   [INFO] Contacting actual SMTP server ({smtp_host})...")
        try:
            import smtplib
            from email.message import EmailMessage
            msg = EmailMessage()
            msg.set_content(body)
            msg['Subject'] = subject
            msg['From'] = smtp_user
            msg['To'] = to
            
            port = int(os.environ.get("SMTP_PORT", 587))
            with smtplib.SMTP(smtp_host, port) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
            return json.dumps({"status": "delivered", "method": "SMTP", "message_id": f"MSG-{uuid.uuid4().hex[:10]}"})  # type: ignore
        except Exception as e:
            print(f"   [ERROR] SMTP email failed ({e}). Falling back to logical dispatch mock...")
    else:
        print("   [WARN] SMTP credentials missing in .env. Falling back to logical dispatch mock...")
        time.sleep(random.uniform(1.0, 2.0))
        
    return json.dumps({
        "status": "delivered", 
        "method": "MOCK", 
        "message_id": f"MSG-{uuid.uuid4().hex[:10]}",  # type: ignore
        "mock_note": "No SMTP configured."
    })

# ---------------------------------------------------------------------------
# RealAgent class (supports async execute for red-team engine integration)
# ---------------------------------------------------------------------------

class RealAgent:
    """Real LangChain agent with async execute() for red-team engine integration."""

    async def execute(self, request: TaskRequest) -> Trace:
        load_dotenv()
        
        # Required for the OpenAI SDK, even if using a local server that ignores it
        api_key = os.environ.get("OPENAI_API_KEY", "local-key")
        api_base = os.environ.get("OPENAI_API_BASE")
        model_name = os.environ.get("MODEL_NAME", "gpt-4o-mini")

        # 1. Initialize tools
        tools = [
            flight_search_api,
            price_comparison_tool,
            booking_api,
            payment_api,
            email_api
        ]

        # 2. Setup the Tracer and Callback handler
        tracer = Tracer(
            service_name="langchain-react-agent",
            project_id=request.project_id,
            export_url="http://localhost:8000",
            api_key=api_key 
        )
        handler = FlightRecorderCallbackHandler(tracer, task=request.task, scenario=request.scenario)
        if request.trace_id:
            handler.trace.trace_id = request.trace_id

        # 3. Initialize LLM — use Ollama if configured, otherwise OpenAI
        provider = os.environ.get("LLM_PROVIDER", "ollama").lower()

        if provider == "ollama":
            from langchain_ollama import ChatOllama
            ollama_model = os.environ.get("OLLAMA_MODEL", "mistral")
            ollama_base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
            llm = ChatOllama(
                model=ollama_model,
                base_url=ollama_base_url,
                temperature=0,
                callbacks=[handler]
            )
        else:
            llm_kwargs = {
                "temperature": 0,
                "model": model_name,
                "api_key": api_key,
                "callbacks": [handler]
            }
            if api_base:
                llm_kwargs["base_url"] = api_base
            llm = ChatOpenAI(**llm_kwargs)

        # 4. Create Agent Setup
        system_prompt = SystemMessage(content="""You are a precise flight booking assistant. You MUST complete every step below IN ORDER using the tools provided. Do NOT skip any step or call a tool without having the output of the previous step.

Step 1 — SEARCH: Call `flight_search_api` with the origin, destination, date and passenger count extracted from the user request. This returns a JSON list of flights.
Step 2 — COMPARE: Call `price_comparison_tool` with the full JSON string returned by `flight_search_api` in Step 1. Use the exact output, not a truncated version. This returns the cheapest flight recommendation.
Step 3 — BOOK: Call `booking_api` with the `id` field from the recommendation returned in Step 2 as `flight_id`. Generate a plausible `payment_token` such as 'tok_visa_demo'.
Step 4 — PAY: Call `payment_api` with the `booking_reference` from Step 3, the price from Step 2, and a `payment_method` of 'card'.
Step 5 — EMAIL: Call `email_api` with the passenger email from the task, a confirmation subject, and a detailed body including the booking reference and PNR from Step 3.

Never produce a final answer before all 5 steps are completed successfully. If a step fails, report the error and stop.""")
        
        agent = create_react_agent(llm, tools=tools, prompt=system_prompt)

        # 5. Execute!
        print(f"🚀 Starting Real Agent execution for task: '{request.task}'")
        with handler.trace:
            try:
                result = await agent.ainvoke(
                    {"messages": [("user", request.task)]},
                    config={"callbacks": [handler]}
                )
                print("\n✅ Final Result:")
                final_msg = result["messages"][-1].content
                print(final_msg)
                handler.trace.final_summary = final_msg
                handler.trace.success = True
                handler.trace.completed = True
            except Exception as e:
                print(f"\n❌ Error during execution: {e}")
                handler.trace.success = False
                handler.trace.completed = False

        return handler.trace


# ---------------------------------------------------------------------------
# Standalone runner (CLI)
# ---------------------------------------------------------------------------

def run_real_agent_task(task: str, project_id: str = "real_agent_demo"):
    import asyncio
    agent = RealAgent()
    request = TaskRequest(task=task, project_id=project_id)
    trace = asyncio.run(agent.execute(request))
    
    # Explicit export to ensure spans are uploaded successfully.
    load_dotenv()
    api_key = os.environ.get("OPENAI_API_KEY", "local-key")
    tracer = Tracer(
        service_name="langchain-react-agent",
        project_id=project_id,
        export_url="http://localhost:8000",
        api_key=api_key 
    )
    tracer.export(trace)
    print(f"📊 Traces uploaded to AgentScope! View them at http://localhost:8000")


PASSENGER_NAME  = "Akhil"
PASSENGER_EMAIL = "venkataakhilkumar.7781@gmail.com"

if __name__ == "__main__":
    print("=" * 60)
    print("  ✈️  AgentScope — Real Flight Booking Agent")
    print("=" * 60)
    print(f"  Passenger : {PASSENGER_NAME}")
    print(f"  Email     : {PASSENGER_EMAIL}")
    print("-" * 60)
    print("Type your flight request below (e.g.  book a flight to")
    print("Delhi from Chennai for tomorrow) or press Enter to quit.")
    print("=" * 60)

    while True:
        user_input = input("\n🗣  Your request: ").strip()
        if not user_input:
            print("Goodbye! 👋")
            break

        # Enrich the raw user request with the passenger info so the
        # LLM always knows who to book for and where to send the email.
        task = (
            f"{user_input}. "
            f"Passenger name is {PASSENGER_NAME} and "
            f"passenger email is {PASSENGER_EMAIL}. "
            f"Return the booking ID and ensure you email them the confirmation."
        )

        run_real_agent_task(task, project_id="real_agent_demo")
