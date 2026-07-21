import re
import sqlite3

conn = sqlite3.connect("data/app.db")
conn.row_factory = sqlite3.Row

queries = [
    ("doc", "SELECT id, title, current_content AS blob FROM documents WHERE id LIKE '2a5d262d%' OR title LIKE '%Prelim%'"),
    ("note", "SELECT id, title, content AS blob FROM notes WHERE id LIKE 'aac4cfed%' OR title LIKE '%Prelim%' OR content LIKE '%Prelim%'"),
    ("note2", "SELECT id, title, content AS blob FROM notes WHERE content LIKE '%prelim%' OR title LIKE '%SWE Product%'"),
    ("job", "SELECT id, company, title, apply_url, source_url FROM job_records WHERE company LIKE '%Prelim%' OR title LIKE '%Prelim%'"),
]

for label, sql in queries:
    print(f"=== {label} ===")
    for r in conn.execute(sql):
        blob = r["blob"] or ""
        print(r["id"][:8], (r["title"] if "title" in r.keys() else "")[:70])
        for u in re.findall(r"https?://[^\s\"'<>]+", blob)[:10]:
            print(" ", u)
        if label == "job":
            print(" apply_url:", r["apply_url"], "source:", r["source_url"])
