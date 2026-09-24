from fastapi import FastAPI
from database import engine, SessionLocal
from models import Base, Product
from routers import products, orders, refunds

app = FastAPI(title="E-commerce API (System A - MVC)", version="2.0.0")

app.include_router(products.router)
app.include_router(orders.router)
app.include_router(refunds.router)


@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)


@app.get("/")
def root():
    """Health check"""
    return {"status": "ok", "system": "A", "architecture": "MVC"}
