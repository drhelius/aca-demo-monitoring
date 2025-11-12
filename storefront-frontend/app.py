from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from opentelemetry import trace, metrics
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from azure.monitor.opentelemetry import configure_azure_monitor
import httpx
import os
import logging
from typing import List

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get Application Insights connection string from environment
connection_string = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")

# Get Orders API URL from environment
ORDERS_API_URL = os.getenv("ORDERS_API_URL", "http://localhost:8001")

# Instrument HTTPX before configuring Azure Monitor
HTTPXClientInstrumentor().instrument()

# Configure Azure Monitor (traces, metrics, and logs)
if connection_string:
    configure_azure_monitor(
        connection_string=connection_string,
        resource_attributes={
            "service.name": "storefront-frontend",
            "service.version": "1.0.0",
            "service.instance.id": os.getenv("HOSTNAME", "localhost"),
        },
        enable_live_metrics=True,
    )
    logger.info("Azure Monitor configured (traces, metrics, and logs)")
else:
    logger.warning("APPLICATIONINSIGHTS_CONNECTION_STRING not set, telemetry will not be exported")

# Create FastAPI app
app = FastAPI(title="Storefront Frontend", version="1.0.0")

# Instrument FastAPI with OpenTelemetry
FastAPIInstrumentor.instrument_app(app)

# Get tracer and meter
tracer = trace.get_tracer(__name__)
meter = metrics.get_meter(__name__)

# Create custom metrics
page_view_counter = meter.create_counter(
    "frontend.page_views",
    description="Number of page views",
)

order_request_counter = meter.create_counter(
    "frontend.order_requests",
    description="Number of order requests from frontend",
)

