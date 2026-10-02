#!/usr/bin/env python3
"""Exercise Nginx -> Spring Boot -> real PostgreSQL, then remove the test note."""
import json
import time
import urllib.error
import urllib.request
import uuid

BASE = "http://127.0.0.1:8080"

def request(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as response:
        payload = response.read()
        return response.status, response.headers, json.loads(payload) if payload else None

def main():
    for attempt in range(60):
        try:
            request("GET", "/api/notes")
            break
        except (urllib.error.URLError, TimeoutError):
            if attempt == 59:
                raise
            time.sleep(2)
    marker = "Smoke " + str(uuid.uuid4())
    status, headers, note = request("POST", "/api/notes", {"title": marker, "content": "Disposable test"})
    assert status == 201 and headers.get("X-Request-Id")
    path = headers["Location"]
    try:
        assert request("GET", path)[2]["title"] == marker
        updated = request("PUT", path, {"title": marker, "content": "Updated"})
        assert updated[2]["content"] == "Updated"
        assert any(item["id"] == note["id"] for item in request("GET", "/api/notes")[2]["items"])
    finally:
        assert request("DELETE", path)[0] == 204
    try:
        request("GET", path)
        raise AssertionError("Deleted note still exists")
    except urllib.error.HTTPError as error:
        assert error.code == 404
    print("PASS: same-origin create, read, list, update, delete, and PostgreSQL persistence.")

if __name__ == "__main__":
    main()
