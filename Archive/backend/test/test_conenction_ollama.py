# debug_ollama.py  — run this from your test/ folder
import requests
import time

BASE = "http://localhost:11434"

print("1. Checking Ollama is running...")
r = requests.get(f"{BASE}/api/tags", timeout=5)
print("   Status:", r.status_code)
models = [m["name"] for m in r.json().get("models", [])]
print("   Models:", models)

print("\n2. Timing a SHORT prompt (no context)...")
t0 = time.time()
r = requests.post(f"{BASE}/api/chat", json={
    "model": "llama3:latest",
    "messages": [{"role": "user", "content": "Say OK"}],
    "stream": False,
    "options": {"num_predict": 5}
}, timeout=300)
print(f"   Done in {time.time()-t0:.1f}s — reply: {r.json()['message']['content']!r}")

print("\n3. Timing a LONG prompt (2500 chars context, like real RAG)...")
fake_context = "This is a test document. " * 100   # ~2500 chars
t0 = time.time()
r = requests.post(f"{BASE}/api/chat", json={
    "model": "llama3:latest",
    "messages": [
        {"role": "system", "content": "Answer only from context."},
        {"role": "user",   "content": f"CONTEXT:\n{fake_context}\n\nQUESTION: What is this about? Answer in one sentence."}
    ],
    "stream": False,
    "options": {"num_predict": 50}
}, timeout=600)
elapsed = time.time() - t0
print(f"   Done in {elapsed:.1f}s")
print(f"   Reply: {r.json()['message']['content'][:100]!r}")
print(f"\n   → Your RAG calls will take roughly {elapsed:.0f}-{elapsed*2:.0f}s per query on this machine.")