"""
Quick end-to-end test for IOAF Tier 2 (ChromaDB) and Tier 3 (JSON facts).
Run: py test_memory.py
"""
import sys, os, json, time
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent))

from core.memory import MemoryManager
from core.models import OllamaClient

FAKE_SESSION = {
    "name": "memory_test_session",
    "mode": "chat",
    "model": "mistral:latest",
    "created": "2026-05-09T08:00:00",
    "messages": [
        {"role": "user",      "content": "My name is Michael and I am working on AXIO."},
        {"role": "assistant", "content": "Got it! I'll remember that you're building AXIO."},
        {"role": "user",      "content": "The main project is the IOAF memory system."},
        {"role": "assistant", "content": "Understood — IOAF three-tier memory architecture."},
    ],
}

def check_dir(label, path):
    p = Path(path)
    if not p.exists():
        print(f"  {label}: NOT FOUND")
        return 0
    items = list(p.rglob("*"))
    size  = sum(f.stat().st_size for f in items if f.is_file())
    print(f"  {label}: {len(items)} files, {size:,} bytes")
    return size

def main():
    print("\n=== AXIO Memory End-to-End Test ===\n")

    mem_dir   = Path.home() / ".axio" / "memory"
    chroma_dir = Path.home() / ".axio" / "chroma"

    print("Before store_session():")
    check_dir("  Tier 3 (~/.axio/memory)", mem_dir)
    check_dir("  Tier 2 (~/.axio/chroma)", chroma_dir)
    print()

    ollama = OllamaClient()
    if not ollama.is_running():
        print("ERROR: Ollama is not running. Start it with: ollama serve")
        sys.exit(1)

    mem = MemoryManager(mode="chat")

    print("Running auto_update_facts() (Tier 3)...")
    for msg in FAKE_SESSION["messages"]:
        if msg["role"] == "user":
            mem.auto_update_facts(msg["content"], "")
    print("  Done.\n")

    print("Running store_session() (Tier 2 + Tier 3 summary)...")
    print("  (This calls qwen3:14b to summarize, then nomic-embed-text to embed — may take ~60s)")
    t0 = time.time()
    mem.store_session(FAKE_SESSION, ollama_client=ollama)
    elapsed = round(time.time() - t0, 1)
    print(f"  Done in {elapsed}s.\n")

    print("After store_session():")
    tier3_size = check_dir("  Tier 3 (~/.axio/memory)", mem_dir)
    tier2_size = check_dir("  Tier 2 (~/.axio/chroma)", chroma_dir)
    print()

    # Show what facts were written
    chat_facts = mem_dir / "chat_memory.json"
    if chat_facts.exists():
        data = json.loads(chat_facts.read_text(encoding="utf-8"))
        print("Tier 3 facts written (chat_memory.json):")
        for k, v in data.items():
            print(f"  {k}: {v}")
        print()

    # Test recall
    print("Testing Tier 2 recall for 'AXIO memory system'...")
    results = mem.recall("AXIO memory system", n_results=3)
    if results:
        print(f"  Recalled {len(results)} result(s):")
        for r in results:
            print(f"    [dist={r.get('distance', 0):.3f}] {r.get('text', '')[:120]}")
    else:
        print("  No results recalled — Tier 2 may not have written (check ChromaDB/embed errors above).")
    print()

    # Summary
    passed = []
    failed = []
    (passed if tier3_size > 0 else failed).append("Tier 3 JSON facts written")
    (passed if tier2_size > 0 else failed).append("Tier 2 ChromaDB written")
    (passed if results    else failed).append("Tier 2 recall returns results")

    print("=== Results ===")
    for p in passed: print(f"  PASS  {p}")
    for f in failed: print(f"  FAIL  {f}")
    print()

if __name__ == "__main__":
    main()
