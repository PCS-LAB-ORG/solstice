from fastapi import FastAPI
from agent.main import load_state

app = FastAPI(title="Solstice Agent Status API")


@app.get("/status")
def status():
    state = load_state()
    return {
        "status": "ok",
        "last_run": state.get("last_run", ""),
        "account_count": len(state.get("accounts", {})),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8100)
