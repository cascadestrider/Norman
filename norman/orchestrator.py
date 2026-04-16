"""Norman Orchestrator — dispatches scouts in parallel, aggregates, routes to analyst → delivery."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

from norman.models import Lead, ScoutResult
from norman.scouts import ALL_SCOUTS
from norman.scouts.base import BaseScout
from norman.analyst import run_analyst
from norman.delivery import run_delivery
from norman.db import init_db, get_seen_urls, save_lead
from norman.config import SCORE_THRESHOLD


def run_pipeline():
    """Execute the full Norman pipeline: scouts → analyst → delivery."""
    today = str(date.today())
    print(f"\n🚀 Norman pipeline starting — {today}")

    # --- Init DB and get seen URLs ---
    conn = init_db()
    seen_urls = get_seen_urls(conn)
    print(f"📦 {len(seen_urls)} previously seen URLs loaded")

    # --- Step 1: Dispatch all scouts in parallel ---
    scouts: list[BaseScout] = [ScoutClass() for ScoutClass in ALL_SCOUTS]
    scout_results: dict[str, ScoutResult] = {}

    print(f"🔍 Dispatching {len(scouts)} scouts in parallel...")
    with ThreadPoolExecutor() as executor:
        futures = {
            executor.submit(scout.run, seen_urls): scout.name
            for scout in scouts
        }
        for future in as_completed(futures):
            scout_name = futures[future]
            try:
                result = future.result()
                scout_results[scout_name] = result
                lead_count = len(result.leads)
                err_count = len(result.errors)
                status = "✅" if not result.errors else "⚠️"
                print(f"  {status} {scout_name}: {lead_count} leads, {err_count} errors")
            except Exception as e:
                print(f"  ❌ {scout_name}: crashed — {e}")
                scout_results[scout_name] = ScoutResult(
                    source=scout_name.lower(),
                    leads=[],
                    errors=[f"{scout_name} crashed: {e}"],
                )

    # --- Step 2: Collect and deduplicate leads ---
    all_leads: list[Lead] = []
    seen_in_run: set[str] = set()

    for name, result in scout_results.items():
        for lead in result.leads:
            if lead.url not in seen_in_run and lead.score >= SCORE_THRESHOLD:
                seen_in_run.add(lead.url)
                all_leads.append(lead)

    print(f"\n📊 {len(all_leads)} qualifying leads after dedup (threshold: {SCORE_THRESHOLD})")

    # --- Step 3: Dispatch Analyst ---
    print("🧠 Running Analyst...")
    try:
        analyst_output = run_analyst(all_leads)
        print(f"  ✅ Analyst enriched {analyst_output.total_leads} leads")
    except Exception as e:
        print(f"  ❌ Analyst failed: {e}")
        print("  ⚠️ Falling back to raw leads for delivery")
        # Fallback: create minimal analyst output from raw leads
        from norman.models import AnalystOutput, AnalystLead
        fallback_leads = [
            AnalystLead(
                url=l.url, title=l.title, score=l.score, keywords=l.keywords,
                source=l.source, platform=l.platform, geo=l.geo, snippet=l.snippet,
            )
            for l in all_leads
        ]
        analyst_output = AnalystOutput(
            date=today,
            total_leads=len(all_leads),
            segments={"general": fallback_leads},
            top_3=fallback_leads[:3],
        )

    # --- Step 4: Build run log (printed to terminal + passed to Delivery) ---
    run_log = _build_run_log(today, scout_results, analyst_output)
    print(run_log)

    # --- Step 5: Dispatch Delivery ---
    print("📬 Running Delivery...")
    delivery_status = run_delivery(analyst_output, run_log=run_log)
    print(f"  Markdown:  {delivery_status.markdown}")
    print(f"  Discord:   {delivery_status.discord}")
    print(f"  Klaviyo:   {delivery_status.klaviyo}")
    print(f"  Dashboard: {delivery_status.dashboard}")

    # --- Save new leads to DB ---
    for lead in all_leads:
        save_lead(conn, lead)
    conn.close()


def _build_run_log(today, scout_results, analyst_output) -> str:
    """Build the terminal-style run summary string. Printed locally and sent to Discord."""
    scout_statuses = []
    for name, result in scout_results.items():
        icon = "✅" if not result.errors else "⚠️"
        scout_statuses.append(f"{name} {icon}")

    top_lead = analyst_output.top_3[0] if analyst_output.top_3 else None
    top_str = (
        f"{top_lead.title[:60]} ({top_lead.source}) — Score {top_lead.score}/100"
        if top_lead else "none"
    )

    sources_with_leads = sum(1 for r in scout_results.values() if r.leads)

    return (
        f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Norman Run Complete — {today}\n"
        f"Scouts: {' | '.join(scout_statuses)}\n"
        f"Total leads: {analyst_output.total_leads} across {sources_with_leads} sources\n"
        f"Top lead: {top_str}\n"
        f"Analyst: ✅ {analyst_output.total_leads} leads enriched\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
