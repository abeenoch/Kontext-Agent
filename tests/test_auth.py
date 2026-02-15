import uuid


def test_auth_signup_and_login(client):
    email = f"auth_{uuid.uuid4().hex[:10]}@example.com"
    password = "testpass123"

    signup = client.post(
        "/auth/signup",
        json={"email": email, "password": password, "display_name": "Auth User"},
    )
    assert signup.status_code == 201, signup.text
    sdata = signup.json()
    assert sdata["user_id"] == email
    assert sdata["token_type"] == "bearer"

    login = client.post("/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    ldata = login.json()
    assert ldata["user_id"] == email
    assert "access_token" in ldata
