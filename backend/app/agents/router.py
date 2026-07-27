"""Deterministic intent router. Maps a natural-language question to the right analysis and
builds a structured answer + human-in-the-loop action suggestions. Works with no LLM key;
the LLM (when configured) only rewrites the prose message on top of this structured result."""
from __future__ import annotations

import re

from app.actions.reorder_action import reorder_recommendations
from app.agents import tools as T

# intent -> compiled keyword pattern (checked in order)
_INTENTS: list[tuple[str, re.Pattern]] = [
    ("bottleneck", re.compile(r"bottleneck|constrain|congest|queue")),
    ("schedule", re.compile(r"schedul|optimi[sz]e|sequenc|\bplan\b|makespan")),
    ("scenario", re.compile(r"scenario|throughput vs|compare .*plan|trade[- ]?off")),
    ("prioritize", re.compile(r"prioriti|most important|urgent order|rank .*order")),
    ("allocation", re.compile(r"allocat|assign .*worker|workforce|staff|resource")),
    ("delay_risk", re.compile(r"delay|at[- ]?risk|late|risk of|will .*miss")),
    ("downtime", re.compile(r"downtime|break ?down|machine fail|maintenance|sensor|health")),
    ("demand", re.compile(r"demand|forecast|sell|sales|how much .*need")),
    ("reorder", re.compile(r"re-?order|material|stock|inventory|procure|supplier")),
    ("capacity", re.compile(r"capac|utili[sz]ation|load|can we handle|enough")),
]


def _email_action(subject: str, details: list[str]) -> dict:
    body = subject + "\n\n" + "\n".join(f"- {d}" for d in details[:20])
    return {"id": "send_email", "label": "Email this alert to operations",
            "params": {"subject": subject, "body": body}}


def _chart_action(kind: str, label: str) -> dict:
    return {"id": "generate_chart", "label": label, "params": {"kind": kind}}


def detect_intent(query: str) -> str:
    q = (query or "").lower()
    for intent, pattern in _INTENTS:
        if pattern.search(q):
            return intent
    return "overview"


