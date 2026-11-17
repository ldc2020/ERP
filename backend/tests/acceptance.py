"""Run against a fresh, disposable ERP instance with captcha disabled."""
import json
import os
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4


ROOT = os.environ.get("ERP_TEST_URL", "http://127.0.0.1:8080/api/system")


def call(path, body=None, token=None, status=200, form=False):
    headers = {}
    payload = None
    if body is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded" if form else "application/json"
        payload = (urlencode(body) if form else json.dumps(body)).encode()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(ROOT + path, data=payload, headers=headers)
    try:
        response = urlopen(request, timeout=10)
    except HTTPError as error:
        response = error
    with response:
        result = json.load(response)
        assert response.status == status, (path, response.status, result)
    if status == 200:
        assert result["code"] == 200, (path, result)
    return result.get("data")


def login(username, password):
    return call("/auth/login", {"username": username, "password": password}, form=True)


def main():
    admin = login(os.environ.get("ADMIN_USERNAME", "admin"), os.environ["ADMIN_PASSWORD"])["access_token"]
    username = "erp-test-" + uuid4().hex[:10]
    password = uuid4().hex
    role = call("/role/create", {"name": "验收角色-" + username}, admin)
    employee = call("/user/create", {
        "username": username, "name": "验收员工", "dept_id": 1,
        "role_ids": [role["id"]], "position_ids": [], "password": password,
    }, admin)
    credentials = login(username, password)
    access = credentials["access_token"]
    info = call("/user/current/info", token=access)
    assert info["username"] == username
    assert [assigned["id"] for assigned in info["roles"]] == [role["id"]]
    call("/user/list", token=access, status=403)
    call("/log/list", token=access, status=403)

    company = {"name": "验收公司", "address": "验收地址", "phone": "123456789"}
    call("/company/profile/update", company, access, status=403)
    call("/company/profile/update", company, admin)
    assert call("/company/profile", token=access)["profile"]["name"] == company["name"]

    call("/user/update", {
        "id": employee["id"], "username": username, "name": "验收员工",
        "dept_id": 1, "available": True, "role_ids": [], "position_ids": [],
    }, admin)
    assert call("/user/current/info", token=access)["roles"] == []
    call("/user/batch/disable", {"ids": [employee["id"], 2147483647]}, admin, status=404)
    assert call("/user/current/info", token=access)["username"] == username
    call("/user/batch/disable", {"ids": [employee["id"]]}, admin)
    call("/user/current/info", token=access, status=401)
    call("/auth/token/refresh", {"refresh_token": credentials["refresh_token"]}, status=401)
    logs = call("/log/list?page=1&page_size=100", token=admin)
    records = json.dumps(logs)
    assert password not in records
    assert "/system/user/disable" in records
    events = [json.loads(log["request_payload"]) for log in logs if log["request_payload"]]
    employee_events = [event for event in events if event.get("user_id") == employee["id"]]
    actions = sorted(event["action"] for event in employee_events)
    assert actions == ["assign-roles", "create", "disable"], actions
    assert all(event["actor"] == os.environ.get("ADMIN_USERNAME", "admin") for event in employee_events)
    print("ERP acceptance passed")


if __name__ == "__main__":
    main()
