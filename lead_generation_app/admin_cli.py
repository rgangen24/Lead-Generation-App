import json
import sys
from datetime import datetime, timedelta
from sqlalchemy import select, func
from lead_generation_app.database.database import get_session
from lead_generation_app.database.models import BusinessClient, Payment, DeliveredLead, QualifiedLead, OptOut
from lead_generation_app.payments import update_subscription
from lead_generation_app.metrics import get_metrics


def _clients_list():
    s = get_session()
    try:
        now = datetime.utcnow()
        start = datetime(now.year, now.month, 1)
        end = start + timedelta(days=31)
        rows = s.execute(select(BusinessClient)).scalars().all()
        out = []
        for c in rows:
            paid = s.execute(select(func.count(Payment.id)).where(Payment.business_client_id == c.id).where(Payment.payment_status.in_( ["paid","success"] ))).scalar_one()
            delivered = s.execute(select(func.count(DeliveredLead.id)).where(DeliveredLead.business_client_id == c.id).where(DeliveredLead.delivered_at >= start).where(DeliveredLead.delivered_at < end)).scalar_one()
            out.append({"id": c.id, "name": c.business_name, "plan": c.subscription_plan, "cap_used": int(delivered), "next_billing_date": (c.next_billing_date.isoformat() if c.next_billing_date else None), "payments": int(paid)})
        print(json.dumps(out))
    finally:
        s.close()


def _clients_update(client_id, plan_name):
    ok = update_subscription(int(client_id), plan_name=plan_name, number_of_users=None, payment_status="paid")
    print(json.dumps({"updated": bool(ok)}))


def _metrics_show():
    print(json.dumps(get_metrics()))


def _optout_list(kind):
    s = get_session()
    try:
        rows = s.execute(select(OptOut).where(OptOut.method == kind)).scalars().all()
        print(json.dumps([{"value": r.value, "created_at": (r.created_at.isoformat() if r.created_at else None)} for r in rows]))
    finally:
        s.close()


def _optout_add(kind, value):
    s = get_session()
    try:
        row = OptOut(method=kind, value=value, created_at=datetime.utcnow())
        s.add(row)
        s.commit()
        print(json.dumps({"added": True}))
    finally:
        s.close()


def main():
    try:
        import click
    except Exception:
        cmd = (sys.argv[1:] + [""])[:1][0]
        if cmd == "clients":
            sub = (sys.argv[2:] + [""])[:1][0]
            if sub == "list":
                _clients_list()
            elif sub == "update":
                _clients_update(sys.argv[3], sys.argv[4])
            else:
                print("usage: admin_cli.py clients list | clients update <client_id> <plan>")
        elif cmd == "metrics":
            _metrics_show()
        elif cmd == "optout":
            sub = (sys.argv[2:] + [""])[:1][0]
            if sub == "list":
                _optout_list(sys.argv[3])
            elif sub == "add":
                _optout_add(sys.argv[3], sys.argv[4])
            else:
                print("usage: admin_cli.py optout list <type> | optout add <type> <value>")
        else:
            print("usage: admin_cli.py clients|metrics|optout ...")
        return

    @click.group()
    def cli():
        pass

    @cli.group()
    def clients():
        pass

    @clients.command("list")
    def clients_list():
        _clients_list()

    @clients.command("update")
    @click.argument("client_id")
    @click.argument("plan_name")
    def clients_update(client_id, plan_name):
        _clients_update(client_id, plan_name)

    @cli.group()
    def metrics():
        pass

    @metrics.command("show")
    def metrics_show():
        _metrics_show()

    @cli.group()
    def optout():
        pass

    @optout.command("list")
    @click.argument("kind")
    def optout_list(kind):
        _optout_list(kind)

    @optout.command("add")
    @click.argument("kind")
    @click.argument("value")
    def optout_add(kind, value):
        _optout_add(kind, value)

    cli()


if __name__ == "__main__":
    main()
