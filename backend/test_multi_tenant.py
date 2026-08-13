"""多租户隔离测试"""
import requests

BASE = "http://127.0.0.1:8001/api/v1"


def login(username, password):
    r = requests.post(f"{BASE}/auth/login", json={"username": username, "password": password})
    data = r.json()["data"]
    me = requests.get(f"{BASE}/auth/me", headers={"Authorization": f"Bearer {data['access_token']}"})
    user = me.json()["data"]
    return data["access_token"], user["role"], user["tenant_id"]


def create_enterprise(token, name, credit_code, industry="WHOLESALE_RETAIL"):
    return requests.post(f"{BASE}/enterprises", headers={"Authorization": f"Bearer {token}"},
                         json={"name": name, "credit_code": credit_code, "industry": industry})


def list_enterprises(token):
    return requests.get(f"{BASE}/enterprises", headers={"Authorization": f"Bearer {token}"})


def get_enterprise(token, eid):
    return requests.get(f"{BASE}/enterprises/{eid}", headers={"Authorization": f"Bearer {token}"})


def ensure_enterprise(token, name, credit_code):
    """确保企业存在，若不存在则创建"""
    r = list_enterprises(token)
    existing = [e for e in r.json()["data"]["enterprises"] if e["name"] == name]
    if existing:
        return existing[0]
    r = create_enterprise(token, name, credit_code)
    return r.json()["data"]


# ── 1. 登录两个租户的管理员 ──
t1_tok, t1_role, t1_tid = login("admin_t1", "a123456")
t2_tok, t2_role, t2_tid = login("admin_t2", "a123456")
print(f"[OK] T1 login: tenant={t1_tid}, role={t1_role}")
print(f"[OK] T2 login: tenant={t2_tid}, role={t2_role}")

# ── 2. 确保两租户企业 ──
t1_ent = ensure_enterprise(t1_tok, "T1企业A", "911100000000000011")
t2_ent = ensure_enterprise(t2_tok, "T2企业B", "911100000000000022")
print(f"[OK] T1 enterprise: id={t1_ent['id'][:8]}...")
print(f"[OK] T2 enterprise: id={t2_ent['id'][:8]}...")

# ── 3. T1 查询企业列表（应只能看到自己的） ──
r = list_enterprises(t1_tok)
names = [e["name"] for e in r.json()["data"]["enterprises"]]
assert "T1企业A" in names, f"T1 should see its own enterprise: {names}"
assert "T2企业B" not in names, f"T1 should NOT see T2's enterprise: {names}"
print(f"[PASS] T1 list: only sees {names} (cross-tenant filtered)")

# ── 4. T2 尝试访问 T1 的企业（应返回业务错误 40001） ──
r = get_enterprise(t2_tok, t1_ent["id"])
data = r.json()
assert data["code"] == 40001, f"T2 accessing T1 enterprise should fail: {data}"
print(f"[PASS] T2 cannot access T1 enterprise (code={data['code']}: {data['message']})")

# ── 5. T2 查询自己的企业列表 ──
r = list_enterprises(t2_tok)
names2 = [e["name"] for e in r.json()["data"]["enterprises"]]
assert "T2企业B" in names2, f"T2 should see its own enterprise: {names2}"
assert "T1企业A" not in names2, f"T2 should NOT see T1's enterprise: {names2}"
print(f"[PASS] T2 list: only sees {names2} (cross-tenant filtered)")

# ── 6. T1 viewer 也能访问自己租户的企业 ──
v_tok, _, _ = login("viewer_t1", "a123456")
r = list_enterprises(v_tok)
names_v = [e["name"] for e in r.json()["data"]["enterprises"]]
assert "T1企业A" in names_v, f"Viewer should see T1's enterprise: {names_v}"
print(f"[PASS] Viewer in T1 sees: {names_v}")

print("\n=== ALL MULTI-TENANT ISOLATION TESTS PASSED ===")
