"""Synthetic-only comparison. Offline by default; --live makes billed model calls.

Run from backend: python tools/benchmark_case_memory.py [--live] [--env-file PATH]
Never reads saved cases/uploads. Local reply cache is fresh per benchmark; provider
prefix caching is unknown. Printed usage is tokens, not a monetary cost estimate.
"""
import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Explicitly enable paid Tokendance calls on synthetic data")
    parser.add_argument("--env-file", type=Path, help="Optional private model configuration; never printed")
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="qier-memory-benchmark-") as folder:
        directory = Path(folder)
        for name in ("CASES", "CACHE", "REVIEWS", "RUNS", "PRIVATE", "CASE_MEMORY"):
            os.environ["XRAY_" + name + "_DIR"] = str(directory / name.lower())
        os.environ.update(XRAY_COMMERCIAL="", XRAY_AMAC_DETAIL="0", XRAY_CNINFO="0")
        from app import config, privacy
        if args.env_file:
            config._load_env(args.env_file)
        from app.llm import LLM
        from app.assistant import answer, context
        from app.case_memory.store import MemoryStore
        from app.case_memory.retriever import retrieve
        from app.models import ChatIn
        from tests.test_case_memory import owned
        import httpx

        usage, input_sizes = [], []
        def observe(response):
            response.read()
            try:
                stats = response.json().get("usage", {})
                usage.append({k:stats.get(k) for k in ("prompt_tokens", "completion_tokens", "total_tokens")})
            except ValueError:
                usage.append({"status": response.status_code})
        class Meter(LLM):
            def _call(self, model, messages, json_out, temperature):
                input_sizes.append(sum(len(str(m["content"])) for m in messages))
                return super()._call(model, messages, json_out, temperature)
        gateway = Meter(base_url=os.getenv("TOKENDANCE_BASE_URL", ""), api_key=os.getenv("TOKENDANCE_API_KEY", ""),
            model=os.getenv("TOKENDANCE_MODEL", ""), mode="live" if args.live else "off",
            json_mode=True, cache_dir=directory / "model-cache",
            client=httpx.Client(trust_env=False, event_hooks={"response":[observe]}))
        if args.live and (not gateway.configured or gateway.model != "qwen3.8-max" or gateway.enable_thinking is not False):
            raise SystemExit("Live comparison requires configured qwen3.8-max with thinking disabled; no calls sent")
        config.CASE_MEMORY_ENABLED = True
        owner = privacy.OWNER.set("guest-a")
        try:
            for label, rows, question in (
                ("small", 0, "合同说能退款，我急用钱时能拿回来吗？"),
                ("medium", 60, "我想存20w但好害怕怎么办"),
                ("large", 400, "我想存20w但好害怕怎么办"),
            ):
                case = owned(rows)
                v = case.versions[-1]
                store = MemoryStore()
                start = time.perf_counter()
                memory = store.get_or_build(case, v.no, case.owner_id)
                cold_ms = (time.perf_counter()-start)*1000
                start = time.perf_counter()
                assert store.get_or_build(case, v.no, case.owner_id) == memory
                warm_ms = (time.perf_counter()-start)*1000
                start = time.perf_counter()
                selected = retrieve(case, v, case.owner_id, memory, question, [])
                print(json.dumps({"size":label, "full_context_chars":len(json.dumps(context(case,v), ensure_ascii=False)),
                    "memory_cold_ms":round(cold_ms,2), "memory_warm_ms":round(warm_ms,2),
                    "retrieval_ms":round((time.perf_counter()-start)*1000,2),
                    "selected_context_chars":len(json.dumps(selected.context, ensure_ascii=False)),
                    "complete":selected.complete, "omitted_units":len(selected.omitted_units)}, ensure_ascii=False), flush=True)
                if not args.live:
                    continue
                for mode in ("full", "selective"):
                    config.ASSISTANT_CONTEXT_MODE = mode
                    usage.clear()
                    input_sizes.clear()
                    start = time.perf_counter()
                    reply = answer(case, ChatIn(text=question), gateway)
                    print(json.dumps({"size":label,"mode":mode,"seconds":round(time.perf_counter()-start,2),
                        "calls":len(input_sizes),"input_chars":input_sizes,"usage":usage,"answer":reply.text,
                        "citations":reply.citations,"context_mode":reply.context_mode,"result_mode":reply.mode,
                        "error_code":reply.error_code,"rewrites":reply.rewrites,"dropped":reply.dropped}, ensure_ascii=False), flush=True)
        finally:
            privacy.OWNER.reset(owner)
            gateway.client.close()


if __name__ == "__main__":
    main()
