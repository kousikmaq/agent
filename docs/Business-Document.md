# Production Planning and Schedule Optimization Agent

## Business Document

---

## 1. What this product is

This is a production planning tool for a factory that makes physical goods on machines. The sample
factory in the current build is a beverage plant that produces drinks in cans and bottles, but the
same tool fits any discrete manufacturing plant that runs orders through a sequence of machines and
workers.

Every working day a factory has to answer a hard question: given all the open customer orders, the
machines available, the workers on shift, and the raw materials in stock, what is the best way to run
the floor today? Which job goes on which machine, at what time, with which operator, so that orders
ship on time and the plant does not waste money?

This tool answers that question automatically. It reads the state of the factory for a chosen date,
builds a complete schedule, checks the schedule for problems, suggests fixes, and lets a planner
compare different ways of running the day before committing to one. A planner can also ask a built in
assistant plain questions about the plan in normal language.

The scheduling itself is done by a mathematical optimizer, not by guesswork and not by a language
model. The same inputs always produce the same plan, which matters in a factory where people need to
trust and repeat decisions.

---

## 2. The problem it solves

Most plants still plan the day in spreadsheets or in the head of a senior planner. That approach has
a few well known pain points.

- **It is slow.** Rebuilding a schedule by hand after a machine breaks down or an urgent order arrives
  can take hours.
- **It is fragile.** The knowledge often lives with one or two experienced people. When they are away,
  planning quality drops.
- **It is hard to compare options.** A planner rarely has time to work out what would happen if they
  added an overtime shift or moved a job to a backup machine. They pick the first workable plan and
  move on.
- **Problems are found too late.** A material shortage or an overloaded machine is often noticed only
  when an order is already late.
- **It is hard to explain.** When a customer asks why their order slipped, the answer is usually a
  guess rather than a clear reason.

This product takes over the heavy calculation, flags problems before they hurt, and gives every
decision a clear reason.

---

## 3. Who uses it

- **Production planners and schedulers.** The main users. They run the plan for the day, review it,
  handle risks, and commit the final schedule.
- **Plant and operations managers.** They watch the key numbers (on time delivery, machine load, cost)
  and read the daily summary.
- **Shop floor supervisors.** They use the live operations view to see machine, worker, and order
  status as the day runs.
- **Procurement and materials staff.** They act on reorder suggestions and stock alerts.

---

## 4. Main use cases

1. **Build today's plan.** Load the factory state for a date and generate a full machine by machine,
   worker by worker schedule in one click.
2. **See the health of the plan at a glance.** On time delivery percentage, machine utilization,
   total lateness, work in progress, and estimated cost are shown as clear cards.
3. **Catch risks early.** The tool scans the plan for late orders, overloaded machines, material
   shortages, low safety stock, worker conflicts, and maintenance clashes, and grades each by severity.
4. **Fix problems in place.** A planner can raise the priority of at risk orders, apply a suggested
   fix, and see the before and after numbers. Every change is logged and can be undone.
5. **Compare what if scenarios.** The tool prepares four ways to run the day (the current plan, adding
   overtime, using backup machines, and adding a night shift) and shows how each one changes delivery,
   lateness, and cost. The planner picks the one to commit.
6. **Plan the week ahead.** A seven day view shows the target workload per day and progress against it,
   with a weekly refresh cadence.
7. **Track deliveries.** Orders due within the horizon are shown as red, amber, or green, and the tool
   flags drift when today's promise slips against yesterday's plan.
8. **Handle materials.** View demand against stock, spot shortfalls, and place a purchase order that
   sends a confirmation email.
9. **Send reports and alerts.** Email a plan, a report, or a risk summary to the right people.
10. **Ask the assistant.** Type a question such as "why is order ORD0142 late" and get a grounded
    answer built from the real plan data, plus suggested next actions.
11. **Watch live operations.** A separate page shows the current state of machines, workers, orders,
    and materials on the floor.

---

## 5. Feature list

### Planning and scheduling
- One click generation of a full daily schedule using a constraint optimizer.
- Timeline (Gantt) views grouped by machine and by order.
- Order table with inline priority editing.
- Forward looking next day and next week plan generation.

### Analytics and reporting
- KPI dashboard: on time delivery, machine utilization, tardiness, work in progress, estimated cost.
- Capacity analysis per machine with a plain verdict on whether the plant can cope.
- Bottleneck detection that scores each machine on load, failure risk, and backlog.
- Cost breakdown covering labor (regular and overtime), machine energy, and lateness penalties.
- Insight charts (utilization, downtime risk, delay risk, demand, scenarios, fault types) with a one
  line takeaway for each.

### Risk and recommendations
- Automatic detection of late orders, machine overload, capacity shortage, material shortage, low
  safety stock, worker conflicts, and maintenance conflicts.
