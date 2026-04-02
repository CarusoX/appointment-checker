"""
Opens the login page in a real browser. Log in manually and
this script will capture the exact request to the Token endpoint.
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
            url = request.url
            if "Token" in url or "token" in url.lower() or "login" in url.lower():
                entry = {
                    "url": url,
                    "method": request.method,
                    "headers": dict(request.headers),
                    "post_data": request.post_data,
                }
                captured.append(entry)
                print(f"\n{'='*60}")
                print(f"CAPTURED: {request.method} {url}")
                print(f"{'='*60}")
                print(f"Headers:\n{json.dumps(dict(request.headers), indent=2)}")
                if request.post_data:
                    try:
                        body = json.loads(request.post_data)
                        print(f"Body:\n{json.dumps(body, indent=2)}")
                    except Exception:
                        print(f"Body (raw): {request.post_data}")

        def on_response(response):
            url = response.url
            if "Token" in url or "token" in url.lower():
                print(f"\nResponse: {response.status}")
                try:
                    body = response.json()
                    # Redact tokens
                    for key in list(body.keys()):
                        if "token" in key.lower():
                            body[key] = body[key][:20] + "..." if isinstance(body[key], str) else body[key]
                    print(f"Response body:\n{json.dumps(body, indent=2)}")
                except Exception:
                    print(f"Response body: {response.text()[:500]}")

        page.on("request", on_request)
        page.on("response", on_response)

        print("Opening login page... Log in manually.")
        print("The script will capture the Token request.\n")
        page.goto("https://miportal.sanatorioallende.com/auth/loginPortal")

        # Wait for the user to log in — keep the browser open until manually closed
        try:
            page.wait_for_url("**/portal/**", timeout=300000)  # wait up to 5 min
            print("\nLogin detected! Redirected to portal.")
        except Exception:
            pass

        if captured:
            print(f"\n{'='*60}")
            print("SUMMARY — all captured requests:")
            print(f"{'='*60}")
            for c in captured:
                print(json.dumps(c, indent=2))

            with open("captured_login.json", "w") as f:
                json.dump(captured, f, indent=2)
            print("\nSaved to captured_login.json")
        else:
            print("\nNo Token requests captured.")

        browser.close()


if __name__ == "__main__":
    main()
