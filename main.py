from pyferox import API, Field, Serializer


class CreateUserIn(Serializer):
    name: str
    age: int = Field(required=False, default=18)


class CreateUserOut(Serializer):
    id: int
    name: str
    age: int


app = API(prefix="api")


@app.post("users", input_schema=CreateUserIn, output_schema=CreateUserOut)
async def create_user(request):
    payload = request.data
    return {"id": 1, **payload}


if __name__ == "__main__":
    print("PyFerOx Django-first example loaded.")
    print("Use `include(app.urls)` inside Django urlpatterns.")
