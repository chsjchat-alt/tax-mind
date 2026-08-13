"""Download Swagger UI + ReDoc static files for local serving."""
import urllib.request
import os

os.makedirs("static", exist_ok=True)

files = {
    "swagger-ui-bundle.js": "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
    "swagger-ui.css": "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css",
}

# Try multiple redoc URLs
redoc_urls = [
    "https://cdn.jsdelivr.net/npm/redoc@2.2.0/bundles/redoc.standalone.js",
    "https://cdn.jsdelivr.net/npm/redoc@2.1.5/bundles/redoc.standalone.js",
    "https://cdn.jsdelivr.net/npm/redoc@2.0.0/bundles/redoc.standalone.js",
    "https://unpkg.com/redoc@2.2.0/bundles/redoc.standalone.js",
]

for name, url in files.items():
    print(f"Downloading {name}...")
    urllib.request.urlretrieve(url, f"static/{name}")
    size = os.path.getsize(f"static/{name}")
    print(f"  OK: {size} bytes")

# Try redoc
for url in redoc_urls:
    try:
        print(f"Trying ReDoc: {url}...")
        urllib.request.urlretrieve(url, "static/redoc.standalone.js")
        size = os.path.getsize("static/redoc.standalone.js")
        print(f"  OK: {size} bytes")
        break
    except Exception as e:
        print(f"  Failed: {e}")

print("Done")
