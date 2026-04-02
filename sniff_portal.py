"""
Opens the portal in a browser. Log in, then navigate to your appointments.
This captures ALL API requests so we can see the real endpoint paths.
"""

import json
from playwright.sync_api import sync_playwright


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        captured = []

        def on_request(request):
            if "/backend/" not in request.url:
                return
            # Skip static assets
            if any(ext in request.url for ext in [".js", ".css", ".png", ".jpg", ".svg", ".woff"]):
                return

            entry = {
                "method": request.method,
                "url": request.url,
                "post_data": request.post_data,
            }
            captured.append(entry)
            print(f"\n>> {request.method} {request.url}")
            if request.post_data:
                try:
                    body = json.loads(request.post_data)
                    print(f"   Body: {json.dumps(body, indent=2, ensure_ascii=False)[:1000]}")
                except Exception:
                    print(f"   Body: {request.post_data[:500]}")

        def on_response(response):
            if "/backend/" not in response.url:
                return
            if any(ext in response.url for ext in [".js", ".css", ".png", ".jpg", ".svg", ".woff"]):
                return
            if "Token" in response.url:
                return  # already captured in login sniff

            status = response.status
            print(f"   <- {status}")
            if status == 200:
                try:
                    body = response.json()
                    text = json.dumps(body, indent=2, ensure_ascii=False)
                    print(f"   Response: {text[:2000]}")
                    if len(text) > 2000:
                        print(f"   ... (truncated, {len(text)} total chars)")
                except Exception:
                    pass

        page.on("request", on_request)
        page.on("response", on_response)

        print("Opening login page...")
        print("1) Log in with your credentials")
        print("2) Navigate to your appointments (Turnos)")
        print("3) Try booking a new appointment to see availability endpoints")
        print("4) Close the browser when done\n")

        page.goto("https://miportal.sanatorioallende.com/auth/loginPortal")

        # Keep browser open until user closes it
        try:
            page.wait_for_event("close", timeout=600000)
        except Exception:
            pass

        if captured:
            print(f"\n{'='*60}")
            print(f"CAPTURED {len(captured)} API requests")
            print(f"{'='*60}")

            with open("captured_portal.json", "w") as f:
                json.dump(captured, f, indent=2, ensure_ascii=False)
            print("Saved to captured_portal.json")
        else:
            print("\nNo API requests captured.")

        browser.close()


if __name__ == "__main__":
    main()
