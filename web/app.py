from flask import Flask, render_template, request, jsonify
import db

app = Flask(__name__)

@app.get("/")
def index():
    return render_template("index.html")

@app.get("/search")
def lookup():
    pasted_url = request.args.get("url", "")   # unused for now; the scraping step will use it
    return render_template("search.html", pasted_url=pasted_url)

@app.get("/health")
def health():
    try:
        with db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
        return jsonify(status="ok", db="up")
    except Exception as e:
        return jsonify(status="error", db=str(e)), 503

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