def route(query: str) -> dict:
    intent = detect_intent(query)

    if intent == "capacity":
        data = T.tool_capacity_analysis()
        constrained = data.get("constrained_machines", [])
        headline = f"Overall utilisation {data['overall_utilization_pct']:.0f}%. {data['verdict']}"
        details = [
            f"{m['machine_id']} {m['machine_name']}: {m['utilization_pct']:.0f}% ({m['status']}"
            + (f", shortfall {m['expected_shortfall_hours']:.0f}h" if m.get("expected_shortfall_hours", 0) > 0 else "")
            + ")"
            for m in data["per_machine"]
        ]
        actions = [_chart_action("capacity", "Show utilisation chart")]
        if constrained:
            # over/near capacity -> run OR-Tools to actually produce an optimized plan
            overtime = data.get("total_expected_shortfall_hours", 0)
            plan = T.tool_optimize_schedule("min_risk")          # OR-Tools CP-SAT
            k = plan.get("kpis", {})
            data = {"capacity": data, "optimized_plan": plan}
            details.append(
                f"{len(constrained)} machine(s) over/near capacity ({', '.join(constrained)}); "
                f"~{overtime:.0f}h overtime needed.")
            details.append(
                f"OR-Tools optimized (min-risk) plan generated: {plan.get('scheduled_orders', 0)} orders, "
                f"makespan {k.get('makespan_hours')}h, tardiness {k.get('total_tardiness_hours')}h, "
                f"cost Rs{k.get('total_energy_cost_inr')}.")
            actions = [
                {"id": "export_plan", "label": "Export this OR-Tools optimized plan (CSV)",
                 "params": {"scenario": "min_risk"}},
                _chart_action("capacity", "Show utilisation chart"),
                _email_action("Machines over capacity - action needed", details),
            ]
        agent = "Capacity & Scheduling"

    elif intent == "bottleneck":
        data = T.tool_detect_bottlenecks()
        headline = f"Primary bottleneck: {data['primary_bottleneck']}"
        details = [f"{b['machine_id']}: score {b['bottleneck_score']:.0f} "
                   f"(util {b['utilization_pct']:.0f}%, {b['pending_jobs']} jobs)" for b in data["bottlenecks"]]
        actions = [_chart_action("bottleneck", "Bar: bottleneck scores"),
                   _chart_action("util_vs_risk", "Scatter: utilisation vs failure")]
        agent = "Capacity & Scheduling"

    elif intent in ("schedule", "scenario"):
        if intent == "scenario":
            data = T.tool_compare_scenarios()
            sc = data["scenarios"]
            headline = "Scenario trade-off computed (throughput vs risk vs cost)"
            details = [f"{k}: makespan {v.get('makespan_hours')}h, tardiness "
                       f"{v.get('total_tardiness_hours')}h, cost Rs{v.get('total_energy_cost_inr')}"
                       for k, v in sc.items()]
            actions = [_chart_action("scenarios", "Show scenario comparison"),
                       {"id": "export_plan", "label": "Export min-risk plan (CSV)",
                        "params": {"scenario": "min_risk"}}]
        else:
            data = T.tool_optimize_schedule("min_risk")
            k = data.get("kpis", {})
            headline = (f"Optimized schedule for {data.get('scheduled_orders', 0)} orders "
                        f"(makespan {k.get('makespan_hours')}h, tardiness {k.get('total_tardiness_hours')}h)")
            details = [f"{a['order_id']}/{a['operation_id']} -> {a['machine_id']} "
                       f"{a['start']} to {a['end']}" for a in data.get("assignments", [])[:12]]
            actions = [{"id": "export_plan", "label": "Export this plan (CSV)",
                        "params": {"scenario": "min_risk"}}]
        agent = "Capacity & Scheduling"

    elif intent == "prioritize":
        data = T.tool_prioritize_orders()
        headline = f"Top {data['count']} orders to prioritise"
        details = [f"#{o['rank']} {o['order_id']} ({o['product']}) score {o['priority_score']:.0f}, "
                   f"due {o['due_date']}" for o in data["ranked_orders"]]
        actions = []
        agent = "Capacity & Scheduling"

    elif intent == "allocation":
        data = T.tool_allocate_resources()
        gaps = data.get("skill_gaps", [])
        headline = ("Workforce covers all skills" if not gaps
                    else f"Workforce shortfall in: {', '.join(gaps)}")
        details = [f"{c['skill']}: coverage {c['coverage_ratio']:.1f}x ({c['status']})"
                   for c in data["skill_coverage"]]
        actions = []
        agent = "Capacity & Scheduling"

    elif intent == "delay_risk":
        data = T.tool_delay_risk()
        headline = data["headline"]
        details = data["details"]
        actions = [_email_action("At-risk orders alert", details),
                   _chart_action("delay_risk", "Show delay-risk chart")]
        agent = "Risk & Reliability"

    elif intent == "downtime":
        data = T.tool_downtime_risk()
        headline = data["headline"]
        details = data["details"]
        actions = [_chart_action("downtime", "Bar: downtime risk"),
                   _chart_action("fault_types", "Pie: fault-type breakdown")]
        at_risk = data.get("recommended_actions", [])
        if any("maintenance" in a.lower() for a in at_risk):
            actions.insert(0, _email_action("Machine maintenance alert", details))
        agent = "Risk & Reliability"

    elif intent == "demand":
        data = T.tool_demand_forecast()
        headline = data["headline"]
        details = data["details"]
        actions = [_chart_action("demand", "Bar: demand forecast"),
                   _chart_action("demand_regions", "Pie: demand by region")]
        agent = "Demand & Inventory"

    elif intent == "reorder":
        data = reorder_recommendations()
        headline = f"{data['count']} material(s) recommended for re-order"
        details = [f"{r['material_id']} {r['material_name']}: stock {r['current_stock']}, "
                   f"suggest {r['suggested_quantity']} (Rs{r['estimated_cost_inr']:.0f})"
                   for r in data["recommendations"]]
        actions = [{"id": "place_reorder",
                    "label": f"Re-order {r['material_id']} x{r['suggested_quantity']}",
                    "params": {"material_id": r["material_id"], "quantity": r["suggested_quantity"]}}
                   for r in data["recommendations"]]
        agent = "Demand & Inventory"

    else:  # overview
        cap = T.tool_capacity_analysis()
        delay = T.tool_delay_risk(3)
        down = T.tool_downtime_risk()
        data = {"capacity": cap, "delay_risk": delay, "downtime": down}
        headline = (f"Plant overview: utilisation {cap['overall_utilization_pct']:.0f}%, "
                    f"{len(delay['details'])} risk items, {down['headline']}")
        details = [cap["verdict"], delay["headline"], down["headline"]]
        actions = [_chart_action("capacity", "Show utilisation chart"),
                   _email_action("Production status summary", details)]
        agent = "Orchestrator"

    return {
        "intent": intent,
        "agent": agent,
        "headline": headline,
        "details": details,
        "data": data,
        "suggested_actions": actions,
    }
