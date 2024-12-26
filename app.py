from flask import Flask, render_template, request
import simpy
import pandas as pd
from datetime import datetime, timedelta
import math

app = Flask(__name__)

def parse_datetime(datetime_string):
    """Parse a datetime string using multiple formats."""
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(datetime_string, fmt)
        except ValueError:
            continue
    raise ValueError(f"Time data '{datetime_string}' does not match any known format.")

def run_simulation(start_date, shifts, hours_per_shift, operators_per_shift, orders, scrap_rate, downtime_rate):
    env = simpy.Environment()
    completed_orders = []
    daily_metrics = {}
    total_production = 0
    total_lead_time = 0  # Add this to track total lead time

    def add_to_daily_metrics(date, production, downtime, scrap):
        if date not in daily_metrics:
            daily_metrics[date] = {"production": 0, "downtime": 0, "scrap": 0}
        daily_metrics[date]["production"] += production
        daily_metrics[date]["downtime"] += downtime
        daily_metrics[date]["scrap"] += scrap

    def process_order(env, order):
        nonlocal total_production, total_lead_time
        entry_time = parse_datetime(order["entry_time"])
        agreed_lead_time = order["agreed_lead_time"]
        start_time = max(entry_time, parse_datetime(start_date))
        yield env.timeout((start_time - parse_datetime(start_date)).total_seconds() / 3600)

        production_time = order["size"] / (operators_per_shift * hours_per_shift)
        scrap = production_time * scrap_rate
        downtime = production_time * downtime_rate
        yield env.timeout(production_time + scrap + downtime)

        completion_time = start_time + timedelta(hours=production_time + scrap + downtime)
        formatted_completion_time = completion_time.strftime("%m/%d/%Y %I:%M")
        production_date = completion_time.strftime("%m/%d/%Y")

        add_to_daily_metrics(production_date, order["size"], downtime, scrap)

        total_production += order["size"]
        lead_time = (completion_time - entry_time).total_seconds() / 3600  # Calculate lead time in hours
        total_lead_time += lead_time  # Add to total lead time

        completed_orders.append({
            "order_id": order["id"],
            "completion_time": formatted_completion_time,
            "lead_time": round(lead_time, 2),  # Include lead time per order (optional)
            "on_time": completion_time <= entry_time + timedelta(hours=agreed_lead_time)
        })

    for order in orders:
        env.process(process_order(env, order))
    env.run()

    return completed_orders, daily_metrics, total_production, total_lead_time

@app.route("/", methods=["GET", "POST"])
def index():
    return render_template("index.html")

@app.route("/update-results", methods=["POST"])
def update_results():
    # Collect user inputs
    start_date = request.form["start_date"]
    shifts = int(request.form["shifts"])
    hours_per_shift = int(request.form["hours_per_shift"])
    operators_per_shift = int(request.form["operators_per_shift"])
    scrap_rate = float(request.form["scrap_rate"])
    downtime_rate = float(request.form["downtime_rate"])

    # Parse CSV file
    file = request.files["orders_file"]
    orders = []
    if file:
        csv_data = pd.read_csv(file)
        for _, row in csv_data.iterrows():
            orders.append({
                "id": int(row["order"]),
                "size": int(row["size"]),
                "entry_time": row["entry time"],
                "agreed_lead_time": float(row["agreed lead time"]),
            })

    # Run simulation
    completed_orders, daily_metrics, total_production, total_lead_time = run_simulation(
        start_date, shifts, hours_per_shift, operators_per_shift, orders, scrap_rate, downtime_rate
    )

    # Generate DataFrames
    df = pd.DataFrame(completed_orders)
    daily_metrics_df = pd.DataFrame.from_dict(daily_metrics, orient="index")
    daily_metrics_df.index.name = "Date"
    daily_metrics_df.reset_index(inplace=True)

    # Calculate Metrics
    metrics = {
        "total_production": total_production,
        "average_lead_time": round(total_lead_time / len(orders), 2) if orders else 0,
        "on_time_delivery": df[df["on_time"]].shape[0],
    }
    metrics["on_time_delivery_percentage"] = (metrics["on_time_delivery"] / len(orders)) * 100

    production_parameters = {
        "start_date": start_date,
        "shifts": shifts,
        "hours_per_shift": hours_per_shift,
        "operators_per_shift": operators_per_shift,
        "scrap_rate": scrap_rate,
        "downtime_rate": downtime_rate,
    }

    return render_template(
        "partials/results.html",
        table=df.to_html(classes="table table-striped"),
        daily_table=daily_metrics_df.to_html(classes="table table-striped"),
        metrics=metrics,
        production_parameters=production_parameters,
    )

if __name__ == "__main__":
    app.run(debug=True)
