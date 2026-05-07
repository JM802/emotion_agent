import uuid
from datetime import datetime
from flask import Flask, request, jsonify

from app.agent_pipeline import AgentPipeline
from database.db import Database

app = Flask(__name__)
pipeline = AgentPipeline()

try:
    db = Database()
    db._connect()
    pipeline.db = db
    print("[app] 数据库连接成功")
except Exception as e:
    print(f"[app] 数据库连接失败{e}")


@app.after_request
def cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    return response


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

@app.route("/analyze", methods=["POST", "OPTIONS"])
def analyze():
    if request.method == "OPTIONS":
        return "", 204

    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error": "请求体为空或非JSON格式"}), 400

    text = body.get("text")
    if not text or not isinstance(text, str) or not text.strip():
        return jsonify({"error": "text 字段为必填"}), 400

    input_data = {
        "id": body.get("id") or str(uuid.uuid4()),
        "user_id": body.get("user_id", "anonymous"),
        "text": text.strip(),
        "source": body.get("source", "api"),
        "created_at": body.get("created_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    try:
        result = pipeline.run(input_data)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": f"分析失败: {str(e)}"}), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8080, debug=True)