- Severity grading (low, medium, high, critical).
- Recommendations that map each risk to a concrete, checked action.
- Apply, undo, and full history of every plan change with before and after numbers.

### Scenario planning
- Four prepared scenarios: current plan, overtime, alternate machines, additional shift.
- Side by side KPI and cost comparison against the baseline.
- Commit a chosen scenario as the working plan.
- A short written explanation of why each plan looks the way it does.

### Deliveries and materials
- Delivery status board with red, amber, green flags over a chosen horizon.
- Delivery drift analysis against the previous planned day.
- Materials view with demand versus stock and shortage alerts.
- One click reorder with automatic order confirmation email.

### Assistant and communication
- Explain only chat assistant that answers questions from the real plan data.
- Email reports, plans, and risk alerts to configured recipients.

### Live operations
- Real time shop floor board for machines, workers, orders, and materials.

### Predictive signals (supporting, not for scheduling)
- Machine learning models that estimate delay risk, machine downtime risk, failure type, operation
  duration, and demand forecast. These feed the risk and insight views. They never make the schedule.

---

## 6. What makes it different

- **The schedule is deterministic.** It comes from a proven constraint solver (Google OR-Tools
  CP-SAT), so the same inputs always give the same plan. There is no black box guessing where it
  matters.
- **The language model is kept on a short leash.** It only explains results and answers questions. It
  never decides the schedule. This keeps trust high and keeps the plant in control.
- **It finds problems before they cost money.** Risk detection and predictive signals surface trouble
  while there is still time to act.
- **It shows the trade offs.** Instead of one plan, it lets a planner weigh delivery against cost
  before committing.
- **Every decision has a reason.** Modifications are logged, and the assistant can explain any part of
  the plan in plain words.

---

## 7. Potential market solutions (the landscape)

There are established players in this space. They are grouped below by type, along with where this
product sits relative to them.

### Large enterprise APS (Advanced Planning and Scheduling)
- **SAP (IBP and PP or DS in S or 4HANA)**, **Oracle Supply Chain Planning**, **Siemens Opcenter APS
  (formerly Preactor)**, **Dassault DELMIA Ortems**.
- These are deep, capable, and expensive. They usually require long implementation projects, heavy
  configuration, and a big budget. They fit large enterprises with dedicated IT teams.

### Mid market and specialist scheduling tools
- **PlanetTogether**, **Asprova**, **DELMIAWorks (formerly IQMS)**, **Katana**, **MRPeasy**.
- These are lighter than the giants and target small to mid size manufacturers. Depth of optimization
  and explainability varies.

### Optimization platforms and libraries
- **Google OR-Tools**, **Gurobi**, **IBM ILOG CPLEX**, **FICO Xpress**.
- These are the engines, not finished products. They give the solving power but need a full
  application, data pipeline, and user interface built around them. This product is built on OR-Tools
  and adds exactly that layer.

### AI scheduling copilots (closest comparisons)
A newer group of products pairs scheduling with an AI assistant, which is the class this product is
closest to. Three current examples:

- [Production Schedule Optimizer Agent (Microsoft Manufacturing Scenario Library)](https://adoption.microsoft.com/en-us/scenario-library/manufacturing/production-schedule-optimizer-agent/)
- [Manufacturing Scheduling Copilot (COMPASS)](https://compass-work.com/en)
- [AI Production Scheduling Copilot (ZenAI)](https://zenaicorp.com/en/cases/manufacturing-ai-scheduling-copilot)

These show clear market demand for an assistant that helps plan and explains its reasoning. The main
difference in this product is the strict split of duties: the schedule is produced by a deterministic
constraint solver so results are repeatable and auditable, and the AI is limited to explaining the
plan and answering questions rather than making the scheduling decision.

### Spreadsheets and manual planning
- Still the most common tool in practice for many plants. Cheap and flexible but slow, error prone,
  and impossible to scale or explain.

### Where this product fits
This product sits between the heavy enterprise suites and the manual spreadsheet approach. It gives a
plant real constraint based optimization, risk detection, scenario comparison, and a plain language
assistant, without the cost and multi month rollout of the large suites. It is a strong fit for a
single plant or a focused operation that wants trustworthy automated planning quickly, and it can be
extended toward live ERP or MES data instead of the built in simulator.

---

## 8. Current status and boundaries

- The factory data today comes from a built in daily simulator that produces realistic snapshots. The
  design keeps the data source behind a clean boundary so it can later be swapped for a live ERP or MES
  feed without changing the planning logic.
- Sign in is a light client side gate restricted to one company domain. It is a convenience, not a
  hardened security boundary, so any sensitive deployment needs proper server side access control.
- Emails and purchase orders run in a simulated or local outbox mode unless real mail settings are
  configured.
