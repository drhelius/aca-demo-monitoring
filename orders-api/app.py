from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from azure.monitor.opentelemetry.exporter import (
    AzureMonitorTraceExporter,
    AzureMonitorMetricExporter,
)
import httpx
import os
import logging
from typing import List, Optional
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get Application Insights connection string from environment
connection_string = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")

# Get Inventory API URL from environment
INVENTORY_API_URL = os.getenv("INVENTORY_API_URL", "http://localhost:8000")

# Configure OpenTelemetry resource
resource = Resource.create(
    {
        "service.name": "orders-api",
        "service.version": "1.0.0",
        "service.instance.id": os.getenv("HOSTNAME", "localhost"),
    }
)

# Configure tracing
if connection_string:
    trace_provider = TracerProvider(resource=resource)
    trace_exporter = AzureMonitorTraceExporter(connection_string=connection_string)
    trace_provider.add_span_processor(BatchSpanProcessor(trace_exporter))
    trace.set_tracer_provider(trace_provider)
    logger.info("Azure Monitor tracing configured")
else:
    logger.warning("APPLICATIONINSIGHTS_CONNECTION_STRING not set, traces will not be exported")

# Configure metrics
if connection_string:
    metric_reader = PeriodicExportingMetricReader(
        AzureMonitorMetricExporter(connection_string=connection_string)
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)
    logger.info("Azure Monitor metrics configured")
else:
    logger.warning("APPLICATIONINSIGHTS_CONNECTION_STRING not set, metrics will not be exported")

# Create FastAPI app
app = FastAPI(title="Orders API", version="1.0.0")

# Instrument FastAPI with OpenTelemetry
FastAPIInstrumentor.instrument_app(app)
HTTPXClientInstrumentor().instrument()

# Get tracer and meter
tracer = trace.get_tracer(__name__)
meter = metrics.get_meter(__name__)

# Create custom metrics
order_counter = meter.create_counter(
    "orders.created",
    description="Number of orders created",
)

order_value_histogram = meter.create_histogram(
    "orders.value",
    description="Order values",
    unit="USD",
)

# Pydantic models
class OrderItem(BaseModel):
    product_id: str
    quantity: int


class CreateOrderRequest(BaseModel):
    customer_id: str
    items: List[OrderItem]


# In-memory order storage
orders_db = {}
order_id_counter = 1000


@app.get("/")
async def root():
    """Root endpoint with service information"""
    return {
        "service": "Orders API",
        "version": "1.0.0",
        "status": "running",
        "endpoints": ["/health", "/api/orders", "/api/orders/{order_id}"],
        "inventory_api": INVENTORY_API_URL,
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy", "service": "orders-api"}


@app.get("/api/orders")
async def get_all_orders():
    """Get all orders"""
    with tracer.start_as_current_span("get_all_orders") as span:
        span.set_attribute("orders.count", len(orders_db))
        logger.info(f"Retrieved all orders: {len(orders_db)} orders")
        return {"orders": list(orders_db.values()), "total": len(orders_db)}


@app.get("/api/orders/{order_id}")
async def get_order(order_id: int):
    """Get a specific order by ID"""
    with tracer.start_as_current_span("get_order_by_id") as span:
        span.set_attribute("orders.order_id", order_id)
        
        if order_id not in orders_db:
            logger.warning(f"Order not found: {order_id}")
            span.set_attribute("orders.found", False)
            raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
        
        span.set_attribute("orders.found", True)
        order = orders_db[order_id]
        logger.info(f"Retrieved order: {order_id}")
        return order


@app.post("/api/orders")
async def create_order(order_request: CreateOrderRequest):
    """Create a new order"""
    global order_id_counter
    
    with tracer.start_as_current_span("create_order") as span:
        span.set_attribute("orders.customer_id", order_request.customer_id)
        span.set_attribute("orders.item_count", len(order_request.items))
        
        order_id = order_id_counter
        order_id_counter += 1
        
        # Validate and reserve inventory for each item
        order_items = []
        total_value = 0.0
        
        async with httpx.AsyncClient() as client:
            for item in order_request.items:
                with tracer.start_as_current_span("check_inventory") as inv_span:
                    inv_span.set_attribute("inventory.product_id", item.product_id)
                    inv_span.set_attribute("inventory.quantity", item.quantity)
                    
                    try:
                        # Check inventory availability
                        logger.info(f"Checking inventory for {item.product_id}")
                        inv_response = await client.get(
                            f"{INVENTORY_API_URL}/api/inventory/{item.product_id}"
                        )
                        
                        if inv_response.status_code != 200:
                            logger.error(f"Product not found in inventory: {item.product_id}")
                            inv_span.set_attribute("inventory.check_success", False)
                            raise HTTPException(
                                status_code=404,
                                detail=f"Product {item.product_id} not found in inventory",
                            )
                        
                        inventory_data = inv_response.json()
                        inv_span.set_attribute("inventory.available_stock", inventory_data["stock"])
                        
                        if inventory_data["stock"] < item.quantity:
                            logger.warning(f"Insufficient stock for {item.product_id}")
                            inv_span.set_attribute("inventory.check_success", False)
                            raise HTTPException(
                                status_code=400,
                                detail=f"Insufficient stock for {item.product_id}. Available: {inventory_data['stock']}, Requested: {item.quantity}",
                            )
                        
                        # Reserve inventory
                        logger.info(f"Reserving {item.quantity} units of {item.product_id}")
                        reserve_response = await client.post(
                            f"{INVENTORY_API_URL}/api/inventory/{item.product_id}/reserve",
                            params={"quantity": item.quantity},
                        )
                        
                        if reserve_response.status_code != 200:
                            logger.error(f"Failed to reserve inventory for {item.product_id}")
                            inv_span.set_attribute("inventory.reservation_success", False)
                            raise HTTPException(
                                status_code=500,
                                detail=f"Failed to reserve inventory for {item.product_id}",
                            )
                        
                        inv_span.set_attribute("inventory.check_success", True)
                        inv_span.set_attribute("inventory.reservation_success", True)
                        
                        item_total = inventory_data["price"] * item.quantity
                        total_value += item_total
                        
                        order_items.append({
                            "product_id": item.product_id,
                            "product_name": inventory_data["name"],
                            "quantity": item.quantity,
                            "unit_price": inventory_data["price"],
                            "total": item_total,
                        })
                        
                    except httpx.RequestError as e:
                        logger.error(f"Error communicating with inventory service: {e}")
                        inv_span.set_attribute("inventory.error", str(e))
                        raise HTTPException(
                            status_code=503,
                            detail=f"Unable to reach inventory service: {str(e)}",
                        )
        
        # Create order
        order = {
            "order_id": order_id,
            "customer_id": order_request.customer_id,
            "items": order_items,
            "total_value": total_value,
            "status": "confirmed",
            "created_at": datetime.utcnow().isoformat(),
        }
        
        orders_db[order_id] = order
        
        # Record metrics
        order_counter.add(1, {"customer_id": order_request.customer_id})
        order_value_histogram.record(total_value, {"customer_id": order_request.customer_id})
        
        span.set_attribute("orders.order_id", order_id)
        span.set_attribute("orders.total_value", total_value)
        span.set_attribute("orders.status", "confirmed")
        
        logger.info(f"Order created successfully: {order_id} with total value ${total_value:.2f}")
        return order


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
