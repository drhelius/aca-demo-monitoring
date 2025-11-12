from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from opentelemetry import trace, metrics
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from azure.monitor.opentelemetry import configure_azure_monitor
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get Application Insights connection string from environment
connection_string = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")

# Instrument HTTPX before configuring Azure Monitor
HTTPXClientInstrumentor().instrument()

# Configure Azure Monitor (traces, metrics, and logs)
if connection_string:
    configure_azure_monitor(
        connection_string=connection_string,
        resource_attributes={
            "service.name": "inventory-api",
            "service.version": "1.0.0",
            "service.instance.id": os.getenv("HOSTNAME", "localhost"),
        },
        enable_live_metrics=True,
    )
    logger.info("Azure Monitor configured (traces, metrics, and logs)")
else:
    logger.warning("APPLICATIONINSIGHTS_CONNECTION_STRING not set, telemetry will not be exported")

# Create FastAPI app
app = FastAPI(title="Inventory API", version="1.0.0")

# Instrument FastAPI with OpenTelemetry
FastAPIInstrumentor.instrument_app(app)

# Get tracer and meter
tracer = trace.get_tracer(__name__)
meter = metrics.get_meter(__name__)

# Create custom metrics
inventory_check_counter = meter.create_counter(
    "inventory.checks",
    description="Number of inventory checks performed",
)

stock_level_gauge = meter.create_up_down_counter(
    "inventory.stock_level",
    description="Current stock levels",
)

# Sample inventory data
inventory = {
    "laptop": {"name": "Laptop Pro", "stock": 25, "price": 1299.99},
    "mouse": {"name": "Wireless Mouse", "stock": 150, "price": 29.99},
    "keyboard": {"name": "Mechanical Keyboard", "stock": 75, "price": 89.99},
    "monitor": {"name": "4K Monitor", "stock": 40, "price": 449.99},
    "headset": {"name": "Gaming Headset", "stock": 60, "price": 79.99},
}


@app.get("/")
async def root():
    """Root endpoint with service information"""
    return {
        "service": "Inventory API",
        "version": "1.0.0",
        "status": "running",
        "endpoints": ["/health", "/api/inventory", "/api/inventory/{product_id}"],
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy", "service": "inventory-api"}


@app.get("/api/inventory")
async def get_all_inventory():
    """Get all inventory items"""
    with tracer.start_as_current_span("get_all_inventory") as span:
        span.set_attribute("inventory.item_count", len(inventory))
        inventory_check_counter.add(1, {"operation": "list_all"})
        
        logger.info(f"Retrieved all inventory items: {len(inventory)} items")
        return {"items": inventory, "total_items": len(inventory)}


@app.get("/api/inventory/{product_id}")
async def get_inventory(product_id: str):
    """Get inventory for a specific product"""
    with tracer.start_as_current_span("get_inventory_by_product") as span:
        span.set_attribute("inventory.product_id", product_id)
        inventory_check_counter.add(1, {"operation": "get_by_id"})
        
        if product_id not in inventory:
            logger.warning(f"Product not found: {product_id}")
            span.set_attribute("inventory.found", False)
            raise HTTPException(status_code=404, detail=f"Product {product_id} not found")
        
        item = inventory[product_id]
        span.set_attribute("inventory.found", True)
        span.set_attribute("inventory.stock_level", item["stock"])
        span.set_attribute("inventory.product_name", item["name"])
        
        stock_level_gauge.add(item["stock"], {"product_id": product_id})
        
        logger.info(f"Retrieved inventory for {product_id}: {item['stock']} units")
        return {
            "product_id": product_id,
            "name": item["name"],
            "stock": item["stock"],
            "price": item["price"],
            "available": item["stock"] > 0,
        }


@app.post("/api/inventory/{product_id}/reserve")
async def reserve_inventory(product_id: str, quantity: int = 1):
    """Reserve inventory for a product"""
    with tracer.start_as_current_span("reserve_inventory") as span:
        span.set_attribute("inventory.product_id", product_id)
        span.set_attribute("inventory.quantity", quantity)
        
        if product_id not in inventory:
            logger.warning(f"Cannot reserve - product not found: {product_id}")
            span.set_attribute("inventory.reservation_success", False)
            raise HTTPException(status_code=404, detail=f"Product {product_id} not found")
        
        if inventory[product_id]["stock"] < quantity:
            logger.warning(f"Insufficient stock for {product_id}: requested {quantity}, available {inventory[product_id]['stock']}")
            span.set_attribute("inventory.reservation_success", False)
            span.set_attribute("inventory.reason", "insufficient_stock")
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient stock. Available: {inventory[product_id]['stock']}, Requested: {quantity}",
            )
        
        inventory[product_id]["stock"] -= quantity
        span.set_attribute("inventory.reservation_success", True)
        span.set_attribute("inventory.remaining_stock", inventory[product_id]["stock"])
        
        stock_level_gauge.add(-quantity, {"product_id": product_id})
        inventory_check_counter.add(1, {"operation": "reserve"})
        
        logger.info(f"Reserved {quantity} units of {product_id}. Remaining stock: {inventory[product_id]['stock']}")
        return {
            "success": True,
            "product_id": product_id,
            "reserved_quantity": quantity,
            "remaining_stock": inventory[product_id]["stock"],
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
