import sys
sys.stdout.reconfigure(encoding='utf-8')

with open("google_finance_dump.html", "r", encoding="utf-8") as f:
    html = f.read()

print("HTML length:", len(html))
print("Contains 'unusual traffic':", "unusual traffic" in html.lower())
print("Contains 'captcha':", "captcha" in html.lower())
print("Contains 'robot':", "robot" in html.lower())
print("Contains 'google':", "google" in html.lower())
print("Contains 'finance':", "finance" in html.lower())

print("\n--- FIRST 2000 CHARS ---")
print(html[:2000])
