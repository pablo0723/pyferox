from pyferox import API, HTTPError, Schema
from pyferox.response import JSONResponse


class CreateUserIn(Schema):
    name: str
    age: int


class CreateUserOut(Schema):
    id: int
    name: str
    age: int


app = API()


@app.post("/users", input_schema=CreateUserIn, output_schema=CreateUserOut)
async def create_user(request):
    payload = request.json_body
    if payload["age"] < 0:
        raise HTTPError(422, "age must be >= 0")
    return {"id": 1, **payload}


@app.get("/users/{user_id}")
def get_user(request):
    user_id = request.path_params.get("user_id")
    if user_id != "1":
        raise HTTPError(404, "user not found")
    return JSONResponse({"id": 1, "name": "Ada", "age": 33})


if __name__ == "__main__":
    print("PyFerOx MVP app is ready.")
    print("Use an ASGI server to run: uvicorn main:app")
