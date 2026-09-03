import requests
from datetime import date

s = requests.Session()
r = s.get("http://127.0.0.1:8080/health")
print("health", r.status_code, r.json())
r = s.get("http://127.0.0.1:8080/")
print("home_redir", r.status_code, r.url)
r = s.post(
    "http://127.0.0.1:8080/login",
    data={"login": "admin", "password": "admin123"},
    allow_redirects=True,
)
print("login", r.status_code, r.url, "cookie", bool(s.cookies))
r = s.get("http://127.0.0.1:8080/")
print("list", r.status_code, "Заказы" in r.text)

# discover mechanic id
from sqlalchemy import select
from app.database import SessionLocal
from app.models import User, ServiceCenter

db = SessionLocal()
admin = db.scalar(select(User).where(User.login == "admin"))
mech = db.scalar(select(User).where(User.login == "mechanic_tbilisi"))
center = db.scalar(select(ServiceCenter).where(ServiceCenter.code == "tbilisi"))
db.close()

r = s.post(
    "http://127.0.0.1:8080/orders/save",
    data={
        "order_date": date.today().isoformat(),
        "assignee_id": str(mech.id),
        "service_center_id": str(center.id),
        "new_machine_serial": "SN-TEST-002",
        "new_machine_model": "Delonghi ECAM350.50",
        "new_client_phone": "555994591",
        "new_client_name": "Daniel",
        "new_issue_reason": "не греет",
        "comment": "test order",
        "line_type": "work",
        "description": "descaling,kapuchinator clean",
        "part_code": "",
        "payment_type": "Cash",
        "amount_work": "100",
        "amount_parts": "0",
    },
    allow_redirects=True,
)
print("save", r.status_code, r.url)
print("has_serial", "SN-TEST-002" in r.text)

r = s.get("http://127.0.0.1:8080/orders/partials/history", params={"serial": "SN-TEST-002"})
print("history", r.status_code, "SN-TEST-002" in r.text or "Предыдущих" in r.text)

r = s.get("http://127.0.0.1:8080/reports")
print("reports", r.status_code, "Сводные" in r.text)

s2 = requests.Session()
r = s2.post(
    "http://127.0.0.1:8080/login",
    data={"login": "mechanic_batumi", "password": "mechanic123"},
    allow_redirects=True,
)
print("mech_login", r.status_code, r.url)
r = s2.get("http://127.0.0.1:8080/")
print("mech_sees_foreign", "SN-TEST-002" in r.text)

s3 = requests.Session()
r = s3.post(
    "http://127.0.0.1:8080/login",
    data={"login": "mechanic_tbilisi", "password": "mechanic123"},
    allow_redirects=True,
)
r = s3.get("http://127.0.0.1:8080/")
print("owner_sees", "SN-TEST-002" in r.text)
print("ok")
