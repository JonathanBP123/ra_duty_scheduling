import csv
import argparse
import datetime
from collections import defaultdict
from ortools.sat.python import cp_model


class RAScheduler:
    def __init__(self, prefs_file, outdir):
        self.prefs_file = prefs_file
        self.outdir = outdir
        self.ras = []
        self.schedule = []
        self.assignments = defaultdict(lambda: {
            "primaries": 0,
            "secondaries": 0,
            "weekend_primaries": 0,
            "weekend_secondaries": 0
        })

    def load_preferences(self):
        with open(self.prefs_file, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                row["block_pref"] = True if row["block_pref"].lower() == "yes" else False
                row["blackout_dates"] = [
                    d.strip() for d in row["blackout_dates"].split(";") if d.strip()
                ] if row["blackout_dates"] else []
                row["weekend_unavailable"] = [
                    d.strip() for d in row["weekend_unavailable"].split(";") if d.strip()
                ] if row["weekend_unavailable"] else []
                self.ras.append(row)

    def build_schedule(self):
        start_date = datetime.date(2025, 9, 21)
        end_date = datetime.date(2025, 12, 13)
        exclude_start = datetime.date(2025, 11, 24)
        exclude_end = datetime.date(2025, 11, 30)

        all_dates = []
        d = start_date
        while d <= end_date:
            if not (exclude_start <= d <= exclude_end):
                all_dates.append(d)
            d += datetime.timedelta(days=1)

        # All shifts
        shifts = []
        for date in all_dates:
            for area in ["NE1", "NE2"]:
                shifts.append((date, area, "primary"))
                shifts.append((date, area, "secondary"))

        model = cp_model.CpModel()
        x = {}

        # Decision variables
        for i, ra in enumerate(self.ras):
            for j, (date, area, role) in enumerate(shifts):
                x[(i, j)] = model.NewBoolVar(f"x_{i}_{j}")

        # Constraints: each shift has exactly 1 RA
        for j, (date, area, role) in enumerate(shifts):
            model.Add(sum(x[(i, j)] for i in range(len(self.ras))) == 1)

        # Respect preferences and blackout dates
        for i, ra in enumerate(self.ras):
            for j, (date, area, role) in enumerate(shifts):
                # Skip blackout dates
                if date.isoformat() in ra["blackout_dates"]:
                    model.Add(x[(i, j)] == 0)

                # Skip unavailable weekends
                if date.weekday() in [4, 5] and date.isoformat() in ra["weekend_unavailable"]:
                    model.Add(x[(i, j)] == 0)

                # Day-of-week preferences
                weekday_map = {6: "Sun", 0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu"}
                if date.weekday() in weekday_map:
                    pref = ra[weekday_map[date.weekday()]]
                    if pref == "Not Available":
                        model.Add(x[(i, j)] == 0)

        # Constraint — no RA can work more than 1 shift on a given date
        for i, ra in enumerate(self.ras):
            for date in all_dates:
                shifts_on_date = [
                    x[(i, j)]
                    for j, (d, _, _) in enumerate(shifts)
                    if d == date
                ]
                model.Add(sum(shifts_on_date) <= 1)

        # Balance load (rough equal primaries/secondaries)
        # --- Fairness variables ---
        n = len(self.ras)
        primaries = [model.NewIntVar(0, len(shifts), f"primaries_{i}") for i in range(n)]
        secondaries = [model.NewIntVar(0, len(shifts), f"secondaries_{i}") for i in range(n)]
        wprimaries = [model.NewIntVar(0, len(shifts), f"wprimaries_{i}") for i in range(n)]
        wsecondaries = [model.NewIntVar(0, len(shifts), f"wsecondaries_{i}") for i in range(n)]

        for i in range(n):
            # Primary count
            model.Add(primaries[i] == sum(
                x[(i, j)] for j, (_, _, role) in enumerate(shifts) if role == "primary"
            ))
            # Secondary count
            model.Add(secondaries[i] == sum(
                x[(i, j)] for j, (_, _, role) in enumerate(shifts) if role == "secondary"
            ))
            # Weekend primary
            model.Add(wprimaries[i] == sum(
                x[(i, j)] for j, (d, _, role) in enumerate(shifts) if role == "primary" and d.weekday() in [4,5]
            ))
            # Weekend secondary
            model.Add(wsecondaries[i] == sum(
                x[(i, j)] for j, (d, _, role) in enumerate(shifts) if role == "secondary" and d.weekday() in [4,5]
            ))

        def add_spread(vars, name):
            maxv = model.NewIntVar(0, len(shifts), f"max_{name}")
            minv = model.NewIntVar(0, len(shifts), f"min_{name}")
            model.AddMaxEquality(maxv, vars)
            model.AddMinEquality(minv, vars)
            spread = model.NewIntVar(0, len(shifts), f"spread_{name}")
            model.Add(spread == maxv - minv)
            return spread

        spread_prim = add_spread(primaries, "prim")
        spread_sec = add_spread(secondaries, "sec")
        spread_wprim = add_spread(wprimaries, "wprim")
        spread_wsec = add_spread(wsecondaries, "wsec")


        # Block scheduling encouragement
        block_bonus = []
        for i, ra in enumerate(self.ras):
            if ra["block_pref"]:
                for j1, (d1, _, _) in enumerate(shifts):
                    for j2, (d2, _, _) in enumerate(shifts):
                        if d2 == d1 + datetime.timedelta(days=1):
                            y = model.NewBoolVar(f"block_{i}_{j1}_{j2}")
                            model.AddBoolAnd([x[(i, j1)], x[(i, j2)]]).OnlyEnforceIf(y)
                            block_bonus.append(y)

        # Minimize spread for fair distribution, still encourage block scheduling
        model.Minimize(spread_prim + spread_sec + spread_wprim + spread_wsec + sum(block_bonus))

        # Solve
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 60
        result = solver.Solve(model)

        if result not in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            print("❌ No feasible schedule found")
            return

        # Build final schedule: group by date
        schedule_by_date = defaultdict(lambda: {
            "NE1_primary": "",
            "NE2_primary": "",
            "NE1_secondary": "",
            "NE2_secondary": ""
        })

        for j, (date, area, role) in enumerate(shifts):
            for i, ra in enumerate(self.ras):
                if solver.Value(x[(i, j)]) == 1:
                    key = f"{area}_{role}"
                    first_name = ra["name"].split()[0]
                    schedule_by_date[date.isoformat()][key] = first_name

                    if role == "primary":
                        self.assignments[ra["ra_id"]]["primaries"] += 1
                        if date.weekday() in [4, 5]:
                            self.assignments[ra["ra_id"]]["weekend_primaries"] += 1
                    else:
                        self.assignments[ra["ra_id"]]["secondaries"] += 1
                        if date.weekday() in [4, 5]:
                            self.assignments[ra["ra_id"]]["weekend_secondaries"] += 1

        self.schedule = schedule_by_date

    def save_outputs(self):
        # Save schedule.csv (date-row format)
        sched_file = f"{self.outdir}/schedule.csv"
        with open(sched_file, "w", newline="") as f:
            fieldnames = ["date", "NE1_primary", "NE2_primary", "NE1_secondary", "NE2_secondary"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for date in sorted(self.schedule.keys()):
                row = {"date": date}
                row.update(self.schedule[date])
                writer.writerow(row)

        # Save metrics.csv (per-RA counts)
        metrics_file = f"{self.outdir}/schedule_metrics.csv"
        with open(metrics_file, "w", newline="") as f:
            fieldnames = ["first_name", "primaries", "secondaries", "weekend_primaries", "weekend_secondaries"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for ra in self.ras:
                fname = ra["name"].split()[0]   # get first name
                data = self.assignments[ra["ra_id"]]
                writer.writerow({
                    "first_name": fname,
                    "primaries": data["primaries"],
                    "secondaries": data["secondaries"],
                    "weekend_primaries": data["weekend_primaries"],
                    "weekend_secondaries": data["weekend_secondaries"]
                })

        # Print summary
        print("\n=== Summary ===")
        total_primary = sum(a["primaries"] for a in self.assignments.values())
        total_secondary = sum(a["secondaries"] for a in self.assignments.values())
        total_weekend_primary = sum(a["weekend_primaries"] for a in self.assignments.values())
        total_weekend_secondary = sum(a["weekend_secondaries"] for a in self.assignments.values())

        print(f"Total primary shifts: {total_primary}")
        print(f"Total secondary shifts: {total_secondary}")
        print(f"Total weekend primaries: {total_weekend_primary}")
        print(f"Total weekend secondaries: {total_weekend_secondary}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefs", required=True, help="Path to RA preferences CSV")
    parser.add_argument("--outdir", required=True, help="Directory for outputs")
    args = parser.parse_args()

    scheduler = RAScheduler(args.prefs, args.outdir)
    scheduler.load_preferences()
    scheduler.build_schedule()
    scheduler.save_outputs()


if __name__ == "__main__":
    main()