# Setup templates
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Home page"""
    with tracer.start_as_current_span("render_home_page") as span:
        page_view_counter.add(1, {"page": "home"})
        logger.info("Home page accessed")
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "orders_api_url": ORDERS_API_URL},
        )


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy", "service": "storefront-frontend"}


@app.get("/api/orders")
async def get_orders():
    """Get all orders from Orders API"""
    with tracer.start_as_current_span("fetch_all_orders") as span:
        try:
            logger.info(f"Fetching orders from {ORDERS_API_URL}/api/orders")
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{ORDERS_API_URL}/api/orders", timeout=10.0)
                
                if response.status_code != 200:
                    logger.error(f"Failed to fetch orders: {response.status_code}")
                    span.set_attribute("orders.fetch_success", False)
                    try:
                        error_detail = response.json().get("detail", response.text)
                    except:
                        error_detail = response.text or f"HTTP {response.status_code}"
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Orders API error: {error_detail}",
                    )
                
                try:
                    orders_data = response.json()
                except Exception as json_err:
                    logger.error(f"Failed to parse orders response as JSON: {json_err}. Response: {response.text[:200]}")
                    span.set_attribute("orders.error", "invalid_json_response")
                    raise HTTPException(
                        status_code=502,
                        detail=f"Invalid response from orders service. Response: {response.text[:100]}",
                    )
                span.set_attribute("orders.fetch_success", True)
                span.set_attribute("orders.count", orders_data.get("total", 0))
                logger.info(f"Fetched {orders_data.get('total', 0)} orders")
                return orders_data
                
        except httpx.RequestError as e:
            error_msg = f"Network error communicating with orders service at {ORDERS_API_URL}: {type(e).__name__}: {str(e)}"
            logger.error(error_msg)
            span.set_attribute("orders.error", str(e))
            span.set_attribute("orders.error_type", type(e).__name__)
            raise HTTPException(
                status_code=503,
                detail=error_msg,
            )
        except HTTPException:
            raise
        except Exception as e:
            error_msg = f"Unexpected error fetching orders: {type(e).__name__}: {str(e)}"
            logger.error(error_msg)
            span.set_attribute("orders.error", str(e))
            raise HTTPException(
                status_code=500,
                detail=error_msg,
            )


@app.get("/api/orders/{order_id}")
async def get_order(order_id: int):
    """Get a specific order from Orders API"""
    with tracer.start_as_current_span("fetch_order_by_id") as span:
        span.set_attribute("orders.order_id", order_id)
        
        try:
            logger.info(f"Fetching order {order_id} from {ORDERS_API_URL}/api/orders/{order_id}")
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{ORDERS_API_URL}/api/orders/{order_id}", timeout=10.0)
                
                if response.status_code == 404:
                    logger.warning(f"Order {order_id} not found")
                    span.set_attribute("orders.found", False)
                    raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
                
                if response.status_code != 200:
                    logger.error(f"Failed to fetch order {order_id}: {response.status_code}")
                    span.set_attribute("orders.fetch_success", False)
                    raise HTTPException(
                        status_code=response.status_code,
                        detail="Failed to fetch order from Orders API",
                    )
                
                order_data = response.json()
                span.set_attribute("orders.found", True)
                span.set_attribute("orders.fetch_success", True)
                logger.info(f"Fetched order {order_id}")
                return order_data
                
        except httpx.RequestError as e:
            error_msg = f"Network error communicating with orders service at {ORDERS_API_URL}: {type(e).__name__}: {str(e)}"
            logger.error(error_msg)
            span.set_attribute("orders.error", str(e))
            span.set_attribute("orders.error_type", type(e).__name__)
            raise HTTPException(
                status_code=503,
                detail=error_msg,
            )
        except HTTPException:
            raise
        except Exception as e:
            error_msg = f"Unexpected error fetching order {order_id}: {type(e).__name__}: {str(e)}"
            logger.error(error_msg)
            span.set_attribute("orders.error", str(e))
            raise HTTPException(
                status_code=500,
                detail=error_msg,
            )


@app.post("/api/orders")
async def create_order(order_data: dict):
    """Create a new order via Orders API"""
    with tracer.start_as_current_span("create_order_request") as span:
        order_request_counter.add(1, {"customer_id": order_data.get("customer_id", "unknown")})
        span.set_attribute("orders.customer_id", order_data.get("customer_id", "unknown"))
        span.set_attribute("orders.item_count", len(order_data.get("items", [])))
        
        try:
            logger.info(f"Creating order for customer {order_data.get('customer_id')}")
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{ORDERS_API_URL}/api/orders",
                    json=order_data,
                    timeout=30.0,
                )
                
                if response.status_code != 200:
                    try:
                        error_detail = response.json().get("detail", response.text)
                    except:
                        error_detail = response.text or f"HTTP {response.status_code}"
                    logger.error(f"Failed to create order: {error_detail}")
                    span.set_attribute("orders.create_success", False)
                    span.set_attribute("orders.error", error_detail)
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=error_detail,
                    )
                
                try:
                    order_result = response.json()
                except Exception as json_err:
                    logger.error(f"Failed to parse order creation response as JSON: {json_err}. Response: {response.text[:200]}")
                    span.set_attribute("orders.error", "invalid_json_response")
                    raise HTTPException(
                        status_code=502,
                        detail=f"Invalid response from orders service. Response: {response.text[:100]}",
                    )
                span.set_attribute("orders.create_success", True)
                span.set_attribute("orders.order_id", order_result.get("order_id"))
                span.set_attribute("orders.total_value", order_result.get("total_value", 0))
                logger.info(f"Order created successfully: {order_result.get('order_id')}")
                return order_result
                
        except httpx.RequestError as e:
            error_msg = f"Network error communicating with orders service at {ORDERS_API_URL}: {type(e).__name__}: {str(e)}"
            logger.error(error_msg)
            span.set_attribute("orders.error", str(e))
            span.set_attribute("orders.error_type", type(e).__name__)
            raise HTTPException(
                status_code=503,
                detail=error_msg,
            )
        except HTTPException:
            raise
        except Exception as e:
            error_msg = f"Unexpected error creating order: {type(e).__name__}: {str(e)}"
            logger.error(error_msg)
            span.set_attribute("orders.error", str(e))
            raise HTTPException(
                status_code=500,
                detail=error_msg,
            )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
