from fastapi import FastAPI

app = FastAPI("OriginCard Backend")

@app.get("/")
def read_root():
    return {"Message: Привіт! Бекенд OriginCard працює успішно!"}
