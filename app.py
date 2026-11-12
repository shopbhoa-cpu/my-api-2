"""
XWorld API - server nhỏ trả phiên mới nhất và lịch sử phiên (phiên + phòng bị giết).
Một file duy nhất, chỉ dùng thư viện có sẵn của Python (không cần requirements).

Chỉ có đúng 1 trang: mở link là thấy JSON toàn bộ lịch sử (mới nhất ở trên),
tự cập nhật mỗi 3 giây. Không có lệnh/đường dẫn nào khác.

Dạng dữ liệu: [{"issue_id": ..., "room": 3, "room_name": "Phòng giám đốc"}, ...]

Biến môi trường (đặt trong trang quản lý của nơi host, KHÔNG viết vào code):
    GAME_USER_ID, GAME_SECRET_KEY   bắt buộc
    API_TOKEN                       tùy chọn; đặt thì phải mở link kèm ?token=... (hoặc header X-Api-Key)
    PORT                            host tự cấp (mặc định 8000)

Chạy thử trên máy: python app.py   rồi mở http://localhost:8000
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

URL = "https://api.escapemaster.net/escape_game/recent_10_issues?asset=BUILD"
SCAN_EVERY = 3
HISTORY_FILE = "history.jsonl"

ROOM_NAMES = ["Nhà Kho", "Phòng họp", "Phòng giám đốc", "Phòng trò chuyện",
              "Phòng giám sát", "Văn phòng", "Phòng tài vụ", "Phòng nhân sự"]
ROOM_BASE = 1  # room_id đếm từ 1 đến 8 (1 = Nhà Kho ... 8 = Phòng nhân sự)

ISSUE_KEYS = ("issue_id", "issue", "id")
ROOM_KEYS = ("killed_room", "kill_room", "killed_room_id", "kill_room_id", "room_id", "room")

BASE_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
    "Origin": "https://xworld.info",
    "Referer": "https://xworld.info/",
}


# ---------- đăng nhập ----------
def candidates(uid, key):
    """Các kiểu gửi đăng nhập có thể có: (tên kiểu, headers, query)."""
    return [
        ("query userId+secretKey", {}, {"userId": uid, "secretKey": key}),
        ("query user_id+user_secret_key", {}, {"user_id": uid, "user_secret_key": key}),
        ("query user_id+secret_key", {}, {"user_id": uid, "secret_key": key}),
        ("header userId+secretKey", {"userId": uid, "secretKey": key}, {}),
        ("header user_id+user_secret_key", {"user_id": uid, "user_secret_key": key}, {}),
        ("header user_id+secret_key", {"user_id": uid, "secret_key": key}, {}),
        ("header user-id+secret-key", {"user-id": uid, "secret-key": key}, {}),
        ("header Authorization", {"Authorization": key}, {}),
        ("header Authorization Bearer", {"Authorization": "Bearer " + key}, {}),
        ("header token", {"token": key}, {}),
        ("không đăng nhập", {}, {}),
    ]


def http_get(url, headers):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.read().decode("utf-8")


def extra_headers():
    h = {}
    if os.path.exists("headers.json"):
        with open("headers.json", encoding="utf-8") as f:
            h.update(json.load(f))
    return h


def fetch_with(cand):
    _, hdr, query = cand
    url = URL + ("&" + urllib.parse.urlencode(query) if query else "")
    headers = dict(BASE_HEADERS)
    headers.update(extra_headers())
    headers.update(hdr)
    return http_get(url, headers)


# ---------- phân tích dữ liệu ----------
def find_list(node):
    """Tìm danh sách các dict có khóa phiên trong JSON, bất kể lồng sâu."""
    if isinstance(node, list):
        if node and all(isinstance(x, dict) for x in node) and any(k in node[0] for k in ISSUE_KEYS):
            return node
        for x in node:
            r = find_list(x)
            if r:
                return r
    elif isinstance(node, dict):
        for v in node.values():
            r = find_list(v)
            if r:
                return r
    return None


def pick(d, keys):
    for k in keys:
        if k in d:
            return d[k]
    return None


def room_name(rid):
    try:
        i = int(rid) - ROOM_BASE
        return ROOM_NAMES[i] if 0 <= i < len(ROOM_NAMES) else "?"
    except Exception:
        return "?"


def parse(text):
    try:
        data = json.loads(text)
    except Exception:
        return None
    items = find_list(data)
    if not items:
        return None
    out = [(pick(it, ISSUE_KEYS), pick(it, ROOM_KEYS)) for it in items]
    out.sort(key=lambda x: (x[0] is None, x[0]), reverse=True)  # mới nhất lên trên
    return out


def detect(cands):
    """Thử lần lượt các kiểu đăng nhập, trả về (kiểu, text) đầu tiên lấy được dữ liệu."""
    last = ""
    for c in cands:
        try:
            text = fetch_with(c)
        except Exception as e:
            last = str(e)
            continue
        if parse(text) is not None:
            return c, text
        last = text
    return None, last


# ---------- trang web ----------
PAGE = """<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>XWorld JSON</title>
<style>
  body { margin:0; padding:12px; background:#0f1115; color:#d7dae0; }
  pre { margin:0; white-space:pre-wrap; word-break:break-word;
        font: 13px/1.5 ui-monospace, Menlo, Consolas, monospace; }
</style>
</head>
<body>
<pre id="out">Đang tải...</pre>
<script>
(function () {
  var token = new URLSearchParams(location.search).get("token");
  var url = "/" + (token ? "?token=" + encodeURIComponent(token) : "");
  function tick() {
    fetch(url, { cache: "no-store", headers: { "Accept": "application/json" } })
      .then(function (r) { return r.text(); })
      .then(function (t) {
        try { t = JSON.stringify(JSON.parse(t), null, 2); } catch (e) {}
        document.getElementById("out").textContent = t;
      })
      .catch(function (e) { document.getElementById("out").textContent = "Lỗi kết nối: " + e; });
  }
  tick();
  setInterval(tick, 3000);
})();
</script>
</body>
</html>
"""


# ---------- server ----------
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STATE = {"updated": None, "login": None, "error": None}
HIST = {}  # issue_id -> room_id
LOCK = threading.Lock()
MAX_KEEP = 1000


def poller():
    uid = os.environ.get("GAME_USER_ID")
    key = os.environ.get("GAME_SECRET_KEY")
    if not uid or not key:
        STATE["error"] = "Thiếu GAME_USER_ID / GAME_SECRET_KEY"
        return
    cands = candidates(uid, key)
    cand = None
    while True:
        try:
            text = None
            if cand is not None:
                text = fetch_with(cand)
                if parse(text) is None:
                    cand = None
            if cand is None:
                cand, text = detect(cands)
                if cand is None:
                    STATE["error"] = "Không đăng nhập được: " + str(text)[:120]
                    time.sleep(30)
                    continue
                STATE["login"] = cand[0]
            rows = parse(text)
            with LOCK:
                for iid, rid in rows:
                    if iid is not None:
                        HIST[iid] = rid
                if len(HIST) > MAX_KEEP:
                    for k in sorted(HIST)[:len(HIST) - MAX_KEEP]:
                        del HIST[k]
                STATE["updated"] = time.time()
                STATE["error"] = None
        except Exception as e:
            STATE["error"] = str(e)[:200]
        time.sleep(SCAN_EVERY)


def item(iid, rid):
    return {"issue_id": iid, "room": rid, "room_name": room_name(rid)}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # bớt ồn
        pass

    def send_json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html):
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        accept = self.headers.get("Accept", "")

        # trình duyệt mở link: hiện JSON tự làm mới mỗi 3 giây
        if "text/html" in accept:
            return self.send_html(PAGE)

        # còn lại (trang tự gọi / gọi từ code): trả JSON thuần
        need = os.environ.get("API_TOKEN")
        if need:
            got = (q.get("token") or [self.headers.get("X-Api-Key", "")])[0]
            if got != need:
                return self.send_json(401, {"error": "unauthorized"})
        with LOCK:
            ids = sorted(HIST, reverse=True)
            data = [item(i, HIST[i]) for i in ids]
        if not data and STATE["error"]:
            return self.send_json(503, {"error": STATE["error"]})
        return self.send_json(200, data)


if __name__ == "__main__":
    threading.Thread(target=poller, daemon=True).start()
    port = int(os.environ.get("PORT", "8000"))
    print(f"API chạy ở cổng {port}")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
